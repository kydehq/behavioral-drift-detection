"""Frozen baselines.

The survey's design lesson (Fernandez 2026): the reference must be frozen at
admission time, because rolling baselines let a drifting system become its own
reference ("reference contamination"). A baseline here is a plain snapshot of
tool-usage statistics over a fixed record window, hashable so that a third
party can verify which baseline a verdict was computed against.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable

from .records import CallRecord, group_by_run


def tool_distribution(records: Iterable[CallRecord]) -> dict[str, float]:
    counts: dict[str, int] = {}
    total = 0
    for rec in records:
        counts[rec.tool] = counts.get(rec.tool, 0) + 1
        total += 1
    if total == 0:
        return {}
    return {tool: c / total for tool, c in sorted(counts.items())}


@dataclass(frozen=True)
class FrozenBaseline:
    """Admission-time snapshot of boundary behavior."""

    tool_dist: dict[str, float]                    # overall tool distribution
    tool_dist_by_goal: dict[str, dict[str, float]]  # goal-conditioned (MI9)
    expected_tools_by_goal: dict[str, frozenset]    # tools present in >= min_support of baseline runs
    error_rate_by_length_bin: dict[int, tuple[int, int]]  # bin -> (errors_or_aborts, calls)
    n_records: int
    n_runs: int

    def fingerprint(self) -> str:
        """Deterministic hash so a verdict can name its exact reference."""
        payload = json.dumps(
            {
                "tool_dist": self.tool_dist,
                "tool_dist_by_goal": self.tool_dist_by_goal,
                "expected_tools_by_goal": {
                    g: sorted(t) for g, t in sorted(self.expected_tools_by_goal.items())
                },
                "error_rate_by_length_bin": {
                    str(k): v for k, v in sorted(self.error_rate_by_length_bin.items())
                },
                "n_records": self.n_records,
                "n_runs": self.n_runs,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


LENGTH_BIN_WIDTH = 10  # runs are binned by step count in bins of this width


def length_bin(step_index: int) -> int:
    return step_index // LENGTH_BIN_WIDTH


def freeze_baseline(records: list[CallRecord], min_support: float = 0.8) -> FrozenBaseline:
    """Build a frozen baseline from an admission-time record window.

    min_support: a tool counts as "expected" for a goal if it appears in at
    least this fraction of the goal's baseline runs (omission detection).
    """
    runs = group_by_run(records)

    by_goal: dict[str, list[CallRecord]] = {}
    tool_presence: dict[str, dict[str, int]] = {}  # goal -> tool -> runs containing it
    runs_per_goal: dict[str, int] = {}
    err_by_bin: dict[int, list[int]] = {}

    for run in runs.values():
        goal = run[0].goal_id
        runs_per_goal[goal] = runs_per_goal.get(goal, 0) + 1
        seen = set()
        for rec in run:
            by_goal.setdefault(goal, []).append(rec)
            seen.add(rec.tool)
            b = length_bin(rec.step_index)
            err_by_bin.setdefault(b, [0, 0])
            err_by_bin[b][1] += 1
            if rec.status in ("error", "abort"):
                err_by_bin[b][0] += 1
        for tool in seen:
            tool_presence.setdefault(goal, {}).setdefault(tool, 0)
            tool_presence[goal][tool] += 1

    expected = {
        goal: frozenset(
            tool
            for tool, n in tools.items()
            if n / runs_per_goal[goal] >= min_support
        )
        for goal, tools in tool_presence.items()
    }

    return FrozenBaseline(
        tool_dist=tool_distribution(records),
        tool_dist_by_goal={g: tool_distribution(rs) for g, rs in sorted(by_goal.items())},
        expected_tools_by_goal=expected,
        error_rate_by_length_bin={b: (e, n) for b, (e, n) in sorted(err_by_bin.items())},
        n_records=len(records),
        n_runs=len(runs),
    )
