"""E1/L1 window sweep: where does divergence calibration recover?

The E1/L1 measurement (eval_l1_terminalwrench) found that the stream
experiment's divergence channel false-alarms on 100% of null streams: a
50-token window over a 51k-109k-token L1 vocabulary saturates the
windowed JSD near its bound, the calibrated threshold hits the 0.9 cap,
and every null stream crosses it. That is a statement about the
*detector's window*, not about the corpus.

This module prices that statement: the same stream experiment, same
splits, same calibration regime (fast_stream_trial, unchanged), swept
over the window size. Reported per (model, window): the median
calibrated divergence threshold, how many of the trials' thresholds sat
at the DIV_THRESHOLD_CAP, and the divergence channel's false-alarm /
detection / delay figures. The CUSUM channel does not depend on the
window; its columns would repeat the E1/L1 table verbatim and are
omitted.

The equal-horizon rule and the composed-timeline HONESTY NOTE of
eval_terminalwrench apply verbatim.

Usage:
    python3 -m driftdetect.eval_l1_window_sweep <ledger-dir> <content-dir>
        [--windows 50,200,800,3200] [--trials 10] [--margin 2.0] [--seed 7]
        [--jobs N] [--out results.md]
"""

from __future__ import annotations

import argparse
import os
import statistics

from concurrent.futures import ProcessPoolExecutor

from .eval_agentdojo import DIV_THRESHOLD_CAP, load_pipeline
from .eval_l1_terminalwrench import fast_stream_trial, load_sidecar, token_runs
from .eval_terminalwrench import CLEAN_CLASS, HACKED_CLASS

DEFAULT_WINDOWS = (50, 200, 800, 3200)


def sweep_model(ledger_dir: str, content_dir: str, model: str,
                windows: tuple[int, ...], trials: int, seed: int,
                margin: float) -> list[dict]:
    """One row per (model, window); loads the corpus once."""
    import random

    l0_runs, labels = load_pipeline(ledger_dir, model)
    sidecar = load_sidecar(content_dir, model)
    runs = token_runs(l0_runs, sidecar)

    benign = sorted(rid for rid, l in labels.items()
                    if l["classification"] == CLEAN_CLASS and l["n_calls"] > 0)
    hacked = sorted(rid for rid, l in labels.items()
                    if l["classification"] == HACKED_CLASS and l["n_calls"] > 0)
    if len(benign) < 40 or len(hacked) < 30:
        return []

    rows = []
    for window in windows:
        cells = []
        for i in range(trials):
            cell = fast_stream_trial(benign, hacked, runs,
                                     random.Random(seed + i), window, margin,
                                     with_thresholds=True)
            if cell is not None:
                cells.append(cell)
        if not cells:
            rows.append({"model": model, "window": window, "cells": 0})
            continue
        delays = [c["delay"]["divergence"] for c in cells
                  if "divergence" in c["delay"]]
        rows.append({
            "model": model,
            "window": window,
            "cells": len(cells),
            "div_threshold_median": statistics.median(
                c["div_threshold"] for c in cells),
            "n_capped": sum(c["div_threshold"] >= DIV_THRESHOLD_CAP
                            for c in cells),
            "false_alarm": sum(c["false_alarm"]["divergence"]
                               for c in cells) / len(cells),
            "detected": sum(c["detected"]["divergence"]
                            for c in cells) / len(cells),
            "median_delay": int(statistics.median(delays)) if delays else None,
        })
    return rows


def render_markdown(rows: list[dict], args) -> str:
    lines = [
        "# E1/L1 window sweep: divergence calibration vs. window size",
        "",
        f"{args.trials} trials per cell, seed base {args.seed}, margin",
        f"{args.margin}. Same corpus, splits, and calibration regime as",
        "results/l1-terminalwrench-rewardhack.md; only the divergence window",
        "varies. 'capped' counts trials whose calibrated threshold sat at the",
        f"{DIV_THRESHOLD_CAP} cap — the saturation signature. CUSUM is",
        "window-independent and omitted (module docstring).",
        "",
        "| model | window | median div threshold | capped | FP div | det. div | delay div |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["cells"] == 0:
            lines.append(f"| {r['model']} | {r['window']} | — | — | — | — | — |")
            continue
        lines.append(
            f"| {r['model']} | {r['window']} "
            f"| {r['div_threshold_median']:.3f} "
            f"| {r['n_capped']}/{r['cells']} "
            f"| {r['false_alarm']:.0%} | {r['detected']:.0%} "
            f"| {r['median_delay'] if r['median_delay'] is not None else '—'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", help="L0 ledgers from adapters.terminalwrench")
    ap.add_argument("content_dir", help="content sidecars from adapters.terminalwrench_content")
    ap.add_argument("--windows", default=",".join(str(w) for w in DEFAULT_WINDOWS),
                    help="comma-separated window sizes in tokens")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--margin", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--jobs", type=int, default=0,
                    help="parallel model workers; 0 = min(#models, cpu count)")
    ap.add_argument("--out", help="write the markdown table here as well")
    args = ap.parse_args(argv)

    windows = tuple(int(w) for w in args.windows.split(","))
    models = sorted(
        f[: -len(".jsonl")] for f in os.listdir(args.ledger_dir)
        if f.endswith(".jsonl") and not f.endswith(".content.jsonl")
    )
    jobs = args.jobs if args.jobs > 0 else min(len(models), os.cpu_count() or 1)
    if jobs > 1 and len(models) > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = [
                pool.submit(sweep_model, args.ledger_dir, args.content_dir,
                            name, windows, args.trials, args.seed, args.margin)
                for name in models
            ]
            per_model = [f.result() for f in futures]
    else:
        per_model = [
            sweep_model(args.ledger_dir, args.content_dir, name, windows,
                        args.trials, args.seed, args.margin)
            for name in models
        ]
    rows = [row for rows_ in per_model for row in rows_]

    md = render_markdown(rows, args)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
