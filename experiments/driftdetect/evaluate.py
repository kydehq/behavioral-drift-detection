"""Evaluation harness: detectors vs. the synthetic test set.

Measures, per drift type and across independently seeded trials:
- detection rate (fraction of trials in which the responsible detector fired),
- detection delay (boundary events between drift onset and first alarm),
- false-positive rate (alarms on the drift-free scenario).

Usage:
    python -m driftdetect.evaluate [--trials 5] [--runs 200] [--seed 7] [--out PATH]

SYNTHETIC VALIDATION ONLY. These numbers demonstrate that the detectors fire
on what they claim to detect. They are not detection performance on real
operational records and must never be entered into Table 2 of the survey.
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass, field

from .baseline import freeze_baseline
from .detectors import (
    CusumChannel,
    DivergenceChannel,
    check_goal_persistence,
    classify_persistence,
    detect_context_decay,
    detect_omission,
    detect_version_drift,
    GoalSpec,
    run_two_regime,
)
from .testset import Generator, TERMINAL_TOOLS


SPECS = {
    goal: GoalSpec(goal_id=goal, terminal_tool=terminal, min_steps=3, max_steps=200)
    for goal, terminal in TERMINAL_TOOLS.items()
}

DRIFT_TYPES = [
    "none", "abrupt", "gradual", "transient",
    "context_decay", "version", "omission", "failure_classes",
]


@dataclass
class TrialResult:
    drift_type: str
    detected: bool
    delay: int | None           # events from onset to first responsible alarm
    detail: str = ""


@dataclass
class Summary:
    trials: list[TrialResult] = field(default_factory=list)

    def add(self, r: TrialResult) -> None:
        self.trials.append(r)

    def rate(self) -> float:
        return sum(t.detected for t in self.trials) / len(self.trials)

    def median_delay(self) -> int | None:
        delays = [t.delay for t in self.trials if t.delay is not None]
        return int(statistics.median(delays)) if delays else None


def run_trial(drift_type: str, seed: int, n_runs: int) -> TrialResult:
    gen = Generator(seed=seed)
    baseline = freeze_baseline(gen.baseline_period(n_runs))
    scenario = gen.scenario(drift_type, n_runs)
    records = scenario.records
    onset = scenario.onset_index
    post = records[onset:] if onset is not None else records[len(records) // 2:]

    alarms = run_two_regime(records, baseline)
    first = {a.channel: a.event_index for a in alarms}

    if drift_type == "none":
        # Any alarm from any detector on drift-free data is a false positive.
        fp = bool(alarms) or bool(detect_context_decay(post, baseline)) \
            or bool(detect_version_drift(records)) \
            or bool(detect_omission(post, baseline)) \
            or bool(check_goal_persistence(records, SPECS))
        return TrialResult(drift_type, detected=fp, delay=None,
                           detail="false positive" if fp else "clean")

    if drift_type == "abrupt":
        # The jump regime belongs to the change-point channel (Section 5).
        idx = first.get("cusum")
        return TrialResult(drift_type, idx is not None,
                           idx - onset if idx is not None else None,
                           detail=f"channels fired: {sorted(first)}")

    if drift_type == "gradual":
        idx = first.get("divergence")
        return TrialResult(drift_type, idx is not None,
                           idx - onset if idx is not None else None,
                           detail=f"channels fired: {sorted(first)}")

    if drift_type == "transient":
        v = classify_persistence(records, baseline)
        ok = v.shifted and not v.persistent
        return TrialResult(
            drift_type, ok,
            v.first_alarm_index - onset if v.first_alarm_index is not None else None,
            detail=f"shifted={v.shifted} persistent={v.persistent}",
        )

    if drift_type == "context_decay":
        findings = detect_context_decay(post, baseline)
        top = max(findings, key=lambda f: f.z, default=None)
        return TrialResult(
            drift_type, bool(findings), None,
            detail=(f"{len(findings)} bins flagged, worst bin {top.bin} "
                    f"({top.baseline_rate:.2f} -> {top.observed_rate:.2f}, z={top.z:.1f})"
                    if top else "no bins flagged"),
        )

    if drift_type == "version":
        shifts = detect_version_drift(records)
        hit = next((s for s in shifts if s.to_version[1] == "2.0"), None)
        return TrialResult(
            drift_type, hit is not None,
            hit.boundary_index - onset if hit else None,
            detail=f"JSD across version boundary: {hit.jsd:.3f}" if hit else "no shift found",
        )

    if drift_type == "omission":
        findings = detect_omission(post, baseline)
        return TrialResult(
            drift_type, bool(findings), None,
            detail="dropped: " + ", ".join(
                f"{f.goal_id}/{f.tool} ({f.observed_presence:.0%} of runs)"
                for f in findings) if findings else "nothing dropped",
        )

    if drift_type == "failure_classes":
        violations = check_goal_persistence(records, SPECS)
        kinds = {v.kind for v in violations}
        expected = {"duplicate_submission", "premature_abort", "false_success", "missing_progress"}
        counts = {k: sum(v.kind == k for v in violations) for k in sorted(kinds)}
        return TrialResult(
            drift_type, expected <= kinds, None,
            detail=f"violations by kind: {counts}",
        )

    raise ValueError(drift_type)


def evaluate(trials: int, n_runs: int, seed: int) -> dict[str, Summary]:
    results: dict[str, Summary] = {t: Summary() for t in DRIFT_TYPES}
    for k in range(trials):
        for drift_type in DRIFT_TYPES:
            results[drift_type].add(run_trial(drift_type, seed + 1000 * k, n_runs))
    return results


RESPONSIBLE = {
    "none": "all (false-positive check)",
    "abrupt": "CUSUM change-point channel",
    "gradual": "windowed JSD + EMA channel",
    "transient": "persistence classifier (shift seen, not durable)",
    "context_decay": "error rate by run-length bin",
    "version": "version segmentation + JSD",
    "omission": "expected-tool presence per goal",
    "failure_classes": "per-run predicates (4 countable classes)",
}


def to_markdown(results: dict[str, Summary], trials: int, n_runs: int, seed: int) -> str:
    lines = [
        "# Synthetic validation of the drift detectors",
        "",
        f"Trials per drift type: {trials} (seeds {seed}, +1000 each) — "
        f"{n_runs} runs per period, stdlib-only, fully deterministic.",
        "",
        "> **These numbers validate the detectors on synthetic data with known",
        "> drift onsets. They are NOT detection performance on real operational",
        "> records and must never be entered into Table 2 of the survey.**",
        "",
        "| Drift scenario | Responsible detector | Detected (rate) | Median delay (events) | Example detail |",
        "|---|---|---|---|---|",
    ]
    for drift_type in DRIFT_TYPES:
        s = results[drift_type]
        rate = s.rate()
        shown = f"{rate:.0%}" if drift_type != "none" else f"FPR {rate:.0%}"
        delay = s.median_delay()
        lines.append(
            f"| {drift_type} | {RESPONSIBLE[drift_type]} | {shown} | "
            f"{delay if delay is not None else 'n/a'} | {s.trials[0].detail} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    results = evaluate(args.trials, args.runs, args.seed)
    md = to_markdown(results, args.trials, args.runs, args.seed)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written to {args.out}")


if __name__ == "__main__":
    main()
