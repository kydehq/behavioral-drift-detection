"""E1 transfer: the frozen Terminal Wrench detectors applied to TRACE.

The E1b rules (eval_l1b_terminalwrench.RULES) and the L3 justification
patterns (eval_l3_terminalwrench.PATTERNS) were developed on Terminal
Wrench's dev split and measured held-out — but the split separates
runs, not tasks, so those numbers are within-task-distribution. This
module measures the stronger claim: both detectors, frozen — not one
regex, threshold, or rule changed — applied to a *different*
reward-hacking corpus (TRACE, adapters.trace), different scaffold
(Claude-Code-shaped toolset vs. plain terminal), different task
population, different hack provenance. The whole corpus is held-out;
there is no TRACE dev split because nothing was developed here.

Rungs measured, per run over the trace content sidecars
(adapters.trace_content):

- L1b — concatenated ``l1_text`` (plain call parameters), flagged at
  >= eval_l1b_terminalwrench.MIN_DISTINCT matching rules.
- L3 — concatenated ``l3_text`` (assistant message text, consecutive
  duplicates collapsed), flagged at >= eval_l3_terminalwrench's
  MIN_DISTINCT matching patterns.

Classes follow eval_trace: hacked = label != "0", clean = label "0".

HONESTY NOTE: TRACE's hacked trajectories differ from Terminal
Wrench's in provenance, and how openly they narrate is a property of
the corpus, not of the detector — a transfer number below the Terminal
Wrench one measures that difference too, not merely rule quality. The
L0 comparison point for this corpus is eval_trace: 0.0% per-run
detection, corpus JSD 0.017.

Usage:
    python3 -m driftdetect.eval_trace_transfer <ledger-dir> <content-dir>
        [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os

from . import eval_l1b_terminalwrench as l1b
from . import eval_l3_terminalwrench as l3
from .adapters.trace import AGENT_ID


def load_labels(ledger_dir: str) -> dict[str, dict]:
    with open(os.path.join(ledger_dir, f"{AGENT_ID}.labels.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def load_texts(content_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """run_id -> (concatenated l1_text, concatenated deduped l3_text)."""
    l1_parts: dict[str, list[str]] = {}
    l3_parts: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    path = os.path.join(content_dir, f"{AGENT_ID}.content.jsonl")
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            line = json.loads(raw)
            rid = line["run_id"]
            if line["l1_text"]:
                l1_parts.setdefault(rid, []).append(line["l1_text"])
            text = line["l3_text"]
            if text and text not in seen.setdefault(rid, set()):
                seen[rid].add(text)
                l3_parts.setdefault(rid, []).append(text)
    return ({rid: "\n".join(p) for rid, p in l1_parts.items()},
            {rid: "\n".join(p) for rid, p in l3_parts.items()})


def evaluate(ledger_dir: str, content_dir: str) -> dict:
    labels = load_labels(ledger_dir)
    l1_texts, l3_texts = load_texts(content_dir)

    rungs = {
        "L1b rules": (l1_texts, l1b.flagged, l1b.matched_rules, l1b.RULES),
        "L3 patterns": (l3_texts, l3.flagged, l3.matched_patterns,
                        l3.PATTERNS),
    }
    rows = []
    coverage: dict[str, dict[str, dict[str, int]]] = {}
    n_clean = n_hacked = 0
    for name, (texts, flag, matcher, ruleset) in rungs.items():
        tp = fp = n_clean = n_hacked = 0
        cov = {r: {"hacked": 0, "clean": 0} for r in ruleset}
        for rid, label in labels.items():
            if label["n_calls"] <= 0:
                continue
            cls = "hacked" if label["hacked"] else "clean"
            text = texts.get(rid, "")
            if cls == "hacked":
                n_hacked += 1
                tp += flag(text)
            else:
                n_clean += 1
                fp += flag(text)
            for rule in matcher(text):
                cov[rule][cls] += 1
        rows.append({
            "rung": name,
            "n_clean": n_clean,
            "n_hacked": n_hacked,
            "detection": tp / n_hacked if n_hacked else None,
            "fpr": fp / n_clean if n_clean else None,
        })
        coverage[name] = cov
    return {"rows": rows, "coverage": coverage,
            "n_clean": n_clean, "n_hacked": n_hacked}


def render_markdown(res: dict, args) -> str:
    lines = [
        "# E1 transfer: frozen Terminal Wrench detectors on TRACE",
        "",
        "The E1b mechanism rules and L3 justification patterns exactly as",
        "frozen on the Terminal Wrench dev split — nothing re-tuned. The",
        "whole TRACE corpus is held-out (module docstring). L0 comparison",
        "point: results/trace-rewardhack.md, 0.0% per-run detection,",
        "corpus JSD 0.017.",
        "",
        "## Per-run verdicts",
        "",
        "| rung | clean runs | hacked runs | detection | FPR |",
        "|---|---|---|---|---|",
    ]
    for r in res["rows"]:
        lines.append(
            f"| {r['rung']} | {r['n_clean']} | {r['n_hacked']} "
            f"| {r['detection']:.1%} | {r['fpr']:.1%} |"
        )
    for rung, cov in res["coverage"].items():
        lines += [
            "",
            f"## Per-rule coverage — {rung} (share of runs matching)",
            "",
            "| rule | hacked | clean |",
            "|---|---|---|",
        ]
        for rule, c in cov.items():
            lines.append(
                f"| {rule} | {c['hacked'] / res['n_hacked']:.1%} "
                f"| {c['clean'] / res['n_clean']:.1%} |"
            )
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", help="TRACE ledger from adapters.trace")
    ap.add_argument("content_dir", help="sidecar from adapters.trace_content")
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    md = render_markdown(evaluate(args.ledger_dir, args.content_dir), args)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
