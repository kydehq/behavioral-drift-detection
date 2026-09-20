"""TRAIL content sidecars: the L1/L2/L3 rungs next to the L0 ledgers.

Follow-up-paper infrastructure (../../paper-followup/): the L0 ledgers
written by ``trail.py`` stay untouched and citable; this module walks
the same ``benchmarking/`` tree and emits one content sidecar line per
L0 record, aligned by (run_id, step_index):

    {"run_id", "step_index", "tool", "kind",
     "l1_text", "l2_text", "l3_text",
     "tokens_prompt", "tokens_completion"}

- ``kind`` — ``openinference.span.kind`` verbatim ("" when absent):
  the eval assigns content to ladder rungs by it, because an LLM
  span's output *is* reasoning text (L3) while a TOOL/CHAIN/AGENT
  span's output is an observation (L2).
- ``l1_text`` — the span's ``input.value`` verbatim ("" when absent):
  what went into the operation, the plain-parameter rung.
- ``l2_text`` — the span's ``output.value`` verbatim ("" when absent):
  what came back across the boundary.
- ``l3_text`` — the concatenated ``llm.output_messages.N.message.content``
  attributes in index order ("" when none): the model's message text
  without the JSON envelope ``output.value`` wraps around it.
- ``tokens_prompt`` / ``tokens_completion`` — the span's recorded
  ``llm.token_count.*`` as integers (null when absent). The corpus
  records them as strings; unparsable values become null. These stand
  in for tokenizing the L1 text: the *true context length* at each
  model call, the quantity the companion's context-decay detector can
  only proxy by step index at L0.

Alignment is guaranteed by construction: the span enumeration reuses
``trail.flatten_spans`` and the same (timestamp, depth-first position)
ordering expression as ``trail.convert_trace``; the unit tests convert
the same synthetic trace through both modules and assert
index-by-index agreement.

Sidecars contain raw source content (model text, tool outputs). Like
the ledgers they live outside the repository
(datasets/raw-fetch/ledger/...), fingerprinted in a manifest.

CLI::

    python3 -m driftdetect.adapters.trail_content <trail-repo>/benchmarking -o <outdir>

writes ``<outdir>/{gaia,swe_bench}.content.jsonl`` and a
``manifest.json`` with the sha256 of every output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re

from .trail import DATASETS, TS_FALLBACK, _epoch, flatten_spans

_OUT_MSG = re.compile(r"^llm\.output_messages\.(\d+)\.message\.content$")


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _int_or_none(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _l3_text(attrs: dict) -> str:
    parts = sorted(
        (int(m.group(1)), _text(v))
        for k, v in attrs.items()
        if (m := _OUT_MSG.match(k)) is not None
    )
    return "\n".join(p for _, p in parts if p)


def content_lines(trace: dict, run_id: str) -> list[dict]:
    """One raw TRAIL trace -> sidecar lines aligned with the L0 records."""
    spans = flatten_spans(trace)
    ordered = sorted(
        ((_epoch(s.get("timestamp"), TS_FALLBACK + i), i, s)
         for i, s in enumerate(spans)),
        key=lambda t: (t[0], t[1]),
    )
    lines: list[dict] = []
    for step_index, (_, _, span) in enumerate(ordered):
        attrs = span.get("span_attributes") or {}
        lines.append({
            "run_id": run_id,
            "step_index": step_index,
            "tool": str(span.get("span_name") or ""),
            "kind": str(attrs.get("openinference.span.kind") or ""),
            "l1_text": _text(attrs.get("input.value")),
            "l2_text": _text(attrs.get("output.value")),
            "l3_text": _l3_text(attrs),
            "tokens_prompt": _int_or_none(attrs.get("llm.token_count.prompt")),
            "tokens_completion": _int_or_none(
                attrs.get("llm.token_count.completion")),
        })
    return lines


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(bench_dir: str, out_dir: str) -> dict:
    """Walk benchmarking/ exactly like the L0 adapter, one sidecar per
    benchmark."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(bench_dir), "datasets": {},
                      "n_skipped": 0}

    for data_name, key in DATASETS:
        data_dir = os.path.join(bench_dir, "data", data_name)
        if not os.path.isdir(data_dir):
            continue
        path = os.path.join(out_dir, f"{key}.content.jsonl")
        n_lines = 0
        n_runs = 0
        with open(path, "w", encoding="utf-8") as out:
            for fname in sorted(os.listdir(data_dir)):
                if not fname.endswith(".json"):
                    continue
                trace_id = fname[: -len(".json")]
                try:
                    with open(os.path.join(data_dir, fname),
                              encoding="utf-8") as fh:
                        trace = json.load(fh)
                    if str(trace.get("trace_id") or "") != trace_id:
                        raise ValueError("trace_id mismatch")
                    lines = content_lines(trace, trace_id)
                except (OSError, ValueError, json.JSONDecodeError,
                        UnicodeDecodeError, KeyError, TypeError):
                    # the same skip contract as the L0 adapter
                    manifest["n_skipped"] += 1
                    continue
                for line in lines:
                    out.write(json.dumps(line, sort_keys=True) + "\n")
                    n_lines += 1
                n_runs += 1

        if not n_lines:
            os.remove(path)
            continue
        manifest["datasets"][key] = {
            "sidecar": os.path.basename(path),
            "n_runs": n_runs,
            "n_lines": n_lines,
            "sha256_sidecar": _sha256_file(path),
        }

    manifest["n_lines_total"] = sum(
        d["n_lines"] for d in manifest["datasets"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bench_dir",
                    help="path to the trail-benchmark repo's benchmarking/ directory")
    ap.add_argument("-o", "--out", required=True,
                    help="output directory for sidecars")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.bench_dir, args.out)
    print(
        f"{len(manifest['datasets'])} benchmarks, "
        f"{manifest['n_lines_total']} sidecar lines "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
