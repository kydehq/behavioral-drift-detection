"""Synthetic test-set builder with known drift onsets.

Purpose: validate that the detectors fire on what they claim to detect, with
measurable delay and false-positive behavior. Every scenario embeds its ground
truth (drift type, onset index) in the generator output, so evaluation needs
no labels from any model.

HONESTY RULE (TODO.md): numbers measured on this synthetic data validate the
*detectors*. They must never be entered into Table 2 of the survey, which is
reserved for measurements on real operational records.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

from .records import CallRecord


# A small deployment vocabulary: two goals, distinct tool profiles.
GOAL_PROFILES: dict[str, dict[str, float]] = {
    "triage-ticket": {
        "search_kb": 0.30, "read_ticket": 0.25, "classify": 0.20,
        "draft_reply": 0.15, "submit_reply": 0.10,
    },
    "reconcile-invoice": {
        "fetch_invoice": 0.25, "fetch_po": 0.25, "compare": 0.25,
        "flag_mismatch": 0.10, "post_entry": 0.15,
    },
}

TERMINAL_TOOLS = {"triage-ticket": "submit_reply", "reconcile-invoice": "post_entry"}

# Profile after a hijack-like objective switch: mass moves to off-goal tools.
SHIFTED_PROFILE: dict[str, float] = {
    "search_kb": 0.10, "read_ticket": 0.05, "export_data": 0.40,
    "send_email": 0.35, "classify": 0.10,
}


@dataclass(frozen=True)
class Scenario:
    name: str
    drift_type: str             # "none" | "abrupt" | "gradual" | "context_decay"
                                # | "version" | "omission" | "transient" | "failure_classes"
    onset_index: Optional[int]  # stream index at which drift begins (None for "none")
    records: list[CallRecord] = field(compare=False, default_factory=list)


class Generator:
    """Deterministic (seeded) generator of boundary call record streams."""

    def __init__(self, seed: int = 7):
        self.rng = random.Random(seed)
        self._run_counter = 0
        self._ts = 1_780_000_000.0

    def _params_hash(self) -> str:
        return hashlib.sha256(str(self.rng.random()).encode()).hexdigest()[:12]

    def _draw(self, profile: dict[str, float]) -> str:
        r = self.rng.random()
        acc = 0.0
        for tool, p in profile.items():
            acc += p
            if r <= acc:
                return tool
        return next(reversed(profile))

    def _run(
        self,
        goal: str,
        profile: dict[str, float],
        length: int,
        error_prob: float = 0.02,
        model_version: str = "1.0",
        omit: frozenset = frozenset(),
        length_error_slope: float = 0.0,
        inject_violation: Optional[str] = None,
    ) -> list[CallRecord]:
        self._run_counter += 1
        run_id = f"run-{self._run_counter:05d}"
        records: list[CallRecord] = []
        excluded = set(omit)
        if inject_violation in ("false_success", "missing_progress"):
            # These violations are defined by the terminal call not happening;
            # keep the mid-run draws from producing it by accident.
            excluded.add(TERMINAL_TOOLS.get(goal, ""))
        prof = {t: p for t, p in profile.items() if t not in excluded}
        total = sum(prof.values())
        prof = {t: p / total for t, p in prof.items()}

        dup_hash = self._params_hash()
        for step in range(length):
            tool = self._draw(prof)
            ph = self._params_hash()
            if inject_violation == "duplicate_submission" and tool == TERMINAL_TOOLS.get(goal):
                ph = dup_hash
            p_err = min(0.9, error_prob + length_error_slope * step)
            status = "error" if self.rng.random() < p_err else "ok"
            self._ts += self.rng.uniform(0.5, 3.0)
            records.append(CallRecord(
                ts=self._ts, run_id=run_id, agent_id="agent-1",
                model="vendor/model-x", model_version=model_version,
                goal_id=goal, step_index=step, tool=tool, params_hash=ph,
                status=status, duration_ms=self.rng.uniform(20, 400),
            ))

        # Normal completion: terminal call at the end.
        terminal = TERMINAL_TOOLS.get(goal)
        if inject_violation == "premature_abort":
            records = records[:2]
            records[-1] = _with(records[-1], status="abort")
        elif inject_violation == "false_success":
            pass  # run ends "ok" but terminal tool is never guaranteed to appear
        elif inject_violation == "missing_progress":
            pass  # long run without terminal call; caller sets length > max_steps
        elif inject_violation == "duplicate_submission":
            self._ts += 1.0
            for k in range(3):
                records.append(CallRecord(
                    ts=self._ts + k, run_id=run_id, agent_id="agent-1",
                    model="vendor/model-x", model_version=model_version,
                    goal_id=goal, step_index=length + k, tool=terminal,
                    params_hash=dup_hash, status="ok",
                    duration_ms=self.rng.uniform(20, 400),
                ))
        elif terminal:
            self._ts += 1.0
            records.append(CallRecord(
                ts=self._ts, run_id=run_id, agent_id="agent-1",
                model="vendor/model-x", model_version=model_version,
                goal_id=goal, step_index=length, tool=terminal,
                params_hash=self._params_hash(), status="ok",
                duration_ms=self.rng.uniform(20, 400),
            ))
        return records

    def _steady(self, n_runs: int, run_length: Optional[int] = None, **kw) -> list[CallRecord]:
        out: list[CallRecord] = []
        goals = sorted(GOAL_PROFILES)
        for i in range(n_runs):
            goal = goals[i % len(goals)]
            # Varied lengths so the baseline error-rate curve covers several
            # length bins (context decay compares bin-wise against it).
            length = run_length if run_length is not None else self.rng.randint(8, 28)
            out.extend(self._run(goal, GOAL_PROFILES[goal], length, **kw))
        return out

    # -- public API ---------------------------------------------------------

    def baseline_period(self, n_runs: int = 200) -> list[CallRecord]:
        """The admission-time window the frozen baseline is built from."""
        return self._steady(n_runs)

    def scenario(self, drift_type: str, n_runs: int = 200) -> Scenario:
        """One observation period with the named drift injected halfway."""
        half = n_runs // 2
        pre = self._steady(half)
        onset = len(pre)
        goals = sorted(GOAL_PROFILES)

        if drift_type == "none":
            return Scenario("null", "none", None, pre + self._steady(n_runs - half))

        if drift_type == "abrupt":
            post: list[CallRecord] = []
            for i in range(n_runs - half):
                post.extend(self._run(goals[i % 2], SHIFTED_PROFILE, 12))
            return Scenario("abrupt-shift", "abrupt", onset, pre + post)

        if drift_type == "transient":
            burst: list[CallRecord] = []
            for i in range(10):  # short burst, then back to baseline
                burst.extend(self._run(goals[i % 2], SHIFTED_PROFILE, 12))
            return Scenario(
                "transient-shift", "transient", onset,
                pre + burst + self._steady(n_runs - half - 10),
            )

        if drift_type == "gradual":
            post = []
            steps = n_runs - half
            for i in range(steps):
                w = (i + 1) / steps
                mixed: dict[str, float] = {}
                base = GOAL_PROFILES[goals[i % 2]]
                for t in set(base) | set(SHIFTED_PROFILE):
                    mixed[t] = (1 - w) * base.get(t, 0.0) + w * SHIFTED_PROFILE.get(t, 0.0)
                post.extend(self._run(goals[i % 2], mixed, 12))
            return Scenario("gradual-shift", "gradual", onset, pre + post)

        if drift_type == "context_decay":
            post = []
            for i in range(n_runs - half):
                post.extend(self._run(
                    goals[i % 2], GOAL_PROFILES[goals[i % 2]],
                    length=30, length_error_slope=0.02,
                ))
            return Scenario("context-decay", "context_decay", onset, pre + post)

        if drift_type == "version":
            post = []
            for i in range(n_runs - half):
                post.extend(self._run(
                    goals[i % 2], SHIFTED_PROFILE, 12, model_version="2.0",
                ))
            return Scenario("version-shift", "version", onset, pre + post)

        if drift_type == "omission":
            post = []
            for i in range(n_runs - half):
                goal = goals[i % 2]
                post.extend(self._run(
                    goal, GOAL_PROFILES[goal], 12,
                    omit=frozenset({"classify", "compare"}),
                ))
            return Scenario("omission", "omission", onset, pre + post)

        if drift_type == "failure_classes":
            post = []
            kinds = ["duplicate_submission", "premature_abort", "false_success", "missing_progress"]
            for i in range(n_runs - half):
                goal = goals[i % 2]
                kind = kinds[i % 4] if i % 5 == 0 else None
                length = 250 if kind == "missing_progress" else 12
                post.extend(self._run(
                    goal, GOAL_PROFILES[goal], length, inject_violation=kind,
                ))
            return Scenario("failure-classes", "failure_classes", onset, pre + post)

        raise ValueError(f"unknown drift type: {drift_type}")


def _with(rec: CallRecord, **changes) -> CallRecord:
    from dataclasses import replace
    return replace(rec, **changes)
