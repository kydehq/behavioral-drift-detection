"""Deterministic behavioral-drift detection from boundary call records.

Companion code to the survey draft in ../paper. Stdlib-only, so every verdict
is reproducible by a third party from the record alone: same log, same score.
"""

from .records import CallRecord, read_jsonl, write_jsonl, group_by_run
from .baseline import FrozenBaseline, freeze_baseline, tool_distribution
from .detectors import (
    Alarm,
    CusumChannel,
    DivergenceChannel,
    GoalSpec,
    check_goal_persistence,
    classify_persistence,
    detect_context_decay,
    detect_omission,
    detect_version_drift,
    js_divergence,
    kl_divergence,
    run_two_regime,
)

__all__ = [name for name in dir() if not name.startswith("_")]
