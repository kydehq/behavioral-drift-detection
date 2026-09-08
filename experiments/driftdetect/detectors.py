"""Deterministic drift detectors over boundary call records.

Every detector in this module is a pure function of (frozen baseline, record
stream) — no model calls, no randomness, no wall clock. Same log, same score.

The set follows the survey directly:

- Two-regime distributional detector (Section 5): a windowed Jensen-Shannon
  divergence channel with EMA smoothing for gradual drift ("creep"), and a
  CUSUM change-point channel on per-event surprisal for abrupt shifts
  ("jump", the injection-like regime). Both run against the same frozen
  baseline.
- Context decay (Table 2): abort/error rate as a function of run length,
  compared bin-wise against the baseline curve.
- Version drift (Table 2): segmentation on the model/version fields plus
  divergence between adjacent segments.
- Omission (Arike et al.): expected calls that stop appearing, per goal.
- Goal-persistence failure classes (Section 4): countable per-run predicates —
  duplicate submission, premature abort, false success claim, missing progress.
- Persistence classifier: distinguishes a durable distribution shift
  (persistent drift, type 6) from a transient one, by whether the divergence
  channel recovers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .baseline import FrozenBaseline, length_bin, tool_distribution
from .records import CallRecord, group_by_run


# ---------------------------------------------------------------------------
# Divergence primitives
# ---------------------------------------------------------------------------

def kl_divergence(p: dict[str, float], q: dict[str, float], eps: float = 1e-9) -> float:
    """KL(p || q) in bits over the union vocabulary, with epsilon smoothing."""
    vocab = set(p) | set(q)
    return sum(
        p.get(t, 0.0) * math.log2((p.get(t, 0.0) + eps) / (q.get(t, 0.0) + eps))
        for t in vocab
        if p.get(t, 0.0) > 0.0
    )


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence in bits; bounded in [0, 1]."""
    vocab = set(p) | set(q)
    m = {t: 0.5 * (p.get(t, 0.0) + q.get(t, 0.0)) for t in vocab}
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


# ---------------------------------------------------------------------------
# Channel 1: windowed divergence with EMA smoothing (the creep regime)
# ---------------------------------------------------------------------------

@dataclass
class DivergenceChannel:
    """Sliding-window JSD against a frozen baseline, exponentially smoothed.

    Answers: "has behavior wandered over weeks?" A low-pass filter by
    construction — tuned for creep, deliberately slow on jumps (Section 5).
    """

    baseline: FrozenBaseline
    window: int = 50            # rolling window size (Rath 2026 uses 50)
    alpha: float = 0.1          # EMA smoothing factor
    threshold: float = 0.15     # alarm when smoothed JSD exceeds this
    patience: int = 5           # ... for this many consecutive events

    _buf: list[str] = field(default_factory=list)
    _ema: Optional[float] = None
    _over: int = 0

    def update(self, rec: CallRecord) -> Optional[float]:
        """Feed one record; returns the smoothed score once the window is full."""
        self._buf.append(rec.tool)
        if len(self._buf) > self.window:
            self._buf.pop(0)
        if len(self._buf) < self.window:
            return None
        counts: dict[str, int] = {}
        for t in self._buf:
            counts[t] = counts.get(t, 0) + 1
        dist = {t: c / len(self._buf) for t, c in counts.items()}
        score = js_divergence(dist, self.baseline.tool_dist)
        self._ema = score if self._ema is None else (
            self.alpha * score + (1 - self.alpha) * self._ema
        )
        self._over = self._over + 1 if self._ema > self.threshold else 0
        return self._ema

    @property
    def alarmed(self) -> bool:
        return self._over >= self.patience


# ---------------------------------------------------------------------------
# Channel 2: CUSUM on per-event surprisal (the jump regime)
# ---------------------------------------------------------------------------

@dataclass
class CusumChannel:
    """One-sided CUSUM over per-event surprisal under the frozen baseline.

    Surprisal of event t is -log2 P_baseline(tool_t). Under no drift its mean
    is the baseline entropy; a sudden switch of effective objective (in-session
    injection, Section 2.3) raises it as a step change. CUSUM accumulates
    excess over (mean + slack) and alarms past a threshold — equally cheap and
    deterministic, better at jumps than at slow deviation.
    """

    baseline: FrozenBaseline
    slack: float = 0.5          # k: tolerated excess surprisal in bits
    threshold: float = 8.0      # h: alarm level in accumulated bits
    floor_prob: float = 1e-4    # probability assigned to tools unseen at baseline

    _mean: float = field(init=False)
    _stat: float = 0.0
    _alarmed: bool = False

    def __post_init__(self) -> None:
        # baseline entropy = expected surprisal under no drift
        self._mean = -sum(
            p * math.log2(p) for p in self.baseline.tool_dist.values() if p > 0
        )

    def update(self, rec: CallRecord) -> float:
        p = self.baseline.tool_dist.get(rec.tool, self.floor_prob)
        surprisal = -math.log2(p)
        self._stat = max(0.0, self._stat + surprisal - self._mean - self.slack)
        if self._stat > self.threshold:
            self._alarmed = True
        return self._stat

    @property
    def alarmed(self) -> bool:
        return self._alarmed


