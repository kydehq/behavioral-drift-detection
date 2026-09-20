"""E3: what content access buys on TRAIL's annotated error mass (L1/L2).

The companion's L0 measurement (eval_trail) established that the
runtime ``status_code`` carries ~6% of the human-annotated error mass.
E3 asks how much of the remaining ~94% becomes visible with content in
view — and what the corpus's *true context length* (the spans' recorded
prompt-token counts, an L1 quantity) does to the decay picture the L0
step-index proxy painted.

Three measurements, one frozen protocol (signatures frozen 2026-09-20,
developed on the DEV split only — the same sha256(run_id) % 5 protocol
as the other follow-up experiments, ``is_dev`` imported, not copied):

1. L2 PER-LOCATION COVERAGE. Six error-signature families over the
   annotated span's own stored outputs (``l2_text``/``l3_text``), and a
   3-span downstream window. Expectation set by dev: near nothing —
   in this scaffold the annotated span's own outputs rarely contain
   the failure evidence.
2. L1 REPLAY DELTA ATTRIBUTION. The smolagents scaffold routes tool
   observations into the *next prompt*: execution-error strings live
   almost exclusively in LLM ``l1_text`` (the prompt replay), where
   history accumulates and naive matching saturates. The deterministic
   fix: an annotated location is credited iff the count of
   execution-signature matches in the first LLM prompt *after* the
   location exceeds the count in the last LLM prompt at-or-before it —
   new error content entered the boundary right there. Negative-span
   rate reported as the noise floor.
3. TRUE-CONTEXT-LENGTH PROFILE (corpus description, no split): the
   annotated-error density per model call, binned by recorded prompt
   tokens and, for contrast, by step index with the bin's median
   prompt tokens. This is where L1 corrects L0: the companion's rising
   step curve is the *status* signal (runtime tool failures over all
   spans); the human-annotated mass per model call FALLS with true
   context length — the two error masses diverge, and only content
   access shows it.

HONESTY NOTES. (1) 148 runs, 144 of them annotated with errors: no
detection-rate claims, corpus description and coverage accounting only
(the eval_trail note applies). (2) The channel structure is
scaffold-specific: which rung sees the evidence is decided by where
smolagents routes observations, not by the ladder — on a scaffold that
stores tool results as span outputs, measurement 2 would be an L2
measurement. (3) Delta attribution credits adjacent new-error content;
it is a boundary-timing argument, not causal proof. (4) The annotated
categories are semantic judgments (formatting, instruction
non-compliance, goal deviation ...); the deterministic rules recover
only the execution-shaped slice, and SWE Bench's dev split already
shows the noise floor — both are the finding, not a tuning failure.
(5) The front-loaded annotated density may partly reflect where
annotators localize errors, not only where errors happen.

Usage:
    python3 -m driftdetect.eval_trail_content <ledger-dir> <content-dir>
        [--out results.md]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

from .eval_l3_terminalwrench import is_dev

# Frozen 2026-09-20, developed on the DEV split only (module docstring).
SIGNATURES: dict[str, str] = {
    "exec_error":  (r"Error when executing|Code execution failed"
                    r"|InterpreterError|Traceback \(most recent call last\)"
                    r"|Error in code parsing"),
    "py_exception": (r"\b(TypeError|ValueError|KeyError|AttributeError"
                     r"|IndexError|NameError|SyntaxError"
                     r"|ModuleNotFoundError)\b"),
    "http_fail":   r"rate.?limit|too many requests|HTTP error|status.code [45]\d\d",
    "timeout":     r"\btime[d]?.?out\b",
    "auth":        r"unauthorized|forbidden|authentication|api.key",
    "not_found":   r"\b404\b|not found|no such file",
}
_COMPILED = {name: re.compile(rx, re.IGNORECASE)
             for name, rx in SIGNATURES.items()}
# Measurement 2 uses only the execution family: it is the one whose
# strings the scaffold demonstrably replays into the next prompt.
_EXEC = _COMPILED["exec_error"]

WINDOW = 3            # downstream spans for measurement 1's relaxed row
TOKEN_BIN_BASE = 2000  # token bins: <2k, then doubling


def matched_signatures(text: str) -> list[str]:
    """Names of the frozen signature families that match, in order."""
    return [name for name, rx in _COMPILED.items() if rx.search(text)]


def output_text(line: dict) -> str:
    """The span's stored outputs — the L2/L3 side, never the prompt."""
    return (line["l2_text"] or "") + "\n" + (line["l3_text"] or "")


def norm_category(raw) -> str:
    """The corpus's category spellings vary; fold the variants."""
    return ((raw or "").strip().lower().rstrip("s")
            .replace("failures", "failure"))


