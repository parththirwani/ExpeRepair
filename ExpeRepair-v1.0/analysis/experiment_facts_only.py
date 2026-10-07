"""Offline experiment: test facts-only retrieval and prompt construction.

Reads the Phase 1 reproduce data, simulates what facts-only mode would do,
and reports metrics without running any model inference.

Usage:
    PYTHONPATH=.. python analysis/experiment_facts_only.py
"""

import json, os, sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results')

def iter_quarantined(base_dir):
    if not os.path.isdir(base_dir):
        return
    for repo in sorted(os.listdir(base_dir)):
        repo_dir = os.path.join(base_dir, repo)
        for task_id in sorted(os.listdir(repo_dir)):
            task_dir = os.path.join(repo_dir, task_id)
            qpath = os.path.join(task_dir, "quarantine.jsonl")
            if not os.path.isfile(qpath):
                continue
            with open(qpath) as f:
                for line in f:
                    entry = json.loads(line)
                    yield task_id, task_dir, entry

def main():
    repro_dir = os.path.join(results_dir, "phase1_reproduce", "django")

    # 1. Count facts available
    tasks_with_facts = 0
    total_facts = 0
    fact_exceptions = defaultdict(int)
    for task_id in sorted(os.listdir(repro_dir)):
        lpath = os.path.join(repro_dir, task_id, "lessons.jsonl")
        if os.path.isfile(lpath):
            tasks_with_facts += 1
            with open(lpath) as f:
                for line in f:
                    fact = json.loads(line)
                    total_facts += 1
                    exc = fact.get("exception_type", "unknown")
                    fact_exceptions[exc] += 1

    print("=== FACTS-ONLY EXPERIMENT (offline) ===")
    print(f"Tasks with facts: {tasks_with_facts}")
    print(f"Total facts: {total_facts}")
    print(f"Exception types: {dict(fact_exceptions)}")

    # 2. For each task with reproduce data, check what facts would be available
    #    (facts from ALL earlier tasks, respecting stream order)
    tid_to_time = {}
    for task_id in sorted(os.listdir(repro_dir)):
        epath = os.path.join(repro_dir, task_id, "reproduce_experiences.jsonl")
        if not os.path.isfile(epath):
            continue
        with open(epath) as f:
            for line in f:
                wrapper = json.loads(line)
                t = wrapper.get("time", "")
                if t:
                    tid_to_time[task_id] = t
                    break

    print(f"\nTasks in stream order: {len(tid_to_time)}")
    sorted_tids = sorted(tid_to_time.keys())
    for i, tid in enumerate(sorted_tids):
        t = tid_to_time[tid]
        lpath = os.path.join(repro_dir, tid, "lessons.jsonl")
        has_lessons = os.path.isfile(lpath)
        # Count facts available FROM earlier tasks
        prior_facts = []
        for j in range(i):
            prior_tid = sorted_tids[j]
            prior_lpath = os.path.join(repro_dir, prior_tid, "lessons.jsonl")
            if os.path.isfile(prior_lpath):
                with open(prior_lpath) as pf:
                    for pline in pf:
                        prior_facts.append(json.loads(pline))
        deduped = set()
        for f in prior_facts:
            key = f"{f.get('task_id','')}_{f.get('exception_type','unknown')}"
            deduped.add(key)
        head = f"  {tid:40s} time={t:25s} self_lessons={'Y' if has_lessons else 'N'} prior_facts={len(prior_facts):2d} (deduped={len(deduped):2d})"

        # 3. Build the prompt that would be injected
        if prior_facts:
            lines = []
            seen = set()
            for f in prior_facts:
                exc = f.get("exception_type", "unknown")
                ptid = f.get("task_id", "")
                key = f"{ptid}_{exc}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- Task {ptid}: avoid tests that raise {exc}")
            prompt = "Failure facts from previous issues:\n" + "\n".join(lines[:15])
            head += f"\n    -> prompt ({len(prompt)} chars, {len(lines[:15])} lines)"
            for l in lines[:3]:
                head += f"\n       {l}"
        print(head)

    # 4. Summary of what a facts-only pipeline would do
    print("\n=== PIPELINE SIMULATION ===")
    print("The facts-only pipeline would: ")
    print("  1. Load all prior lessons.jsonl files (deduped by task+exception)")
    print("  2. Format into a bullet list for the {summarized_rules} slot")
    print("  3. Build thread via _construct_init_thread_exp()")
    print("  4. NOT call get_experiences() — no demo retrieval")
    print("  5. Call the model once with SYSTEM_PROMPT_W_RULE + facts")

    # Model call requirement
    total_model_calls = sum(1 for tid in sorted_tids if True)
    print(f"\n  Total model calls needed for full slice: {total_model_calls}")
    print("  Blocked by: no OPENAI_KEY / CLAUDE_KEY set")

if __name__ == "__main__":
    main()
