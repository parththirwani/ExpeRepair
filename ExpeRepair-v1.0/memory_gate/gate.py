"""
Memory gate combinator. Takes a candidate entry and decides promote vs quarantine.

Supports five modes:
  - none:      no memory (skip entirely)
  - baseline:  unmodified ExpeRepair (promote everything)
  - gated:     provenance + execution evidence required
  - gated-provenance:  provenance check only
  - gated-execution:   execution evidence only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config
from memory_gate.provenance import test_patch_overlap
from memory_gate.evidence import check_exec_evidence
from memory_gate.store import promote, quarantine


@dataclass
class GateResult:
    promoted: bool
    reasons: list[str]


class MemoryGateMode:
    NONE = "none"
    BASELINE = "baseline"
    GATED = "gated"
    GATED_PROVENANCE = "gated-provenance"
    GATED_EXECUTION = "gated-execution"

    VALID = {NONE, BASELINE, GATED, GATED_PROVENANCE, GATED_EXECUTION}


def gate_candidate(
    entry: dict[str, Any],
    issue_text: str,
    task_dir: str,
    task=None,
    regression_test_file: str | None = None,
) -> GateResult:
    """
    Run the gate on a candidate memory entry.

    Args:
        entry:              The dict being written (experience entry).
        issue_text:         The issue/problem statement text.
        task_dir:           Output directory for this task (store tier files).
        task:               Optional SweTask for execution evidence.
        regression_test_file: Optional regression test file path.

    Returns:
        GateResult with promoted bool + reasons list.
    """
    mode = config.memory_mode

    if mode == MemoryGateMode.NONE:
        return GateResult(promoted=False, reasons=["memory_mode=none"])

    if mode == MemoryGateMode.BASELINE:
        promote(entry, task_dir, ["memory_mode=baseline: always promote"])
        return GateResult(promoted=True, reasons=["baseline mode"])

    reasons = []
    provenance_ok = True
    execution_ok = True

    # Check provenance
    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_PROVENANCE):
        patch_content = entry.get("new_patch") or ""
        test_content = entry.get("new_test") or ""

        # For patches, overlap is expected (the diff touches the same code
        # described in the issue). A perfect 1.0 is common for simple fixes
        # that change one line. Only flag if overlap is truly extreme
        # AND the candidate adds no novel tokens. Use asymmetric overlap
        # (fraction of candidate tokens also in issue). Raise threshold
        # to 0.85 to avoid quarantining legitimate patches.
        from memory_gate.provenance import compute_issue_overlap
        code = patch_content if patch_content else test_content
        if code:
            score = compute_issue_overlap(issue_text, code)
            overloaded = score > 0.85 and compute_issue_overlap(code, issue_text) > 0.95
            if overloaded:
                provenance_ok = False
                reasons.append(f"provenance: near-total overlap {score:.2f}")
            else:
                reasons.append(f"provenance: overlap {score:.2f} OK")
        else:
            reasons.append("provenance: no code to check")

    # Check execution evidence
    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_EXECUTION):
        patch_content = entry.get("new_patch") or ""
        test_content = entry.get("new_test") or ""

        if patch_content and test_content:
            # Patch experiences: run before/after test execution
            if task is not None:
                ev_ok, ev_reasons = check_exec_evidence(
                    task, test_content, patch_content, regression_test_file
                )
                execution_ok = ev_ok
                reasons.extend(ev_reasons)
            else:
                reasons.append("execution: no task object for patch check")
                execution_ok = False
        elif test_content and not patch_content:
            # Reproduce experiences: use LLM's if-reproduce judgement
            repro = entry.get("new_check_repro", {})
            llm_yes = bool(repro.get("if-reproduce") == "YES") if isinstance(repro, dict) else False
            if llm_yes:
                reasons.append("execution: LLM judged reproduction as YES")
            else:
                execution_ok = False
                reasons.append("execution: LLM judged reproduction as NO")
        else:
            # Patch-only entries (no test, patch from review cycle)
            # Assume captured if the entry was written (review passed)
            if mode == MemoryGateMode.GATED_EXECUTION:
                execution_ok = False
                reasons.append("execution: no test to run (patch-only entry)")
            else:
                reasons.append("execution: no test (patch-only, skipped in combined)")

    # Decide
    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_PROVENANCE, MemoryGateMode.GATED_EXECUTION):
        if provenance_ok and execution_ok:
            promote(entry, task_dir, reasons)
            return GateResult(promoted=True, reasons=reasons)
        else:
            quarantine(entry, task_dir, reasons)
            return GateResult(promoted=False, reasons=reasons)

    # Fallback: promote
    promote(entry, task_dir, reasons)
    return GateResult(promoted=True, reasons=reasons)