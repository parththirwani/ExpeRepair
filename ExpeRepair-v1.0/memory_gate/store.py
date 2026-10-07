"""
Tiered JSONL store for the memory gate.

Three tiers per task directory:
  - all.jsonl: every candidate with provenance fields and gate decision (audit log).
  - promoted.jsonl: candidates that passed the gate (only file read paths may load).
  - quarantine.jsonl: candidates rejected by the gate with the reason.
"""

import json
import os
from pathlib import Path
from typing import Any

_COUNTERS: dict[str, int] = {}


def _next_seq(task_dir: str) -> int:
    _COUNTERS[task_dir] = _COUNTERS.get(task_dir, 0) + 1
    return _COUNTERS[task_dir]


def _ensure_store_dir(task_dir: str, tier: str) -> Path:
    p = Path(task_dir, tier)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append_entry(task_dir: str, tier: str, entry: dict[str, Any]):
    path = _ensure_store_dir(task_dir, tier)
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def load_tier(task_dir: str, tier: str) -> list[dict[str, Any]]:
    path = Path(task_dir, tier)
    if not path.exists():
        return []
    return [json.loads(line) for line in open(path)]


def promote(entry: dict[str, Any], task_dir: str, reasons: list[str]):
    entry["gate_decision"] = "promoted"
    entry["gate_reasons"] = reasons
    entry["gate_seq"] = _next_seq(task_dir)
    append_entry(task_dir, "all.jsonl", entry)
    gate_entry = {k: v for k, v in entry.items() if k != "gate_reasons"}
    gate_entry["gate_decision"] = "promoted"
    gate_entry["gate_seq"] = entry["gate_seq"]
    append_entry(task_dir, "promoted.jsonl", gate_entry)


def quarantine(entry: dict[str, Any], task_dir: str, reasons: list[str]):
    entry["gate_decision"] = "quarantined"
    entry["gate_reasons"] = reasons
    entry["gate_seq"] = _next_seq(task_dir)
    append_entry(task_dir, "all.jsonl", entry)
    quarantine_entry = {k: v for k, v in entry.items() if k != "gate_reasons"}
    quarantine_entry["gate_decision"] = "quarantined"
    quarantine_entry["gate_reasons"] = reasons
    quarantine_entry["gate_seq"] = entry["gate_seq"]
    append_entry(task_dir, "quarantine.jsonl", quarantine_entry)