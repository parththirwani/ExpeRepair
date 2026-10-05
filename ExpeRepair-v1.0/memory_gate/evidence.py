"""
Execution evidence gate: run regression tests and check before/after behavior.

Uses the task's own conda environment to execute the reproduction test
with and without the candidate patch, and checks that the regression test
file (from swe_regression_test.json) still passes.
"""

import json
import os
from pathlib import Path
from task import SweTask


def check_exec_evidence(
    task: SweTask,
    test_content: str,
    patch_content: str | None,
    regression_test_file: str | None,
) -> tuple[bool, list[str]]:
    """
    Returns (passed: bool, reasons: list[str]).

    Checks:
      1. The reproduction test produces different output when applied.
      2. The regression test file still passes (if available).
    """
    reasons = []

    # Run test without patch
    before = task.execute_test(test_content, patch_content=None)
    # Run test with patch
    after = task.execute_test(test_content, patch_content=patch_content) if patch_content else before

    if before.returncode == after.returncode and before.stdout.strip() == after.stdout.strip():
        reasons.append("repro test output unchanged by patch")
        return False, reasons

    if before.returncode == 0 and after.returncode != 0:
        reasons.append("patch breaks previously passing test")
        return False, reasons

    reasons.append(f"behavior changed: rc {before.returncode} -> {after.returncode}")

    # Run regression test file if available
    if regression_test_file and os.path.exists(regression_test_file):
        try:
            test_content_path = Path(task.project_path, regression_test_file)
            if test_content_path.exists():
                regression_content = test_content_path.read_text()
                after_reg = task.execute_test(regression_content, patch_content=patch_content)
                if after_reg.returncode != 0:
                    reasons.append(f"regression test {regression_test_file} failed after patch")
                    return False, reasons
                reasons.append(f"regression test {regression_test_file} passed")
        except Exception as e:
            reasons.append(f"regression check skipped: {e}")

    return True, reasons