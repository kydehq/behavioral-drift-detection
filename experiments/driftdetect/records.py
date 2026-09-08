"""Boundary call records: the only input any detector is allowed to see.

The schema is provisional until the gateway ledger schema audit (AMP-134)
fixes the real field set. It deliberately contains nothing that does not
cross the system boundary: no reasoning traces, no memory contents, no
model internals (Table 2 of the survey scopes those out).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Iterable, Iterator


@dataclass(frozen=True)
class CallRecord:
    """One tool/action call crossing the system boundary."""

    ts: float                 # unix timestamp of the call
    run_id: str               # one task execution (a "run")
    agent_id: str
    model: str                # e.g. "vendor/model-name"
    model_version: str        # version string as reported on the record
    goal_id: str              # declared objective of the run (MI9-style goal conditioning)
    step_index: int           # position of the call within its run, 0-based
    tool: str                 # tool / action name
    params_hash: str          # hash of the call parameters (content never leaves the boundary)
    status: str               # "ok" | "error" | "abort"
    duration_ms: float
    meta: dict = field(default_factory=dict, compare=False)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "CallRecord":
        return cls(**json.loads(line))


def write_jsonl(records: Iterable[CallRecord], path: str) -> int:
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(rec.to_json() + "\n")
            n += 1
    return n


def read_jsonl(path: str) -> Iterator[CallRecord]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield CallRecord.from_json(line)


def group_by_run(records: Iterable[CallRecord]) -> dict[str, list[CallRecord]]:
    """Group records into runs, each sorted by step index."""
    runs: dict[str, list[CallRecord]] = {}
    for rec in records:
        runs.setdefault(rec.run_id, []).append(rec)
    for recs in runs.values():
        recs.sort(key=lambda r: r.step_index)
    return runs
