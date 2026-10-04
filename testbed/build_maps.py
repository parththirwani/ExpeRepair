"""Build setup_map.json / tasks_map.json for the ExpeRepair dev slice.

Usage:
    python testbed/build_maps.py [--n N] [--repo django/django]

Reads the SWE-bench Lite parquet, takes the first N issues of the repo in
chronological (created_at) order, and writes:
    testbed/lite_setup_result/setup_map.json
    testbed/lite_setup_result/tasks_map.json
    testbed/lite_setup_result/task_list_<repo>_<n>.txt   (chronological order)

Per-instance repo checkouts live at:
    testbed/lite_testbed/<repo_combo>/setup_<instance_id>/
(one dir per instance, following the ACR layout seen in results fixtures)
"""

import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.expanduser("~/.pyenv/versions/3.12.9/lib/python3.12/site-packages"))
from swebench.harness.constants import (
    MAP_REPO_TO_TEST_FRAMEWORK,
    MAP_VERSION_TO_INSTALL_DJANGO,
)
from swebench.harness.utils import get_test_directives

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARQUET = os.path.join(ROOT, "data", "SWE-bench_Lite", "data", "test-00000-of-00001.parquet")
OUT_DIR = os.path.join(ROOT, "testbed", "lite_setup_result")
TESTBED = os.path.join(ROOT, "testbed", "lite_testbed")

VERSION_TO_SPEC = {
    "django/django": MAP_VERSION_TO_INSTALL_DJANGO,
}


def env_name_for(repo: str, version: str) -> str:
    spec = VERSION_TO_SPEC[repo][version]
    py = spec["python"].replace(".", "")
    combo = repo.replace("/", "-")
    return f"exprepair-{combo}-py{py}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=22)
    ap.add_argument("--repo", type=str, default="django/django")
    args = ap.parse_args()

    df = pd.read_parquet(PARQUET)
    d = df[df.repo == args.repo].sort_values("created_at").reset_index(drop=True)
    sl = d.head(args.n)
    print(f"repo={args.repo} total={len(d)} slice={len(sl)}")
    print("versions:", sl.version.value_counts().to_dict())

    combo = args.repo.replace("/", "__")
    setup_map, tasks_map, task_ids = {}, {}, []
    for _, row in sl.iterrows():
        iid = row["instance_id"]
        task_ids.append(iid)
        spec = VERSION_TO_SPEC[args.repo][row["version"]]
        directives = get_test_directives(row.to_dict())
        test_cmd = MAP_REPO_TO_TEST_FRAMEWORK[args.repo]
        if directives:
            test_cmd = f"{test_cmd} {' '.join(directives)}"
        setup_map[iid] = {
            "repo_path": os.path.join(TESTBED, combo, f"setup_{iid}"),
            "env_name": env_name_for(args.repo, row["version"]),
            "pre_install": [],
            "install": spec["install"],
            "test_cmd": test_cmd,
        }
        tasks_map[iid] = {
            "base_commit": row["base_commit"],
            "hints_text": row.get("hints_text", ""),
            "created_at": row["created_at"],
            "test_patch": row["test_patch"],
            "repo": row["repo"],
            "problem_statement": row["problem_statement"],
            "version": row["version"],
            "instance_id": iid,
            "FAIL_TO_PASS": list(row["FAIL_TO_PASS"]),
            "PASS_TO_PASS": list(row["PASS_TO_PASS"]),
            "environment_setup_commit": row["environment_setup_commit"],
            "patch": row["patch"],
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "setup_map.json"), "w") as f:
        json.dump(setup_map, f, indent=2)
    with open(os.path.join(OUT_DIR, "tasks_map.json"), "w") as f:
        json.dump(tasks_map, f, indent=2)
    list_file = os.path.join(OUT_DIR, f"task_list_{combo}_{len(sl)}.txt")
    with open(list_file, "w") as f:
        f.write("\n".join(task_ids) + "\n")
    print("wrote:", OUT_DIR)
    print("envs needed:", sorted({s["env_name"] for s in setup_map.values()}))
    print("first:", task_ids[0], "| last:", task_ids[-1])


if __name__ == "__main__":
    main()
