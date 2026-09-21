"""E4: failure attribution on Who&When via L3 seam content.

The companion's L0 measurement (eval_whowhen) established seam
*observability*: the annotated mistake agent appears as a speaker and
the mistake step is a valid record index in 184/184 runs — but the
corpus holds only failures, so no detection rates exist. E4 asks the
follow-up the L3 rung permits: given the seam *content* (the message
text), can a deterministic rule LOCALIZE the annotated mistake — name
its step and agent — better than content-free baselines? Attribution
accounting, not detection.

Predictors (frozen 2026-09-21, developed on the DEV split only — the
same sha256(run_id) % 5 protocol as the other follow-up experiments,
``is_dev`` imported, not copied). Each names exactly one record per
run:

- positional baselines (no content): ``first``, ``third``, ``middle``,
  ``last`` record;
- content predictors: ``first_error`` (first record whose text matches
  the frozen error signature), ``before_first_error`` (the record
  before it — the *causer* of the first visible failure),
  ``before_first_apology`` (the record before the first
  self-correction marker); all fall back to ``first`` when nothing
  matches;
- structural predictors (sequence, no content): ``first_worker`` /
  ``second_worker`` — the first/second record spoken by a plain
  worker (speaker neither Orchestrator nor human, no routing/thought
  frame), the Magentic-One shape where the orchestrator's turns are
  bookkeeping.

Metrics per variant, dev and held-out eval: step@1 (predicted record
index equals the annotated ``mistake_step``), |Δ| ≤ 2, and agent@1
(the predicted record's speaker equals ``mistake_agent``); ``E[random]``
is the analytic expectation of step@1 under a uniform pick, mean(1/n).

HONESTY NOTES. (1) All 184 runs are failures: this measures
localization given failure, never detection — nothing here belongs in
a detection-rate column. (2) The dev split is small (16 + 14 runs);
the dev/eval agreement column carries the weight. (3) The expected
shape is itself the finding: on Algorithm-Generated the first visible
execution failure has a *causer one step earlier* which content finds;
on Hand-Crafted the annotated mistakes are semantic judgments
("clicked an irrelevant link") with no deterministic content
signature — the periodic "Updated Ledger" cadence matches every turn
— so whatever localization exists there comes from *structure*, not
content. (4) The predictors are scaffold-shaped (AG2 expert teams,
Magentic-One routing) like every content-bearing detector in this
paper: per-deployment, frozen, maintained.

Usage:
    python3 -m driftdetect.eval_whowhen_content <ledger-dir> <content-dir>
        [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

from .eval_l3_terminalwrench import is_dev
from .eval_whowhen import speaker

# Frozen 2026-09-21, developed on the DEV split only (module docstring).
ERROR_SIGNATURE = re.compile(
    r"Traceback \(most recent call last\)|exitcode: [1-9]"
    r"|\bexecution failed\b|Error: |\bexception\b", re.IGNORECASE)
APOLOGY_SIGNATURE = re.compile(
    r"\b(apolog|sorry|let'?s try again|try a different|didn'?t work"
    r"|does not work|failed to)\b", re.IGNORECASE)

BASELINES = ("first", "third", "middle", "last")
CONTENT = ("first_error", "before_first_error", "before_first_apology")
STRUCTURAL = ("first_worker", "second_worker")
PREDICTORS = BASELINES + CONTENT + STRUCTURAL


def is_worker(seam_label: str) -> bool:
    """A plain worker turn: not Orchestrator/human, not a routing or
    thought frame like 'Orchestrator (-> WebSurfer)'."""
    return (speaker(seam_label).lower() not in ("orchestrator", "human")
            and "(" not in seam_label)


def predict(seq: list[tuple[int, str, str]]) -> dict[str, int]:
    """seq: ordered (step_index, seam_label, l3_text) records of one run.
    Returns predictor name -> predicted source step index."""
    n = len(seq)
    preds = {
        "first": seq[0][0],
        "third": seq[min(2, n - 1)][0],
        "middle": seq[n // 2][0],
        "last": seq[-1][0],
    }
    first_error = next((i for i, (_, _, text) in enumerate(seq)
                        if ERROR_SIGNATURE.search(text)), None)
    preds["first_error"] = (seq[first_error][0]
                            if first_error is not None else seq[0][0])
    preds["before_first_error"] = (seq[max(first_error - 1, 0)][0]
                                   if first_error is not None else seq[0][0])
    first_apology = next((i for i, (_, _, text) in enumerate(seq)
                          if APOLOGY_SIGNATURE.search(text)), None)
    preds["before_first_apology"] = (seq[max(first_apology - 1, 0)][0]
                                     if first_apology is not None
                                     else seq[0][0])
    workers = [step for step, label, _ in seq if is_worker(label)]
    preds["first_worker"] = workers[0] if workers else seq[0][0]
    preds["second_worker"] = (workers[1] if len(workers) > 1
                              else preds["first_worker"])
    return preds


def load_runs(content_dir: str, key: str) -> dict[str, list]:
    runs: dict[str, list] = defaultdict(list)
    path = os.path.join(content_dir, f"{key}.content.jsonl")
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = json.loads(raw)
            runs[line["run_id"]].append(
                (line["step_index"], line["tool"], line["l3_text"]))
    return runs


def evaluate_variant(ledger_dir: str, content_dir: str, key: str) -> dict:
    with open(os.path.join(ledger_dir, f"{key}.labels.json"),
              encoding="utf-8") as fh:
        labels = json.load(fh)
    runs = load_runs(content_dir, key)

    rows = []
    for split, keep in (("eval", lambda rid: not is_dev(rid)),
                        ("dev", is_dev)):
        per = {name: [0, 0, 0] for name in PREDICTORS}  # step@1, |d|<=2, agent@1
        n = 0
        inv_n_sum = 0.0
        for run_id, label in labels.items():
            if not keep(run_id):
                continue
            seq = sorted(runs.get(run_id, []))
            if not seq:
                continue
            try:
                mistake_step = int(str(label.get("mistake_step")))
            except (TypeError, ValueError):
                continue
            mistake_agent = str(label.get("mistake_agent") or "").lower()
            n += 1
            inv_n_sum += 1.0 / len(seq)
            label_by_step = {step: seam for step, seam, _ in seq}
            for name, p in predict(seq).items():
                row = per[name]
                row[0] += (p == mistake_step)
                row[1] += abs(p - mistake_step) <= 2
                row[2] += (speaker(label_by_step.get(p, "")).lower()
                           == mistake_agent)
        rows.append({
            "variant": key, "split": split, "n": n,
            "random_step_at_1": inv_n_sum / n if n else 0.0,
            "predictors": {name: tuple(v) for name, v in per.items()},
        })
    return rows


def render_markdown(results: list[list[dict]]) -> str:
    lines = [
        "# E4: failure attribution on Who&When, L3 seam content",
        "",
        "One frozen prediction per run and predictor (module docstring);",
        "predictors were developed on the ~20% dev split only, 'eval' is",
        "the held-out measurement. step@1 = predicted record index equals",
        "the annotated mistake_step; agent@1 = the predicted record's",
        "speaker equals mistake_agent. All 184 runs are failures:",
        "attribution accounting, never detection rates. E[random] is the",
        "analytic step@1 of a uniform pick.",
        "",
    ]
    for rows in results:
        for r in rows:
            lines += [
                f"## {r['variant']} — {r['split']} split "
                f"({r['n']} runs, E[random] step@1 = "
                f"{r['random_step_at_1']:.1%})",
                "",
                "| predictor | class | step@1 | abs. dist <= 2 | agent@1 |",
                "|---|---|---|---|---|",
            ]
            for name in PREDICTORS:
                s1, d2, a1 = r["predictors"][name]
                cls = ("baseline" if name in BASELINES
                       else "content" if name in CONTENT else "structure")
                lines.append(
                    f"| {name} | {cls} | {s1 / r['n']:.1%} "
                    f"| {d2 / r['n']:.1%} | {a1 / r['n']:.1%} |")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", help="L0 ledgers from adapters.whowhen")
    ap.add_argument("content_dir",
                    help="content sidecars from adapters.whowhen_content")
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    keys = sorted(
        f[: -len(".content.jsonl")] for f in os.listdir(args.content_dir)
        if f.endswith(".content.jsonl")
    )
    results = [evaluate_variant(args.ledger_dir, args.content_dir, key)
               for key in keys]

    md = render_markdown(results)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
