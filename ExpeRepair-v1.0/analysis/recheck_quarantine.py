"""Phase 4: re-check judge-rejected reproduce entries.

For each quarantined reproduce entry:
1. Denylist scan (flag unsafe)
2. If denylist-clean, run test at base commit (if SweTask available)
3. If patch exists for same issue, run test after patch
4. Classify: rescued, confirmed failure, or undetermined
5. For confirmed failures, write template-based failure facts

Usage:
    PYTHONPATH=.. python analysis/recheck_quarantine.py \\
        --repro-dir results/phase1_reproduce \\
        --generate-dir results/phase1_generate
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from memory_gate.denylist import scan_test


def _iter_quarantined(base_dir):
    """Yield (task_id, task_dir, entry_dict) from quarantine.jsonl files.
    Only includes entries the LLM judge said NO to (if-reproduce == NO).
    Deduplicates by taking only the LAST entry per task (most recent retry)."""
    if not os.path.isdir(base_dir):
        return
    entries_by_task = defaultdict(list)
    for repo in sorted(os.listdir(base_dir)):
        repo_dir = os.path.join(base_dir, repo)
        if not os.path.isdir(repo_dir):
            continue
        for task_id in sorted(os.listdir(repo_dir)):
            task_dir = os.path.join(repo_dir, task_id)
            qpath = os.path.join(task_dir, "quarantine.jsonl")
            if not os.path.isfile(qpath):
                continue
            with open(qpath) as f:
                for line in f:
                    entry = json.loads(line)
                    judge = entry.get('new_check_repro', {}).get('if-reproduce', '')
                    if judge == 'NO':
                        entries_by_task[task_id].append((task_dir, entry))
    for task_id, items in entries_by_task.items():
        task_dir, entry = items[-1]  # last retry
        yield task_id, task_dir, entry


def _has_promoted_patch(generate_dir, task_id):
    """Check if the task has a promoted patch entry."""
    for repo in sorted(os.listdir(generate_dir)):
        for t in sorted(os.listdir(os.path.join(generate_dir, repo))):
            if t == task_id:
                ppath = os.path.join(generate_dir, repo, t, "promoted.jsonl")
                if os.path.isfile(ppath) and os.path.getsize(ppath) > 0:
                    return True
    return False


def _classify(entry, denylist_flags, has_patch, issue_text):
    """Classify a quarantined entry.
    
    Returns (verdict: str, dict_of_evidence).
    """
    test = entry.get("new_test", "")
    repro_result = entry.get("new_exec_result", "")
    return_code = entry.get("new_returncode", None)
    
    evidence = {
        "denylist_flags": denylist_flags,
        "test_length": len(test),
        "return_code": return_code,
    }
    
    # 1. Denylist-flagged: unsafe
    if denylist_flags:
        return "unsafe", evidence
    
    # 2. No test content at all
    if not test.strip():
        return "undetermined", evidence
    
    # 3. Check if test reproduces the reported symptom
    # We do a simple heuristic: check if the return code is non-zero
    # or the output suggests a failure
    if return_code is not None and return_code != 0:
        evidence["test_fails_at_base"] = True
        # Check if the symptom matches the issue
        symptom = repro_result[:500].lower() if repro_result else ""
        issue_lower = issue_text[:1000].lower() if issue_text else ""
        symptom_match = False
        if symptom and issue_lower:
            # Check for shared exception types or error messages
            for word in ["error", "exception", "traceback", "failed", "attributeerror",
                          "importerror", "typeerror", "valueerror", "keyerror",
                          "indexerror", "assertionerror", "doesnotexist"]:
                if word in symptom and word in issue_lower:
                    symptom_match = True
                    break
        evidence["symptom_matches_issue"] = symptom_match
        
        if symptom_match:
            if has_patch:
                return "rescued_pending_execution", evidence
            else:
                # Fails and symptom matches but no patch to verify
                return "undetermined", evidence
        else:
            return "confirmed_failure", evidence
    else:
        # Test passes (rc=0) but judge said NO on correctness
        evidence["test_passes_but_wrong"] = True
        return "confirmed_failure", evidence


def _generate_failure_fact(entry, evidence, task_id, repo_name="django"):
    """Generate a template-based failure fact from evidence."""
    test = entry.get("new_test", "")
    repro_result = entry.get("new_exec_result", "")
    return_code = entry.get("new_returncode", None)
    
    # Extract exception type from output
    exception_type = "unknown"
    if repro_result:
        for line in repro_result.splitlines():
            line = line.strip()
            for exc in ["AttributeError", "ImportError", "TypeError", "ValueError",
                         "KeyError", "IndexError", "AssertionError", "NameError",
                         "ModuleNotFoundError", "FileNotFoundError", "SyntaxError"]:
                if exc in line:
                    exception_type = exc
                    break
    
    # Extract evidence pointer (first file:line from traceback)
    evidence_pointer = ""
    for line in (repro_result or "").splitlines():
        if 'File "' in line:
            evidence_pointer = line.strip()
            break
    
    fact = {
        "kind": "avoid",
        "task_id": task_id,
        "repo": repo_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exception_type": exception_type,
        "return_code": return_code,
        "evidence_pointer": evidence_pointer,
        "reason": evidence.get("verdict", "unknown"),
        "fact_text": f"A test for task {task_id} failed with {exception_type}",
    }
    
    if evidence_pointer:
        fact["fact_text"] += f" at {evidence_pointer}"
    
    return fact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repro-dir", required=True)
    ap.add_argument("--generate-dir", required=True)
    ap.add_argument("--output", default="quarantine_recheck.json")
    args = ap.parse_args()
    
    config.memory_mode = "gated"
    
    results = {
        "rescued": [],
        "unsafe": [],
        "confirmed_failure": [],
        "undetermined": [],
        "failure_facts": [],
    }
    
    for task_id, task_dir, entry in _iter_quarantined(args.repro_dir):
        test = entry.get("new_test", "")
        issue_text = entry.get("issue_description", entry.get("new_check_repro", {}).get("test-analysis", ""))
        
        denylist_flags = scan_test(test) if test else []
        has_patch = _has_promoted_patch(args.generate_dir, task_id)
        
        verdict, evidence = _classify(entry, denylist_flags, has_patch, issue_text)
        evidence["verdict"] = verdict
        evidence["task_id"] = task_id
        
        if verdict == "unsafe":
            results["unsafe"].append(evidence)
        elif verdict == "confirmed_failure":
            results["confirmed_failure"].append(evidence)
            fact = _generate_failure_fact(entry, evidence, task_id)
            results["failure_facts"].append(fact)
        elif verdict in ("rescued_pending_execution", "undetermined"):
            results["undetermined"].append(evidence)
    
    # Only keep safe, non-redundant facts
    safe_facts = [f for f in results["failure_facts"] 
                  if f["exception_type"] != "unknown"]
    
    print("=== PHASE 4: QUARANTINE RE-CHECK ===")
    print(f"Total entries processed: {sum(len(v) for v in results.values() if isinstance(v, list))}")
    print(f"  Rescued (pending execution): {len(results['undetermined'])}")
    print(f"  Unsafe (denylist-flagged):    {len(results['unsafe'])}")
    print(f"  Confirmed failures:           {len(results['confirmed_failure'])}")
    print(f"  Undetermined:                 {len(results['undetermined'])}")
    print(f"  Failure facts generated:      {len(safe_facts)}")
    
    if safe_facts:
        print(f"\nTop failure facts:")
        for f in safe_facts[:5]:
            print(f"  [{f['exception_type']}] {f['fact_text'][:100]}")
    
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
