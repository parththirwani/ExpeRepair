"""
Phase 1: measure label noise in ExpeRepair memory stores.

Reads reproduce_experiences.jsonl and patch_experiences.jsonl from a
Phase-0 run directory and compares each "successful" entry's LLM-judged
status against the SWE-bench oracle (FAIL_TO_PASS + PASS_TO_PASS).

Outputs:
  - stdout summary table
  - label_noise_report.json  (per-entry decisions + aggregate stats)

Usage:
    PYTHONPATH=.. python analysis/measure_label_noise.py \
        --reproduce-dir results/phase0_reproduce \
        --generate-dir results/phase0_generate \
        --tasks-map ../../testbed/lite_setup_result/tasks_map.json
"""

import argparse
import json
import os
import sys
from collections import Counter


def load_tasks_map(path: str) -> dict:
    return json.load(open(path))


def resolve_task_id(base_dir: str, subpath: str) -> str:
    """Derive the SWE-bench task ID from the directory nesting.

    The on-disk layout is:
        <base_dir>/<repo_name>/<task_id>/<experience_file>.jsonl
    Returns None if the path doesn't match.
    """
    parts = subpath.split(os.sep)
    if len(parts) >= 2:
        return parts[-2]  # dirname of the file is the task_id
    return subpath


def _iter_task_dirs(base_dir: str):
    """Yield (task_id, full_path_to_dir) for every task dir under base."""
    if not os.path.isdir(base_dir):
        return
    for repo_dir in sorted(os.listdir(base_dir)):
        repo_path = os.path.join(base_dir, repo_dir)
        if not os.path.isdir(repo_path):
            continue
        for task_id in sorted(os.listdir(repo_path)):
            yield task_id, os.path.join(repo_path, task_id)


def check_reproduce_entries(reproduce_dir: str, tasks_map: dict):
    """Score each entry's LLM-judged success against the oracle."""
    results = []
    f2p_oracle = Counter()
    if not os.path.isdir(reproduce_dir):
        print(f"WARNING: {reproduce_dir} not found")
        return results, f2p_oracle

    for task_id, task_dir in _iter_task_dirs(reproduce_dir):
        exp_path = os.path.join(task_dir, "reproduce_experiences.jsonl")
        if not os.path.exists(exp_path):
            continue

        oracle_f2p = set(tasks_map.get(task_id, {}).get("FAIL_TO_PASS", []))
        oracle_p2p = set(tasks_map.get(task_id, {}).get("PASS_TO_PASS", []))

        for line in open(exp_path):
            entry = json.loads(line)
            for exp in entry.get("exps", []):
                repro_judge = exp.get("new_check_repro", {})
                if isinstance(repro_judge, dict):
                    llm_yes = repro_judge.get("if-reproduce", "") == "YES"
                else:
                    llm_yes = False

                has_oracle = len(oracle_f2p) > 0 or len(oracle_p2p) > 0

                if llm_yes and has_oracle:
                    category = "TP"
                elif llm_yes and not has_oracle:
                    category = "FP_NO_ORACLE"
                elif not llm_yes and has_oracle:
                    category = "FN"
                else:
                    category = "TN_ORACLE_LESS"

                results.append({
                    "task_id": task_id,
                    "store": "reproduce",
                    "llm_judged_yes": llm_yes,
                    "oracle_has_F2P": len(oracle_f2p) > 0,
                    "oracle_F2P_count": len(oracle_f2p),
                    "oracle_P2P_count": len(oracle_p2p),
                    "category": category,
                })

    return results, f2p_oracle


def check_patch_entries(generate_dir: str, tasks_map: dict):
    """Score each patch experience entry's new_result against the oracle."""
    results = []
    if not os.path.isdir(generate_dir):
        print(f"WARNING: {generate_dir} not found")
        return results

    for task_id, task_dir in _iter_task_dirs(generate_dir):
        exp_path = os.path.join(task_dir, "patch_experiences.jsonl")
        if not os.path.exists(exp_path):
            continue

        oracle_f2p = set(tasks_map.get(task_id, {}).get("FAIL_TO_PASS", []))
        oracle_p2p = set(tasks_map.get(task_id, {}).get("PASS_TO_PASS", []))

        for line in open(exp_path):
            entry = json.loads(line)
            for exp in entry.get("exps", []):
                new_result = exp.get("new_result", False)
                has_oracle = len(oracle_f2p) > 0

                if new_result and has_oracle:
                    category = "TP"
                elif new_result and not has_oracle:
                    category = "FP_NO_ORACLE"
                elif not new_result and has_oracle:
                    category = "FN"
                else:
                    category = "TN_ORACLE_LESS"

                results.append({
                    "task_id": task_id,
                    "store": "patch",
                    "llm_judged_yes": bool(new_result),
                    "oracle_has_F2P": len(oracle_f2p) > 0,
                    "oracle_F2P_count": len(oracle_f2p),
                    "oracle_P2P_count": len(oracle_p2p),
                    "category": category,
                })

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reproduce-dir", type=str, default="results/phase0_reproduce")
    ap.add_argument("--generate-dir", type=str, default="results/phase0_generate")
    ap.add_argument(
        "--tasks-map",
        type=str,
        default="/home/too_geeky/projects/research/ExpeRepair/testbed/lite_setup_result/tasks_map.json",
    )
    args = ap.parse_args()

    tasks_map = load_tasks_map(args.tasks_map)

    repro_results, _ = check_reproduce_entries(args.reproduce_dir, tasks_map)
    patch_results = check_patch_entries(args.generate_dir, tasks_map)

    all_results = repro_results + patch_results

    if not all_results:
        print("\nNo results found. Check that reproduce/generate dirs exist.")
        return

    # Aggregate
    cat_counts = Counter(r["category"] for r in all_results)
    store_counts = Counter(r["store"] for r in all_results)
    print(f"\n{'='*60}")
    print(f"LABEL NOISE REPORT (Phase 1)")
    print(f"{'='*60}")
    print(f"\nTotal entries scored:  {len(all_results)}")
    print(f"  Reproduce entries:   {store_counts.get('reproduce', 0)}")
    print(f"  Patch entries:       {store_counts.get('patch', 0)}")
    print(f"\nCategory breakdown:")
    print(f"  TP (plausibly correct):       {cat_counts.get('TP', 0)}")
    print(f"  FP_NO_ORACLE (label noise):   {cat_counts.get('FP_NO_ORACLE', 0)}")
    print(f"  FN (missed):                  {cat_counts.get('FN', 0)}")
    print(f"  TN/ORACLE_LESS:               {cat_counts.get('TN_ORACLE_LESS', 0)}")
    total_labeled = cat_counts.get("TP", 0) + cat_counts.get("FP_NO_ORACLE", 0) + cat_counts.get("FN", 0)
    if total_labeled > 0:
        noise = cat_counts.get("FP_NO_ORACLE", 0) / total_labeled
        print(f"\nFalse positive rate among scored entries: {noise:.1%}")
        print(f"  (scored = TP + FP + FN = {total_labeled})")

    print(f"\nPer-task detail (reproduce):")
    for r in repro_results:
        print(f"  {r['task_id']:40s} {r['category']:20s}  oracle_F2P={r['oracle_F2P_count']}")

    print(f"\nPer-task detail (patch):")
    for r in patch_results:
        print(f"  {r['task_id']:40s} {r['category']:20s}  oracle_F2P={r['oracle_F2P_count']}")

    report = {
        "total_entries": len(all_results),
        "category_counts": dict(cat_counts),
        "entries": all_results,
    }
    out_path = "label_noise_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()