"""Re-process existing Phase 1/Phase 0 experience files through the fixed gate.

Reads reproduce_experiences.jsonl and patch_experiences.jsonl,
runs the gate (with the current fixed logic), writes promoted.jsonl
and quarantine.jsonl alongside all.jsonl.

Usage:
    PYTHONPATH=.. python analysis/backfill_gate.py \
        --reproduce-dir results/phase1_reproduce \
        --generate-dir results/phase1_generate
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from memory_gate.gate import MemoryGateMode, gate_candidate
from memory_gate.store import promote, quarantine


def _iter_experience_files(base_dir: str, exp_filename: str):
    """Yield (task_id, task_dir, issue_text, entry_dict_list)."""
    if not os.path.isdir(base_dir):
        return
    for repo_dir in sorted(os.listdir(base_dir)):
        repo_path = os.path.join(base_dir, repo_dir)
        if not os.path.isdir(repo_path):
            continue
        for task_id in sorted(os.listdir(repo_path)):
            task_dir = os.path.join(repo_path, task_id)
            exp_path = os.path.join(task_dir, exp_filename)
            if not os.path.exists(exp_path):
                continue
            for line in open(exp_path):
                entry = json.loads(line)
                issue_text = entry.get("issue_description", "")
                exps = entry.get("exps", [])
                yield task_id, task_dir, issue_text, exps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reproduce-dir", type=str, required=True)
    ap.add_argument("--generate-dir", type=str, required=True)
    args = ap.parse_args()

    config.memory_mode = "gated"

    total_promoted = 0
    total_quarantined = 0

    # Reproduce experiences
    for task_id, task_dir, issue_text, exps in _iter_experience_files(
        args.reproduce_dir, "reproduce_experiences.jsonl"
    ):
        for exp in exps:
            result = gate_candidate(
                entry=exp,
                issue_text=issue_text,
                task_dir=task_dir,
            )
            if result.promoted:
                total_promoted += 1
            else:
                total_quarantined += 1

    # Patch experiences (generate dir)
    for task_id, task_dir, issue_text, exps in _iter_experience_files(
        args.generate_dir, "patch_experiences.jsonl"
    ):
        for exp in exps:
            result = gate_candidate(
                entry=exp,
                issue_text=issue_text,
                task_dir=task_dir,
            )
            if result.promoted:
                total_promoted += 1
            else:
                total_quarantined += 1

    # Tally by store
    print(f"\n{'='*60}")
    print(f"GATE BACKFILL RESULTS (gated mode)")
    print(f"{'='*60}")
    print(f"Total promoted:    {total_promoted}")
    print(f"Total quarantined: {total_quarantined}")
    if total_promoted + total_quarantined > 0:
        print(f"Promoted fraction: {total_promoted / (total_promoted + total_quarantined):.1%}")
    print()

    # Per-task detail
    for store, base_dir, exp_name in [
        ("reproduce", args.reproduce_dir, "reproduce_experiences.jsonl"),
        ("patch", args.generate_dir, "patch_experiences.jsonl"),
    ]:
        print(f"\n--- {store} ---")
        for task_id, task_dir, issue_text, exps in _iter_experience_files(base_dir, exp_name):
            prom_path = os.path.join(task_dir, "promoted.jsonl")
            n = sum(1 for _ in open(prom_path)) if os.path.exists(prom_path) else 0
            print(f"  {task_id:40s} promoted={n}")


if __name__ == "__main__":
    main()