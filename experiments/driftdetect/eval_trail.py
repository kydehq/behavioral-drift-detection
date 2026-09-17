"""Error-rate / context-decay validation on real TRAIL records.

TRAIL's role differs from the AgentDojo / Terminal Wrench evals: 148
traces are far too few for detection-rate tables. What the corpus
uniquely has is a real per-call ``status_code`` PLUS 841 human-annotated
per-step errors — enough to validate the premises of the error-rate
detector (``detect_context_decay``) on real records:

1. Signal coverage — how much of the human-annotated error mass does the
   runtime status signal actually carry? The overview table reports the
   share of annotated errors whose span also has status Error; the
   remainder is reasoning-level error invisible to a boundary status.
2. Length profile — do the status-error rate and the annotated-error
   rate rise with position in the run? That rising shape is exactly what
   ``detect_context_decay`` is built to flag.
3. Calibration — on a stationary split (baseline frozen on half the
   runs, detector on the other half, same distribution) the detector
   should flag nothing; every flag on this split is a false positive.

HONESTY NOTE (for any number leaving this harness): these are corpus
descriptions and a calibration check on real records — not detection
rates, and nothing here belongs in Table 2 of the survey.

Usage:
    python3 -m driftdetect.eval_trail <ledger-dir> [--trials 10]
        [--seed 7] [--z 3.0] [--min-calls 30] [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import random

from .baseline import LENGTH_BIN_WIDTH, freeze_baseline, length_bin
from .detectors import detect_context_decay
from .records import group_by_run, read_jsonl


def load_dataset(ledger_dir: str, key: str):
    records = list(read_jsonl(os.path.join(ledger_dir, f"{key}.jsonl")))
    with open(os.path.join(ledger_dir, f"{key}.labels.json"),
              encoding="utf-8") as fh:
        labels = json.load(fh)
    return group_by_run(records), labels


def evaluate_dataset(ledger_dir: str, key: str, trials: int, seed: int,
                     z: float, min_calls: int) -> dict:
    runs, labels = load_dataset(ledger_dir, key)
    all_records = [r for recs in runs.values() for r in recs]

    n_err = sum(r.status == "error" for r in all_records)
    n_ann = sum(l["n_errors_annotated"] for l in labels.values())
    n_resolved = sum(l["n_locations_resolved"] for l in labels.values())
    n_on_err = sum(l["n_annotated_on_error_status"] for l in labels.values())
    models = sorted({r.model for r in all_records if r.model})

    # annotated errors mapped onto length bins via the records' span ids
    ann_by_bin: dict[int, int] = {}
    for run_id, label in labels.items():
        by_span = {r.meta.get("span_id"): r for r in runs.get(run_id, [])}
        for err in label["errors"]:
            rec = by_span.get(err["location"])
            if rec is not None:
                b = length_bin(rec.step_index)
                ann_by_bin[b] = ann_by_bin.get(b, 0) + 1

    calls_by_bin: dict[int, int] = {}
    err_by_bin: dict[int, int] = {}
    for r in all_records:
        b = length_bin(r.step_index)
        calls_by_bin[b] = calls_by_bin.get(b, 0) + 1
        if r.status == "error":
            err_by_bin[b] = err_by_bin.get(b, 0) + 1

    bins = []
    for b in sorted(calls_by_bin):
        n = calls_by_bin[b]
        if n < min_calls:
            continue
        bins.append({
            "bin": b,
            "steps": f"{b * LENGTH_BIN_WIDTH}–{(b + 1) * LENGTH_BIN_WIDTH - 1}",
            "calls": n,
            "status_error_rate": err_by_bin.get(b, 0) / n,
            "annotated": ann_by_bin.get(b, 0),
            "annotated_rate": ann_by_bin.get(b, 0) / n,
        })

    # stationary split-half calibration: every flag is a false positive
    run_ids = sorted(runs)
    flags_per_trial: list[int] = []
    for i in range(trials):
        rng = random.Random(seed + i)
        shuffled = run_ids[:]
        rng.shuffle(shuffled)
        half = len(shuffled) // 2
        base_recs = [r for rid in shuffled[:half] for r in runs[rid]]
        cur_recs = [r for rid in shuffled[half:] for r in runs[rid]]
        baseline = freeze_baseline(base_recs)
        findings = detect_context_decay(cur_recs, baseline,
                                        z_threshold=z, min_calls=min_calls)
        flags_per_trial.append(len(findings))

    return {
        "dataset": key,
        "n_runs": len(runs),
        "n_records": len(all_records),
        "n_status_error": n_err,
        "status_error_rate": n_err / len(all_records) if all_records else 0.0,
        "n_annotated": n_ann,
        "n_resolved": n_resolved,
        "n_annotated_on_error_status": n_on_err,
        "models": models,
        "bins": bins,
        "calibration_flags": flags_per_trial,
    }


def render_markdown(rows: list[dict], args) -> str:
    lines = [
        "# Error-rate / context-decay validation on TRAIL records",
        "",
        f"Split-half calibration: {args.trials} trials, seed base {args.seed},",
        f"z-threshold {args.z}, min {args.min_calls} calls per bin. Real",
        "records; corpus description + calibration check, not detection",
        "rates (module docstring). One record per OpenTelemetry span.",
        "",
        "## Overview and signal coverage",
        "",
        "share on-status = annotated errors whose span also carries",
        "status_code Error — the fraction of human-judged error mass the",
        "runtime status signal sees at all.",
        "",
        "| dataset | runs | records | status errors | annotated errors"
        " (resolved) | on-status | share on-status | models |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        share = (r["n_annotated_on_error_status"] / r["n_resolved"]
                 if r["n_resolved"] else 0.0)
        lines.append(
            f"| {r['dataset']} | {r['n_runs']} | {r['n_records']} "
            f"| {r['n_status_error']} ({r['status_error_rate']:.1%}) "
            f"| {r['n_annotated']} ({r['n_resolved']}) "
            f"| {r['n_annotated_on_error_status']} | {share:.1%} "
            f"| {', '.join(r['models']) or '—'} |"
        )
    for r in rows:
        lines += [
            "",
            f"## Length profile — {r['dataset']}",
            "",
            "| steps in run | calls | status-error rate | annotated errors"
            " | annotated per call |",
            "|---|---|---|---|---|",
        ]
        for b in r["bins"]:
            lines.append(
                f"| {b['steps']} | {b['calls']} "
                f"| {b['status_error_rate']:.1%} "
                f"| {b['annotated']} | {b['annotated_rate']:.3f} |"
            )
    lines += [
        "",
        "## Split-half calibration (stationary — every flag is false)",
        "",
        "| dataset | trials | trials with flags | flagged bins total |",
        "|---|---|---|---|",
    ]
    for r in rows:
        f = r["calibration_flags"]
        lines.append(
            f"| {r['dataset']} | {len(f)} "
            f"| {sum(1 for x in f if x)} | {sum(f)} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir",
                    help="directory with <dataset>.jsonl + labels from the adapter")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--z", type=float, default=3.0)
    ap.add_argument("--min-calls", type=int, default=30)
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    keys = sorted(
        f[: -len(".jsonl")] for f in os.listdir(args.ledger_dir)
        if f.endswith(".jsonl")
    )
    rows = [evaluate_dataset(args.ledger_dir, k, args.trials, args.seed,
                             args.z, args.min_calls) for k in keys]

    md = render_markdown(rows, args)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
