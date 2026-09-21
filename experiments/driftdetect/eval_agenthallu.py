"""E4b: hallucination detection and localization on AgentHallu.

The first corpus in this paper's attribution family WITH a clean side
(443 hallucinated / 250 clean across 7 frameworks), so the multi-agent
/ attribution row gets real detection rates for the first time — and
the corpus is used for paper measurements only (adapter docstring).

Two measurements, two protocols:

1. DETECTION (dev/eval protocol — the rule was developed on the ~20%
   dev split, sha256(run_id) % 5, shared ``is_dev``; frozen
   2026-09-21). One deterministic cross-channel consistency rule:

       unacknowledged_error — some tool-response step matches the
       error signature AND the run's final agent message contains no
       acknowledgment vocabulary.

   This is detector TYPE three in the follow-up's inventory: not a
   distribution, not a content pattern alone, but a *consistency check
   between rungs* (L2 evidence vs the L3 claim). A candidate
   ``unsupported_number`` rule (final-answer numbers absent from all
   evidence) was dropped on dev as a false-positive source, like E1b's
   test_script_write.

2. LOCALIZATION TRANSFER (whole corpus held-out — nothing was
   developed here): E4's frozen Who&When predictors applied verbatim
   to the hallucinated runs with a valid ``hallucination_step``
   (source coordinates, 1-based), plus ONE re-instantiated variant,
   ``first_worker_local`` (worker = role not containing
   "orchestrator", not user/human/system) — the per-deployment
   re-authoring the TRACE transfer showed is the part that does not
   travel. Predictions map to source step numbers before comparison.

HONESTY NOTES. (1) The detection rule needs the L2 channel: four of
the seven frameworks log content only, and the rule cannot fire there
— visible as near-zero detection at zero FPR. That is the finding, not
a bug: the observability floor of the *log format* caps every detector
above it. (2) Where the rule fires, its FPR is intrinsic, not tunable:
clean runs also hit tool errors and also leave them unverbalized
(BFCL dev: 36%); the semantic core — is the final claim *false*? —
stays out of deterministic reach, as in E3/E4. (3) ~40% of
hallucinated runs carry no step annotation; localization is measured
on the annotated subset. (4) Small per-framework clean sides
(OpenManus: 20) make single-framework FPR fragile; the aggregate row
carries the weight.

Usage:
    python3 -m driftdetect.eval_agenthallu <ledger-dir> [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

from .eval_l3_terminalwrench import is_dev
from .eval_whowhen_content import PREDICTORS, predict

# Frozen 2026-09-21, developed on the DEV split only (module docstring).
ERROR_SIGNATURE = re.compile(
    r'"error"|\berror\b|not found|no such file|failed', re.IGNORECASE)
ACK_SIGNATURE = re.compile(
    r"\b(error|fail|cannot|could not|unable|not possible|apolog|sorry"
    r"|no such)\b", re.IGNORECASE)

TRANSFER_PREDICTORS = PREDICTORS + ("first_worker_local",)


def final_message(seq: list[dict]) -> str:
    """The run's last non-empty agent message (l3)."""
    for line in reversed(seq):
        if line["l3_text"].strip():
            return line["l3_text"]
    return ""


def unacknowledged_error(seq: list[dict]) -> bool:
    """The frozen detection rule (module docstring)."""
    has_error = any(ERROR_SIGNATURE.search(line["l2_text"])
                    for line in seq if line["l2_text"].strip())
    return has_error and not ACK_SIGNATURE.search(final_message(seq))


def is_worker_local(role: str) -> bool:
    """The re-instantiated worker notion for this corpus's role
    spellings ('MagenticOneOrchestrator', ...)."""
    low = role.lower()
    return ("orchestrator" not in low
            and low not in ("user", "human", "system"))


def load_runs(ledger_dir: str, key: str):
    with open(os.path.join(ledger_dir, f"{key}.labels.json"),
              encoding="utf-8") as fh:
        labels = json.load(fh)
    runs: dict[str, list] = defaultdict(list)
    with open(os.path.join(ledger_dir, f"{key}.content.jsonl"),
              encoding="utf-8") as fh:
        for raw in fh:
            line = json.loads(raw)
            runs[line["run_id"]].append(line)
    for seq in runs.values():
        seq.sort(key=lambda x: x["step_index"])
    return runs, labels


def evaluate_detection(runs: dict, labels: dict, key: str) -> list[dict]:
    rows = []
    for split, keep in (("eval", lambda rid: not is_dev(rid)),
                        ("dev", is_dev)):
        n_hall = tp = n_clean = fp = 0
        for rid, label in labels.items():
            if not keep(rid) or rid not in runs:
                continue
            hit = unacknowledged_error(runs[rid])
            if label["is_hallucination"]:
                n_hall += 1
                tp += hit
            else:
                n_clean += 1
                fp += hit
        rows.append({
            "framework": key, "split": split,
            "n_hall": n_hall, "n_clean": n_clean, "tp": tp, "fp": fp,
        })
    return rows


