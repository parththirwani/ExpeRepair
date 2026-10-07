"""
Memory gate combinator. Takes a candidate entry and decides promote vs quarantine.

Supports five modes:
  - none:      no memory (skip entirely)
  - baseline:  unmodified ExpeRepair (promote everything)
  - gated:     denylist + execution evidence + weak provenance filter
  - gated-provenance:  provenance check only
  - gated-execution:   execution evidence only

Reproduce gate is judge-independent: never reads if-reproduce or new_result.
Patch gate requires either execution evidence or denylist + provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config
from memory_gate.provenance import test_patch_overlap
from memory_gate.evidence import check_exec_evidence
from memory_gate.denylist import scan_test, scan_patch
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
    FACTS = "facts"

    VALID = {NONE, BASELINE, GATED, GATED_PROVENANCE, GATED_EXECUTION, FACTS}


def _check_denylist(entry: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    test = entry.get("new_test") or ""
    patch = entry.get("new_patch") or ""

    if test:
        flags = scan_test(test)
        if flags:
            reasons.append(f"denylist-test: {', '.join(flags)}")
            return False, reasons
        reasons.append("denylist-test: clean")

    if patch:
        flags = scan_patch(patch)
        if flags:
            reasons.append(f"denylist-patch: {', '.join(flags)}")
            return False, reasons
        reasons.append("denylist-patch: clean")

    return True, reasons


def _check_execution(entry: dict[str, Any], task, regression_test_file) -> tuple[bool, list[str]]:
    reasons = []
    test_content = entry.get("new_test") or ""
    patch_content = entry.get("new_patch") or ""

    if not test_content:
        reasons.append("execution: no test to run (patch-only, skipped)")
        return True, reasons

    if task is not None:
        ev_ok, ev_reasons = check_exec_evidence(
            task, test_content, patch_content or None, regression_test_file
        )
        reasons.extend(ev_reasons)
        return ev_ok, reasons
    else:
        if patch_content:
            reasons.append("execution: no task object (patch entry deferred)")
            return True, reasons
        else:
            reasons.append("execution: no task object (deferred, relying on denylist+provenance)")
            return True, reasons


def _check_provenance(entry: dict[str, Any], issue_text: str) -> tuple[bool, list[str]]:
    reasons = []
    patch_content = entry.get("new_patch") or ""
    test_content = entry.get("new_test") or ""
    code = patch_content if patch_content else test_content
    if code:
        from memory_gate.provenance import compute_issue_overlap, token_jaccard
        score_i2c = compute_issue_overlap(issue_text, code)
        score_c2i = compute_issue_overlap(code, issue_text)
        jaccard = token_jaccard(issue_text, code)
        if len(code) < 30:
            reasons.append(f"provenance: code too short ({len(code)} chars), using jaccard={jaccard:.2f}")
        elif score_i2c > 0.85 and score_c2i > 0.95:
            reasons.append(f"provenance: near-total overlap {score_i2c:.2f}/{score_c2i:.2f}")
            return False, reasons
        else:
            reasons.append(f"provenance: overlap i2c={score_i2c:.2f} c2i={score_c2i:.2f} jaccard={jaccard:.2f} OK")
    else:
        reasons.append("provenance: no code to check")
    return True, reasons


def gate_candidate(
    entry: dict[str, Any],
    issue_text: str,
    task_dir: str,
    task=None,
    regression_test_file: str | None = None,
) -> GateResult:
    mode = config.memory_mode

    if mode == MemoryGateMode.NONE:
        return GateResult(promoted=False, reasons=["memory_mode=none"])

    if mode == MemoryGateMode.BASELINE:
        promote(entry, task_dir, ["memory_mode=baseline: always promote"])
        return GateResult(promoted=True, reasons=["baseline mode"])

    reasons = []
    denylist_ok = True
    execution_ok = True
    provenance_ok = True

    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_EXECUTION, MemoryGateMode.FACTS):
        denylist_ok, denylist_reasons = _check_denylist(entry)
        reasons.extend(denylist_reasons)

    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_EXECUTION, MemoryGateMode.FACTS):
        execution_ok, exec_reasons = _check_execution(entry, task, regression_test_file)
        reasons.extend(exec_reasons)

    if mode in (MemoryGateMode.GATED, MemoryGateMode.GATED_PROVENANCE, MemoryGateMode.FACTS):
        provenance_ok, prov_reasons = _check_provenance(entry, issue_text)
        reasons.extend(prov_reasons)

    if mode == MemoryGateMode.FACTS:
        if denylist_ok and execution_ok and provenance_ok:
            promote(entry, task_dir, reasons)
            return GateResult(promoted=True, reasons=reasons)
        else:
            quarantine(entry, task_dir, reasons)
            return GateResult(promoted=False, reasons=reasons)

    if denylist_ok and execution_ok and provenance_ok:
        promote(entry, task_dir, reasons)
        return GateResult(promoted=True, reasons=reasons)
    else:
        quarantine(entry, task_dir, reasons)
        return GateResult(promoted=False, reasons=reasons)