# ---------------------------------------------------------------------------
# The two-regime detector (Section 5's deployment recommendation)
# ---------------------------------------------------------------------------

@dataclass
class Alarm:
    channel: str        # "divergence" | "cusum"
    event_index: int    # index into the record stream at which the alarm fired
    score: float


def run_two_regime(
    records: Iterable[CallRecord],
    baseline: FrozenBaseline,
    divergence: Optional[DivergenceChannel] = None,
    cusum: Optional[CusumChannel] = None,
) -> list[Alarm]:
    """Run both channels over one stream; returns first alarm per channel."""
    div = divergence or DivergenceChannel(baseline)
    cus = cusum or CusumChannel(baseline)
    alarms: list[Alarm] = []
    div_fired = cus_fired = False
    for i, rec in enumerate(records):
        score = div.update(rec)
        stat = cus.update(rec)
        if not div_fired and div.alarmed:
            alarms.append(Alarm("divergence", i, score if score is not None else 0.0))
            div_fired = True
        if not cus_fired and cus.alarmed:
            alarms.append(Alarm("cusum", i, stat))
            cus_fired = True
    return alarms


# ---------------------------------------------------------------------------
# Context decay: error/abort rate as a function of run length (Table 2: cheap)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BinFinding:
    bin: int            # length bin (steps // LENGTH_BIN_WIDTH)
    baseline_rate: float
    observed_rate: float
    z: float            # two-proportion z statistic
    n_observed: int


def detect_context_decay(
    records: list[CallRecord],
    baseline: FrozenBaseline,
    z_threshold: float = 3.0,
    min_calls: int = 30,
) -> list[BinFinding]:
    """Compare the per-length-bin error/abort rate against the baseline curve.

    Flags bins where the observed rate is significantly above baseline. Context
    decay shows up as flagged bins concentrated at high length bins; a uniform
    lift across all bins is general degradation, not decay.
    """
    obs: dict[int, list[int]] = {}
    for rec in records:
        b = length_bin(rec.step_index)
        obs.setdefault(b, [0, 0])
        obs[b][1] += 1
        if rec.status in ("error", "abort"):
            obs[b][0] += 1

    findings = []
    for b, (e, n) in sorted(obs.items()):
        if n < min_calls or b not in baseline.error_rate_by_length_bin:
            continue
        be, bn = baseline.error_rate_by_length_bin[b]
        p_obs, p_base = e / n, be / bn
        p_pool = (e + be) / (n + bn)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n + 1 / bn)) or 1e-12
        z = (p_obs - p_base) / se
        if z > z_threshold:
            findings.append(BinFinding(b, p_base, p_obs, z, n))
    return findings


# ---------------------------------------------------------------------------
# Version drift: segmentation on record fields (Table 2: cheapest)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VersionShift:
    from_version: tuple[str, str]   # (model, model_version)
    to_version: tuple[str, str]
    boundary_index: int             # stream index of the first record of the new version
    jsd: float                      # divergence between the two segments' tool distributions


def detect_version_drift(
    records: list[CallRecord],
    jsd_threshold: float = 0.05,
    min_segment: int = 50,
) -> list[VersionShift]:
    """Segment the stream on (model, model_version); compare adjacent segments.

    The version change itself is read off the record — no statistics needed.
    The JSD quantifies whether behavior moved with it (reassessment trigger).
    """
    segments: list[tuple[tuple[str, str], int, list[CallRecord]]] = []
    for i, rec in enumerate(records):
        key = (rec.model, rec.model_version)
        if not segments or segments[-1][0] != key:
            segments.append((key, i, []))
        segments[-1][2].append(rec)

    shifts = []
    for (ka, _, seg_a), (kb, start_b, seg_b) in zip(segments, segments[1:]):
        if len(seg_a) < min_segment or len(seg_b) < min_segment:
            continue
        d = js_divergence(tool_distribution(seg_a), tool_distribution(seg_b))
        if d >= jsd_threshold:
            shifts.append(VersionShift(ka, kb, start_b, d))
    return shifts


# ---------------------------------------------------------------------------
# Omission: expected calls that stop appearing (the strongest log signal)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OmissionFinding:
    goal_id: str
    tool: str
    baseline_presence: float    # fraction of baseline runs containing the tool (>= min_support)
    observed_presence: float    # fraction of observed runs containing it
    n_runs: int