def evaluate_localization(runs: dict, labels: dict, key: str) -> dict:
    """E4-predictor transfer on the step-annotated hallucinated runs;
    whole corpus, held-out by construction."""
    per = {name: [0, 0] for name in TRANSFER_PREDICTORS}  # step@1, |d|<=2
    n = 0
    inv_n_sum = 0.0
    for rid, label in labels.items():
        if not label["is_hallucination"]:
            continue
        target = label["hallucination_step"]
        seq = runs.get(rid, [])
        source_steps = [line["step_source"] for line in seq]
        if target is None or target not in source_steps:
            continue
        n += 1
        inv_n_sum += 1.0 / len(seq)
        # E4 predictors read (step_index, seam_label, text); feed the
        # role as seam label and the agent text as content.
        e4_seq = [(line["step_index"], line["role"], line["l3_text"])
                  for line in seq]
        preds = predict(e4_seq)
        workers = [line["step_index"] for line in seq
                   if is_worker_local(line["role"])]
        preds["first_worker_local"] = (workers[0] if workers
                                       else e4_seq[0][0])
        by_index = {line["step_index"]: line["step_source"] for line in seq}
        for name, p in preds.items():
            predicted_source = by_index.get(p)
            if predicted_source is None:
                continue
            per[name][0] += (predicted_source == target)
            per[name][1] += abs(predicted_source - target) <= 2
    return {"framework": key, "n": n,
            "random_step_at_1": inv_n_sum / n if n else 0.0,
            "predictors": per}


def render_markdown(det: list[list[dict]], loc: list[dict]) -> str:
    lines = [
        "# E4b: hallucination detection and localization on AgentHallu",
        "",
        "Paper-use-only corpus (adapter docstring). Detection: one frozen",
        "cross-channel rule (tool-response error, unacknowledged in the",
        "final message), developed on the ~20% dev split; 'eval' is the",
        "held-out measurement. Localization: E4's frozen Who&When",
        "predictors transferred verbatim (whole corpus held-out) plus the",
        "re-instantiated first_worker_local; targets are the corpus's",
        "1-based source steps on annotated hallucinated runs.",
        "",
        "## Detection (unacknowledged_error)",
        "",
        "| framework | split | hallucinated | clean | detection | FPR |",
        "|---|---|---|---|---|---|",
    ]
    totals: dict[str, list[int]] = {"eval": [0, 0, 0, 0],
                                    "dev": [0, 0, 0, 0]}
    for rows in det:
        for r in rows:
            t = totals[r["split"]]
            t[0] += r["n_hall"]
            t[1] += r["n_clean"]
            t[2] += r["tp"]
            t[3] += r["fp"]
            lines.append(
                f"| {r['framework']} | {r['split']} | {r['n_hall']} "
                f"| {r['n_clean']} "
                f"| {r['tp'] / r['n_hall']:.1%} "
                f"| {r['fp'] / r['n_clean']:.1%} |")
    for split in ("eval", "dev"):
        n_hall, n_clean, tp, fp = totals[split]
        lines.append(
            f"| **all** | {split} | {n_hall} | {n_clean} "
            f"| {tp / n_hall:.1%} | {fp / n_clean:.1%} |")
    lines += [
        "",
        "## Localization transfer (annotated hallucinated runs)",
        "",
        "| framework | runs | E[random] | "
        + " | ".join(TRANSFER_PREDICTORS) + " |",
        "|---|---|---|" + "---|" * len(TRANSFER_PREDICTORS),
    ]
    for r in loc:
        if not r["n"]:
            continue
        cells = []
        for name in TRANSFER_PREDICTORS:
            s1, _ = r["predictors"][name]
            cells.append(f"{s1 / r['n']:.0%}")
        lines.append(f"| {r['framework']} | {r['n']} "
                     f"| {r['random_step_at_1']:.0%} | "
                     + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir",
                    help="content ledgers from adapters.agenthallu")
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    keys = sorted(
        f[: -len(".content.jsonl")] for f in os.listdir(args.ledger_dir)
        if f.endswith(".content.jsonl")
    )
    det = []
    loc = []
    for key in keys:
        runs, labels = load_runs(args.ledger_dir, key)
        det.append(evaluate_detection(runs, labels, key))
        loc.append(evaluate_localization(runs, labels, key))

    md = render_markdown(det, loc)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
