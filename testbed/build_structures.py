"""Generate Agentless-style repo-structure JSONs from local checkouts.

Writes testbed/repo_structure/<instance_id>.json with keys
{repo, base_commit, structure, instance_id} — the format
repo_structure.preprocess_data.get_repo_structure expects under PROJECT_FILE_LOC.

Usage:
    PYTHONPATH=ExpeRepair-v1.0 python testbed/build_structures.py [--task-list FILE]
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ExpeRepair-v1.0"))

from repo_structure.get_repo_structure import create_structure  # noqa: E402

OUT_DIR = os.path.join(ROOT, "testbed", "repo_structure")
SETUP_MAP = os.path.join(ROOT, "testbed", "lite_setup_result", "setup_map.json")
TASKS_MAP = os.path.join(ROOT, "testbed", "lite_setup_result", "tasks_map.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-list", type=str, default=None)
    args = ap.parse_args()

    setup_map = json.load(open(SETUP_MAP))
    tasks_map = json.load(open(TASKS_MAP))
    if args.task_list:
        wanted = [l.strip() for l in open(args.task_list) if l.strip()]
    else:
        wanted = sorted(setup_map.keys())

    os.makedirs(OUT_DIR, exist_ok=True)
    for iid in wanted:
        out = os.path.join(OUT_DIR, f"{iid}.json")
        if os.path.exists(out):
            print("exists", iid)
            continue
        repo_path = setup_map[iid]["repo_path"]
        structure = create_structure(repo_path)
        d = {
            "repo": tasks_map[iid]["repo"],
            "base_commit": tasks_map[iid]["base_commit"],
            "structure": structure,
            "instance_id": iid,
        }
        with open(out, "w") as f:
            json.dump(d, f)
        print("wrote", iid)


if __name__ == "__main__":
    main()