def detect_omission(
    records: list[CallRecord],
    baseline: FrozenBaseline,
    presence_drop: float = 0.5,
    min_runs: int = 10,
) -> list[OmissionFinding]:
    """Per goal, find expected tools whose per-run presence collapsed.

    Arike et al.: omission consistently exceeds commission — the absence of
    expected calls is a stronger drift signal than the presence of wrong ones.
    """
    runs = group_by_run(records)
    presence: dict[str, dict[str, int]] = {}
    runs_per_goal: dict[str, int] = {}
    for run in runs.values():
        goal = run[0].goal_id
        runs_per_goal[goal] = runs_per_goal.get(goal, 0) + 1
        for tool in {r.tool for r in run}:
            presence.setdefault(goal, {}).setdefault(tool, 0)
            presence[goal][tool] += 1

    findings = []
    for goal, expected in sorted(baseline.expected_tools_by_goal.items()):
        n = runs_per_goal.get(goal, 0)
        if n < min_runs:
            continue
        for tool in sorted(expected):
            obs = presence.get(goal, {}).get(tool, 0) / n
            if obs < presence_drop:
                findings.append(OmissionFinding(goal, tool, 1.0, obs, n))
    return findings


# ---------------------------------------------------------------------------
# Goal-persistence failure classes: countable per-run predicates (Section 4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GoalSpec:
    """Minimal per-goal contract the operator declares at admission time."""

    goal_id: str
    terminal_tool: str          # the call that constitutes completing the task
    min_steps: int = 3          # fewer than this before ending = premature abort
    max_steps: int = 200        # more than this without the terminal call = missing progress
    max_duplicate_calls: int = 1  # identical (tool, params_hash) repeats allowed


@dataclass(frozen=True)
class RunViolation:
    run_id: str
    goal_id: str
    kind: str   # "duplicate_submission" | "premature_abort" | "false_success" | "missing_progress"
    detail: str


def check_goal_persistence(
    records: list[CallRecord],
    specs: dict[str, GoalSpec],
) -> list[RunViolation]:
    """Evaluate the four countable failure classes per completed run."""
    violations = []
    for run_id, run in sorted(group_by_run(records).items()):
        goal = run[0].goal_id
        spec = specs.get(goal)
        if spec is None:
            continue

        counts: dict[tuple[str, str], int] = {}
        for rec in run:
            key = (rec.tool, rec.params_hash)
            counts[key] = counts.get(key, 0) + 1
        for (tool, ph), c in sorted(counts.items()):
            if c > spec.max_duplicate_calls:
                violations.append(RunViolation(
                    run_id, goal, "duplicate_submission",
                    f"{tool} with identical params called {c}x",
                ))

        last = run[-1]
        terminal_called = any(r.tool == spec.terminal_tool and r.status == "ok" for r in run)

        if last.status == "abort" and len(run) < spec.min_steps:
            violations.append(RunViolation(
                run_id, goal, "premature_abort",
                f"aborted after {len(run)} steps (min {spec.min_steps})",
            ))
        if last.status == "ok" and not terminal_called:
            violations.append(RunViolation(
                run_id, goal, "false_success",
                f"run ended ok but terminal tool '{spec.terminal_tool}' never succeeded",
            ))
        if len(run) > spec.max_steps and not terminal_called:
            violations.append(RunViolation(
                run_id, goal, "missing_progress",
                f"{len(run)} steps without terminal tool '{spec.terminal_tool}'",
            ))
    return violations


# ---------------------------------------------------------------------------
# Persistence: durable vs. transient distribution shift (type 6, indirect)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PersistenceVerdict:
    shifted: bool           # did the divergence channel ever alarm?
    persistent: bool        # ... and was it still elevated at the end of the stream?
    first_alarm_index: Optional[int]
    final_score: Optional[float]


def classify_persistence(
    records: list[CallRecord],
    baseline: FrozenBaseline,
    channel: Optional[DivergenceChannel] = None,
) -> PersistenceVerdict:
    """A shift that the smoothed divergence never recovers from is persistent
    drift in the Table 2 sense (an incident converted into a state); a shift
    that reverts below threshold is transient."""
    ch = channel or DivergenceChannel(baseline)
    first_alarm = None
    score = None
    for i, rec in enumerate(records):
        score = ch.update(rec)
        if first_alarm is None and ch.alarmed:
            first_alarm = i
    still_elevated = score is not None and score > ch.threshold
    return PersistenceVerdict(
        shifted=first_alarm is not None,
        persistent=first_alarm is not None and still_elevated,
        first_alarm_index=first_alarm,
        final_score=score,
    )
