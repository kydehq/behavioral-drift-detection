"""Two-regime detector vs. SWE-bench submission ledgers.

Two experiments over the ledgers produced by adapters.swebench, using the
same admission-time calibration protocol as eval_agentdojo (out-of-sample
Phase-I: thresholds = max in-control score * margin; equal horizons):

1. NULL STABILITY (within one submission): a submission is one batch of
   runs of one agent version — no drift is expected inside it. Streams
   are composed from shuffled runs, split 50/25/25 into admission window
   (frozen baseline), calibration stream, and null stream; any alarm on
   the null stream is a false positive. This is the false-positive
   measurement the AgentDojo suites were too small for (~500 runs here
   vs. ~30 there). Streams are NOT goal-conditioned: a coding agent's
   tool vocabulary is repository-independent (edit/open/execute on every
   task), so the suite-mixture artifact of AgentDojo does not arise —
   which is itself a scoping statement worth reporting.

2. VERSION DRIFT (across submissions of one framework family): freeze
   the baseline (and calibrate) on the earlier submission, stream the
   later one against it, truncated to the same horizon as the null
   experiment's stream. The version change is real ground truth read off
   the record (the submissions ARE different agent versions); reported
   alongside is the plain JSD between the two submissions' overall tool
   distributions (the detect_version_drift quantity). Only within-family
   pairs are compared — across frameworks the vocabulary changes
   trivially and detection would be free.

HONESTY NOTE: records are unmodified real agent behavior; run order
within a submission batch carries no temporal meaning, so stream order
is seeded shuffling — a constructed timeline. Report accordingly.

Usage:
    python3 -m driftdetect.eval_swebench <ledger-dir> [--trials 5]
        [--window 50] [--margin 1.2] [--min-runs 100] [--seed 7]
        [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics

from .baseline import freeze_baseline, tool_distribution
from .detectors import CusumChannel, DivergenceChannel, js_divergence, run_two_regime
from .records import CallRecord, read_jsonl

CHANNELS = ("divergence", "cusum")

# Framework families for the version-drift pairing; matched against the
# lowercased submission name. Submissions matching nothing stay out of
# experiment 2 (cross-framework comparisons would be trivially detectable).
FAMILIES = ("sweagent", "openhands", "emergent", "epam", "lingxi", "trae")


def family_of(submission: str) -> str | None:
    low = submission.lower()
    for fam in FAMILIES:
        if fam in low:
            return fam
    return None


def load_runs(ledger_dir: str, submission: str) -> dict[str, list[CallRecord]]:
    runs: dict[str, list[CallRecord]] = {}
    for rec in read_jsonl(os.path.join(ledger_dir, f"{submission}.jsonl")):
        runs.setdefault(rec.run_id, []).append(rec)
    for recs in runs.values():
        recs.sort(key=lambda r: r.step_index)
    return runs


def _concat(run_ids: list[str], runs: dict[str, list[CallRecord]]) -> list[CallRecord]:
    return [rec for rid in run_ids for rec in runs[rid]]


DIV_THRESHOLD_CAP = 0.9


def calibrate(baseline, calibration: list[CallRecord], window: int, margin: float):
    div = DivergenceChannel(baseline, window=window)
    cus = CusumChannel(baseline)
    max_jsd = max_stat = 0.0
    for rec in calibration:
        s = div.update(rec)
        if s is not None:
            max_jsd = max(max_jsd, s)
        max_stat = max(max_stat, cus.update(rec))
    # JSD is bounded in [0, 1]: a multiplicative margin can push the
    # threshold beyond the attainable range, silently disabling the channel
    # (observed: the largest real shift, JSD 0.813, went 0%-detected at
    # margin 2.0). CUSUM is unbounded and needs no cap.
    return min(max_jsd * margin, DIV_THRESHOLD_CAP), max_stat * margin


def _split(run_ids: list[str], rng: random.Random):
    ids = run_ids[:]
    rng.shuffle(ids)
    n = len(ids)
    return ids[: n // 2], ids[n // 2 : (3 * n) // 4], ids[(3 * n) // 4 :]


def null_trial(runs, rng: random.Random, window: int, margin: float) -> dict | None:
    adm_ids, cal_ids, null_ids = _split(sorted(runs), rng)
    admission = _concat(adm_ids, runs)
    calibration = _concat(cal_ids, runs)
    null_stream = _concat(null_ids, runs)
    if len(calibration) <= window or len(null_stream) <= window:
        return None
    baseline = freeze_baseline(admission)
    div_thr, cusum_thr = calibrate(baseline, calibration, window, margin)
    alarms = {
        a.channel
        for a in run_two_regime(
            null_stream, baseline,
            DivergenceChannel(baseline, window=window, threshold=div_thr),
            CusumChannel(baseline, threshold=cusum_thr),
        )
    }
    return {
        "false_alarm": {ch: ch in alarms for ch in CHANNELS},
        "thresholds": {"divergence": div_thr, "cusum": cusum_thr},
        "horizon": len(null_stream),
    }


def version_trial(runs_old, runs_new, rng: random.Random, window: int, margin: float) -> dict | None:
    adm_ids, cal_ids, null_ids = _split(sorted(runs_old), rng)
    admission = _concat(adm_ids, runs_old)
    calibration = _concat(cal_ids, runs_old)
    horizon = len(_concat(null_ids, runs_old))
    if len(calibration) <= window or horizon <= window:
        return None
    baseline = freeze_baseline(admission)
    div_thr, cusum_thr = calibrate(baseline, calibration, window, margin)

    new_ids = sorted(runs_new)
    rng.shuffle(new_ids)
    stream = _concat(new_ids, runs_new)[:horizon]
    alarms = {
        a.channel: a.event_index
        for a in run_two_regime(
            stream, baseline,
            DivergenceChannel(baseline, window=window, threshold=div_thr),
            CusumChannel(baseline, threshold=cusum_thr),
        )
    }
    return {
        "detected": {ch: ch in alarms for ch in CHANNELS},
        "delay": alarms,
    }


def evaluate(ledger_dir: str, trials: int, seed: int, window: int, margin: float,
             min_runs: int):
    with open(os.path.join(ledger_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    submissions = sorted(
        s for s, info in manifest["submissions"].items() if info["n_runs"] >= min_runs
    )
    all_runs = {s: load_runs(ledger_dir, s) for s in submissions}

    null_rows = []
    for sub in submissions:
        cells = [c for i in range(trials)
                 if (c := null_trial(all_runs[sub], random.Random(seed + i), window, margin))]
        if not cells:
            continue
        null_rows.append({
            "submission": sub,
            "n_runs": len(all_runs[sub]),
            "cells": len(cells),
            "fp": {ch: sum(c["false_alarm"][ch] for c in cells) / len(cells) for ch in CHANNELS},
            "median_horizon": int(statistics.median(c["horizon"] for c in cells)),
        })

    version_rows = []
    by_family: dict[str, list[str]] = {}
    for sub in submissions:
        fam = family_of(sub)
        if fam:
            by_family.setdefault(fam, []).append(sub)
    for fam, subs in sorted(by_family.items()):
        subs = sorted(subs)  # date prefix sorts chronologically
        for old, new in zip(subs, subs[1:]):
            cells = [c for i in range(trials)
                     if (c := version_trial(all_runs[old], all_runs[new],
                                            random.Random(seed + i), window, margin))]
            if not cells:
                continue
            dist_jsd = js_divergence(
                tool_distribution([r for rs in all_runs[old].values() for r in rs]),
                tool_distribution([r for rs in all_runs[new].values() for r in rs]),
            )
            def med_delay(ch):
                d = [c["delay"][ch] for c in cells if ch in c["delay"]]
                return int(statistics.median(d)) if d else None
            version_rows.append({
                "family": fam, "old": old, "new": new,
                "cells": len(cells), "jsd": dist_jsd,
                "detection": {ch: sum(c["detected"][ch] for c in cells) / len(cells)
                              for ch in CHANNELS},
                "median_delay": {ch: med_delay(ch) for ch in CHANNELS},
            })
    return null_rows, version_rows


def render_markdown(null_rows, version_rows, args) -> str:
    lines = [
        "# Two-regime detector on SWE-bench submission ledgers",
        "",
        f"{args.trials} trials, seed base {args.seed}, divergence window {args.window},",
        f"calibration margin {args.margin}, submissions with >= {args.min_runs} runs.",
        "Real records, composed (shuffled) stream order — run order inside a",
        "submission batch has no temporal meaning. See module docstring.",
        "",
        "## Null stability within submissions (no drift expected; alarms = FP)",
        "",
        "| submission | runs | cells | FP div | FP cusum | median horizon |",
        "|---|---|---|---|---|---|",
    ]
    for r in null_rows:
        lines.append(
            f"| {r['submission']} | {r['n_runs']} | {r['cells']} "
            f"| {r['fp']['divergence']:.0%} | {r['fp']['cusum']:.0%} "
            f"| {r['median_horizon']} |"
        )
    lines += [
        "",
        "## Version drift across submissions (same framework family; real version change)",
        "",
        "| family | baseline submission | streamed submission | cells | dist. JSD | det. div | det. cusum | delay div | delay cusum |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in version_rows:
        m = r["median_delay"]
        lines.append(
            f"| {r['family']} | {r['old']} | {r['new']} | {r['cells']} "
            f"| {r['jsd']:.3f} "
            f"| {r['detection']['divergence']:.0%} | {r['detection']['cusum']:.0%} "
            f"| {m['divergence'] if m['divergence'] is not None else '—'} "
            f"| {m['cusum'] if m['cusum'] is not None else '—'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", help="directory with <submission>.jsonl + manifest.json")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--window", type=int, default=50)
    ap.add_argument("--margin", type=float, default=1.2)
    ap.add_argument("--min-runs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    null_rows, version_rows = evaluate(
        args.ledger_dir, args.trials, args.seed, args.window, args.margin, args.min_runs
    )
    md = render_markdown(null_rows, version_rows, args)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