def exec_prompt_counts(lines: list[dict]) -> list[int | None]:
    """Per line: execution-signature match count in an LLM prompt, else
    None. Computed once per run — the prompts are large and the delta
    rule is asked per location."""
    return [len(_EXEC.findall(line["l1_text"] or ""))
            if line["kind"] == "LLM" else None
            for line in lines]


def exec_delta_covered(index: int, counts: list[int | None]) -> bool:
    """Measurement 2's credit rule for the location at ``index``.

    True iff the first LLM prompt after the location contains more
    execution-signature matches than the last LLM prompt at-or-before
    it (module docstring). ``counts`` comes from
    ``exec_prompt_counts`` on the run's lines.
    """
    before = 0
    for j in range(index, -1, -1):
        if counts[j] is not None:
            before = counts[j]
            break
    for j in range(index + 1, len(counts)):
        if counts[j] is not None:
            return counts[j] > before
    return False


def token_bin(tokens: int) -> int:
    """<2k -> -1, then doubling bins: 2k-4k -> 0, 4k-8k -> 1, ..."""
    if tokens < TOKEN_BIN_BASE:
        return -1
    return (tokens // TOKEN_BIN_BASE).bit_length() - 1


def token_bin_label(b: int) -> str:
    if b < 0:
        return f"0–{TOKEN_BIN_BASE:,}"
    return f"{TOKEN_BIN_BASE * 2 ** b:,}–{TOKEN_BIN_BASE * 2 ** (b + 1):,}"


def load_runs(ledger_dir: str, content_dir: str, key: str):
    """(runs, labels): run_id -> ordered [(span_id, sidecar line)]."""
    with open(os.path.join(ledger_dir, f"{key}.labels.json"),
              encoding="utf-8") as fh:
        labels = json.load(fh)
    runs: dict[str, list] = defaultdict(list)
    ledger_path = os.path.join(ledger_dir, f"{key}.jsonl")
    content_path = os.path.join(content_dir, f"{key}.content.jsonl")
    with open(ledger_path, encoding="utf-8") as lf, \
            open(content_path, encoding="utf-8") as cf:
        for lraw, craw in zip(lf, cf):
            rec = json.loads(lraw)
            line = json.loads(craw)
            if (rec["run_id"], rec["step_index"]) != (line["run_id"],
                                                      line["step_index"]):
                raise ValueError("ledger/sidecar misalignment")
            line["status"] = rec["status"]
            runs[rec["run_id"]].append((rec["meta"]["span_id"], line))
    return runs, labels


def evaluate_coverage(runs: dict, labels: dict, key: str) -> dict:
    """Measurements 1 and 2: dev/eval rows + eval per-category table."""
    rows = []
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    #  [n, own, window, l1_delta] on the eval split
    for split, keep in (("eval", lambda rid: not is_dev(rid)),
                        ("dev", is_dev)):
        n = own = win = delta = on_status = 0
        neg_n = neg_own = neg_win = neg_delta = 0
        for rid, label in labels.items():
            if not keep(rid) or rid not in runs:
                continue
            seq = runs[rid]
            index_of = {sid: i for i, (sid, _) in enumerate(seq)}
            lines = [line for _, line in seq]
            counts = exec_prompt_counts(lines)
            annotated = {e["location"] for e in label["errors"]}
            for err in label["errors"]:
                i = index_of.get(err["location"])
                if i is None:
                    continue
                n += 1
                own_hit = bool(matched_signatures(output_text(lines[i])))
                win_hit = own_hit or any(
                    matched_signatures(output_text(lines[j]))
                    for j in range(i + 1, min(i + 1 + WINDOW, len(lines))))
                delta_hit = exec_delta_covered(i, counts)
                status_hit = lines[i]["status"] == "error"
                own += own_hit
                win += win_hit
                delta += delta_hit
                on_status += status_hit
                if split == "eval":
                    row = by_category[norm_category(err["category"])]
                    row[0] += 1
                    row[1] += own_hit
                    row[2] += win_hit
                    row[3] += delta_hit
            own_hits = [bool(matched_signatures(output_text(line)))
                        for line in lines]
            for sid, line in seq:
                if sid in annotated:
                    continue
                i = index_of[sid]
                neg_n += 1
                neg_own += own_hits[i]
                neg_win += any(
                    own_hits[j]
                    for j in range(i, min(i + 1 + WINDOW, len(lines))))
                neg_delta += exec_delta_covered(i, counts)
        rows.append({
            "dataset": key, "split": split, "n_locations": n,
            "on_status": on_status, "own": own, "window": win,
            "l1_delta": delta, "neg_n": neg_n, "neg_own": neg_own,
            "neg_window": neg_win, "neg_delta": neg_delta,
        })
    return {"rows": rows, "by_category": dict(by_category)}


def context_profile(runs: dict, labels: dict, key: str) -> dict:
    """Measurement 3 (whole corpus): density by tokens and by step."""
    annotated = {(rid, e["location"])
                 for rid, label in labels.items() for e in label["errors"]}
    by_tokens: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    by_step: dict[int, list] = defaultdict(lambda: [0, 0, []])
    for rid, seq in runs.items():
        for step, (sid, line) in enumerate(seq):
            if line["kind"] != "LLM" or not line["tokens_prompt"]:
                continue
            hit = (rid, sid) in annotated
            tb = token_bin(line["tokens_prompt"])
            by_tokens[tb][0] += 1
            by_tokens[tb][1] += hit
            sb = step // 10
            by_step[sb][0] += 1
            by_step[sb][1] += hit
            by_step[sb][2].append(line["tokens_prompt"])
    return {"dataset": key, "by_tokens": dict(by_tokens),
            "by_step": {b: (n, a, sorted(t)[len(t) // 2])
                        for b, (n, a, t) in by_step.items() if n >= 20}}


def _row(cells) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render_markdown(coverage: list[dict], profiles: list[dict]) -> str:
    lines = [
        "# E3: content access vs TRAIL's annotated error mass",
        "",
        f"Frozen signature families ({len(SIGNATURES)}), developed on the",
        "~20% dev split only; 'eval' is the held-out measurement. own =",
        "signatures on the annotated span's stored outputs; window adds",
        f"{WINDOW} downstream spans; L1 delta = new execution-error content",
        "in the next prompt (module docstring). on-status is the L0",
        "baseline restricted to the same locations. Negative rates are the",
        "same predicates on non-annotated spans — the noise floor. 148",
        "runs: coverage accounting, not detection rates.",
        "",
        "## Per-location coverage of the annotated error mass",
        "",
        _row(["dataset", "split", "locations", "on-status (L0)",
              "own outputs", f"window {WINDOW}", "L1 delta",
              "neg own", f"neg window {WINDOW}", "neg L1 delta"]),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for res in coverage:
        for r in res["rows"]:
            n = r["n_locations"] or 1
            lines.append(_row([
                r["dataset"], r["split"], r["n_locations"],
                f"{r['on_status'] / n:.1%}", f"{r['own'] / n:.1%}",
                f"{r['window'] / n:.1%}", f"{r['l1_delta'] / n:.1%}",
                f"{r['neg_own'] / max(r['neg_n'], 1):.1%}",
                f"{r['neg_window'] / max(r['neg_n'], 1):.1%}",
                f"{r['neg_delta'] / max(r['neg_n'], 1):.1%}",
            ]))
    lines += [
        "",
        "## Per-category coverage (eval split)",
        "",
        _row(["dataset", "category", "locations", "own", f"window {WINDOW}",
              "L1 delta"]),
        "|---|---|---|---|---|---|",
    ]
    for res in coverage:
        key = res["rows"][0]["dataset"]
        for cat, (n, own, win, delta) in sorted(
                res["by_category"].items(), key=lambda kv: -kv[1][0]):
            lines.append(_row([key, cat, n, f"{own / n:.0%}",
                               f"{win / n:.0%}", f"{delta / n:.0%}"]))
    for prof in profiles:
        lines += [
            "",
            f"## True-context-length profile — {prof['dataset']}"
            " (whole corpus, LLM calls)",
            "",
            _row(["prompt tokens", "calls", "annotated per call"]),
            "|---|---|---|",
        ]
        for b in sorted(prof["by_tokens"]):
            n, a = prof["by_tokens"][b]
            lines.append(_row([token_bin_label(b), n, f"{a / n:.3f}"]))
        lines += [
            "",
            _row(["steps in run", "calls", "annotated per call",
                  "median prompt tokens"]),
            "|---|---|---|---|",
        ]
        for b in sorted(prof["by_step"]):
            n, a, med = prof["by_step"][b]
            lines.append(_row([f"{b * 10}–{b * 10 + 9}", n,
                               f"{a / n:.3f}", f"{med:,}"]))
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger_dir", help="L0 ledgers from adapters.trail")
    ap.add_argument("content_dir",
                    help="content sidecars from adapters.trail_content")
    ap.add_argument("--out", help="write the markdown tables here as well")
    args = ap.parse_args(argv)

    keys = sorted(
        f[: -len(".content.jsonl")] for f in os.listdir(args.content_dir)
        if f.endswith(".content.jsonl")
    )
    coverage = []
    profiles = []
    for key in keys:
        runs, labels = load_runs(args.ledger_dir, args.content_dir, key)
        coverage.append(evaluate_coverage(runs, labels, key))
        profiles.append(context_profile(runs, labels, key))

    md = render_markdown(coverage, profiles)
    print(md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"written: {args.out}")


if __name__ == "__main__":
    main()
