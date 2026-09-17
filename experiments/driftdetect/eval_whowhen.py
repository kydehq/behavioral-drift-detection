"""Seam observability on Who&When multi-agent records.

This corpus cannot support a detection-rate experiment at all: all 184
runs are failures (the dataset exists to attribute them), so there is no
clean side to calibrate on and nothing to compose a drifted-vs-benign
contrast from. What it CAN measure is the premise behind Table 2's
multi-agent row — "partial: visible if the seam itself crosses the
boundary" — because every history entry is a message on the delegation
seam and the human ground truth names the agent and step responsible:

1. Attribution observability — for how many runs does the annotated
   ``mistake_agent`` appear as a speaker in the boundary record, and
   for how many is ``mistake_step`` a valid record index? If a human's
   failure attribution can be stated in terms the record contains, a
   seam-level detector has the vocabulary it needs.
2. Position profile — where in the run do the annotated mistakes sit
   (early / middle / late third)? Uniform positions mean a seam
   detector cannot rely on "failures happen late".
3. Routing weight — the share of a run's messages spoken by the
   mistake agent. If failing agents are also dominant speakers,
   routing *volume* alone cannot localize them; localization needs
   sequence or content-adjacent signals.

HONESTY NOTE (for any number leaving this harness): these are corpus
descriptions of failed runs — no detection rates exist or can exist on
this data, and nothing here belongs in Table 2's "detection rate"
column.

Usage:
    python3 -m driftdetect.eval_whowhen <ledger-dir> [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics

from .records import group_by_run, read_jsonl


def speaker(seam_label: str) -> str:
    """Plain speaker from a seam label: 'Orchestrator (-> WebSurfer)' ->
    'Orchestrator'; Algorithm-Generated names pass through unchanged."""
    return seam_label.split(" (")[0]


def load_variant(ledger_dir: str, key: str):
    records = list(read_jsonl(os.path.join(ledger_dir, f"{key}.jsonl")))
    with open(os.path.join(ledger_dir, f"{key}.labels.json"),
              encoding="utf-8") as fh:
        labels = json.load(fh)
    return group_by_run(records), labels


def evaluate_variant(ledger_dir: str, key: str) -> dict:
    runs, labels = load_variant(ledger_dir, key)
    all_records = [r for recs in runs.values() for r in recs]

    seam_vocab = {r.tool for r in all_records}
    speakers = {speaker(r.tool) for r in all_records}

    n_agent_visible = 0
    n_step_valid = 0
    n_both = 0
    thirds = [0, 0, 0]
    mistake_share: list[float] = []
    for run_id, label in labels.items():
        recs = runs.get(run_id, [])
        ma = str(label.get("mistake_agent") or "").lower()
        agent_visible = any(speaker(r.tool).lower() == ma for r in recs)
        n_agent_visible += agent_visible

        step_valid = False
        try:
            ms = int(str(label.get("mistake_step")))
            step_valid = 0 <= ms < len(recs)
        except (TypeError, ValueError):
            pass
        n_step_valid += step_valid
        n_both += agent_visible and step_valid

        if step_valid and len(recs) > 0:
            rel = ms / len(recs)
            thirds[min(2, int(rel * 3))] += 1
        if agent_visible and recs:
            share = sum(speaker(r.tool).lower() == ma for r in recs) / len(recs)
            mistake_share.append(share)

    return {
        "variant": key,
        "n_runs": len(labels),
        "n_records": len(all_records),
        "seam_vocab": len(seam_vocab),
        "n_speakers": len(speakers),
        "agent_visible": n_agent_visible,
        "step_valid": n_step_valid,
        "both": n_both,
        "thirds": thirds,
        "median_mistake_share": (statistics.median(mistake_share)
                                 if mistake_share else None),
    }


def render_markdown(rows: list[dict], args) -> str:
    lines = [
        "# Seam observability on Who&When records",
        "",
        "All runs in this corpus are failures; no detection-rate",
        "experiment is possible (module docstring). Measured instead:",
        "whether the failure attribution a human produced can be stated",
        "in terms the boundary record contains.",
        "",
        "## Attribution observability",
        "",
        "| variant | runs | records | seam labels | speakers "
        "| mistake agent visible | mistake step valid | both |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['n_runs']} | {r['n_records']} "
            f"| {r['seam_vocab']} | {r['n_speakers']} "
            f"| {r['agent_visible']}/{r['n_runs']} "
            f"| {r['step_valid']}/{r['n_runs']} "
            f"| {r['both']}/{r['n_runs']} |"
        )
    lines += [
        "",
        "## Where the annotated mistake sits, and who makes it",
        "",
        "Position = mistake_step relative to run length. Routing weight =",
        "median share of a run's messages spoken by the mistake agent.",
        "",
        "| variant | early third | middle third | late third | median routing weight of mistake agent |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        t = r["thirds"]
        share = (f"{r['median_mistake_share']:.1%}"
                 if r["median_mistake_share"] is not None else "—")
        lines.append(
            f"| {r['variant']} | {t[0]} | {t[1]} | {t[2]} | {share} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir",
                    help="directory with <variant>.jsonl + labels from the adapter")
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    keys = sorted(
        f[: -len(".jsonl")] for f in os.listdir(args.ledger_dir)
        if f.endswith(".jsonl")
    )
    rows = [evaluate_variant(args.ledger_dir, k) for k in keys]

    md = render_markdown(rows, args)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
