"""TRAIL agent traces -> boundary call record ledgers.

Source: github.com/patronus-ai/trail-benchmark, checkout ``benchmarking/``:
``data/{GAIA,SWE Bench}/<trace_id>.json`` holds one OpenTelemetry trace per
task run — exactly one root span, children nested recursively under
``child_spans`` (148 traces / 4,626 spans in the checkout we converted;
smolagents scaffold traced via OpenInference).
``processed_annotations_{gaia,swe_bench}/<trace_id>.json`` holds the human
error annotations: ``errors[]`` with ``category``, ``location`` (a span id)
and ``impact``, plus per-trace scores.

Why this corpus: its spans carry a real per-operation ``status_code``
(Ok 3,665 / Unset 524 / Error 437 in our checkout) — the per-call status
signal the SWE-bench trajectories lack, and the input the error-rate /
context-decay detector consumes.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per span, at every depth. The annotations address spans
  of every depth (839 of the 841 ``location`` ids resolve into the span
  trees, frames included) and 257 of the 437 Error statuses sit on
  non-leaf frames ("Step N", ``CodeAgent.run``); converting leaves only
  would orphan those labels and drop most of the status signal. ``tool``
  is ``span_name`` verbatim — including the index-bearing step frames
  ("Step 5"). This corpus targets the error-rate detector, which never
  reads tool identity; a distributional detector over this ledger would
  first have to canonicalize the step-frame names.
- Order: spans sorted by their ISO ``timestamp``, depth-first position as
  the tie-break; ``step_index`` = rank; ``ts`` = epoch seconds of that
  timestamp. Deterministic from the source; no detector reads ``ts``.
- ``status`` is "error" iff ``status_code`` == "Error", else "ok".
  "Unset" means the instrumentation recorded no verdict; it is mapped to
  "ok" because it is the absence of a failure signal, not evidence of one.
- ``duration_ms`` parses the span's ISO-8601 ``duration`` ("PT1M48.75S");
  an unparseable duration becomes 0.0.
- ``agent_id`` is the benchmark key ("gaia" / "swe_bench") — the
  deployment identity here is the per-benchmark scaffold. ``model``
  carries the span attribute ``llm.model_name`` where the span has one
  (model-call spans), else ""; ``model_version`` stays "".
- ``run_id`` = ``goal_id`` = trace id: the corpus has exactly one run per
  task, so run and goal coincide.
- ``meta`` carries the source ``span_id`` so the labels' ``location``
  references stay resolvable against the ledger (an identifier, not
  content; ``meta`` is outside record equality and never read by a
  detector).

Ground truth goes to a labels sidecar per benchmark, keyed by run_id:
the annotated errors (``category``/``location``/``impact`` verbatim; the
free-text ``evidence``/``description`` stay in the source), the first
``scores`` entry verbatim, and counts (records, status errors, resolved
locations). One annotation file in the corpus is JSON with a trailing
comma; the loader strips trailing commas before ``]``/``}`` and nothing
else.

CLI::

    python3 -m driftdetect.adapters.trail <trail-repo>/benchmarking -o <outdir>

writes ``<outdir>/{gaia,swe_bench}.jsonl``, ``.labels.json`` and a
``manifest.json`` with the sha256 of every output file — the fingerprint
a verdict names its input by.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re

from ..records import CallRecord, write_jsonl

# (data directory name, ledger/annotation key)
DATASETS = (("GAIA", "gaia"), ("SWE Bench", "swe_bench"))
TS_FALLBACK = 1_760_000_000.0   # only if a span lacks a parsable timestamp

_DURATION = re.compile(
    r"^P(?:(?P<d>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<h>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<m>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<s>\d+(?:\.\d+)?)S)?)?$"
)
_TRAILING_COMMA = re.compile(r",(\s*[\]}])")


def duration_ms(raw) -> float:
    """ISO-8601 duration ("PT1M48.75S") -> milliseconds; unparseable -> 0.0."""
    if not isinstance(raw, str):
        return 0.0
    m = _DURATION.match(raw)
    if not m or not any(m.groups()):
        return 0.0
    d, h, mi, s = (float(g) if g else 0.0
                   for g in (m.group("d"), m.group("h"),
                             m.group("m"), m.group("s")))
    return (d * 86400.0 + h * 3600.0 + mi * 60.0 + s) * 1000.0


def load_annotation(path: str) -> dict:
    """Load an annotation file; tolerate the corpus's one trailing comma."""
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", txt))


def flatten_spans(trace: dict) -> list[dict]:
    """Depth-first pre-order flattening of the trace's span tree."""
    if not isinstance(trace, dict) or not isinstance(trace.get("spans"), list):
        raise ValueError("not a TRAIL trace")
    out: list[dict] = []

    def walk(span) -> None:
        if not isinstance(span, dict):
            raise ValueError("malformed span")
        out.append(span)
        for child in span.get("child_spans") or []:
            walk(child)

    for root in trace["spans"]:
        walk(root)
    return out


def _params_hash(attrs: dict) -> str:
    canon = json.dumps(attrs, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _epoch(raw, fallback: float) -> float:
    if isinstance(raw, str):
        try:
            return datetime.datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    return fallback


def convert_trace(
    trace: dict, annotation: dict | None, dataset_key: str
) -> tuple[list[CallRecord], dict]:
    """One raw trace + its (optional) annotation -> (records, label)."""
    spans = flatten_spans(trace)
    run_id = str(trace.get("trace_id") or "")
    if not run_id:
        raise ValueError("trace without trace_id")

    ordered = sorted(
        ((_epoch(s.get("timestamp"), TS_FALLBACK + i), i, s)
         for i, s in enumerate(spans)),
        key=lambda t: (t[0], t[1]),
    )
    records: list[CallRecord] = []
    span_ids: set = set()
    error_span_ids: set = set()
    for step_index, (epoch, _, span) in enumerate(ordered):
        attrs = span.get("span_attributes") or {}
        status = "error" if span.get("status_code") == "Error" else "ok"
        sid = span.get("span_id")
        span_ids.add(sid)
        if status == "error":
            error_span_ids.add(sid)
        records.append(CallRecord(
            ts=epoch,
            run_id=run_id,
            agent_id=dataset_key,
            model=str(attrs.get("llm.model_name") or ""),
            model_version="",
            goal_id=run_id,
            step_index=step_index,
            tool=str(span.get("span_name") or ""),
            params_hash=_params_hash(attrs),
            status=status,
            duration_ms=duration_ms(span.get("duration")),
            meta={"span_id": sid},
        ))

    ann_errors: list[dict] = []
    scores = None
    n_resolved = 0
    n_on_error_status = 0
    if annotation:
        for err in annotation.get("errors") or []:
            entry = {"category": err.get("category"),
                     "location": err.get("location"),
                     "impact": err.get("impact")}
            if entry["location"] in span_ids:
                n_resolved += 1
                if entry["location"] in error_span_ids:
                    n_on_error_status += 1
            ann_errors.append(entry)
        s = annotation.get("scores") or []
        scores = s[0] if s else None

    label = {
        "dataset": dataset_key,
        "n_calls": len(records),
        "n_error_status": len(error_span_ids),
        "errors": ann_errors,
        "n_errors_annotated": len(ann_errors),
        "n_locations_resolved": n_resolved,
        "n_annotated_on_error_status": n_on_error_status,
        "scores": scores,
    }
    return records, label


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(bench_dir: str, out_dir: str) -> dict:
    """Convert benchmarking/ (data/ + processed_annotations_*/), one ledger
    per benchmark."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(bench_dir), "datasets": {},
                      "n_skipped": 0}

    for data_name, key in DATASETS:
        data_dir = os.path.join(bench_dir, "data", data_name)
        ann_dir = os.path.join(bench_dir, f"processed_annotations_{key}")
        if not os.path.isdir(data_dir):
            continue
        records: list[CallRecord] = []
        labels: dict[str, dict] = {}
        for fname in sorted(os.listdir(data_dir)):
            if not fname.endswith(".json"):
                continue
            trace_id = fname[: -len(".json")]
            ann_path = os.path.join(ann_dir, fname)
            try:
                with open(os.path.join(data_dir, fname), encoding="utf-8") as fh:
                    trace = json.load(fh)
                annotation = (load_annotation(ann_path)
                              if os.path.isfile(ann_path) else None)
                recs, label = convert_trace(trace, annotation, key)
            except (OSError, ValueError, json.JSONDecodeError,
                    UnicodeDecodeError, KeyError, TypeError):
                # one malformed trace must not kill the corpus
                manifest["n_skipped"] += 1
                continue
            if not recs or recs[0].run_id != trace_id:
                # the file name and the embedded trace_id must agree
                manifest["n_skipped"] += 1
                continue
            records.extend(recs)
            labels[trace_id] = label

        if not records:
            continue
        ledger_path = os.path.join(out_dir, f"{key}.jsonl")
        labels_path = os.path.join(out_dir, f"{key}.labels.json")
        n = write_jsonl(records, ledger_path)
        with open(labels_path, "w", encoding="utf-8") as fh:
            json.dump(labels, fh, sort_keys=True, indent=1)
        manifest["datasets"][key] = {
            "ledger": os.path.basename(ledger_path),
            "labels": os.path.basename(labels_path),
            "n_runs": len(labels),
            "n_records": n,
            "sha256_ledger": _sha256_file(ledger_path),
            "sha256_labels": _sha256_file(labels_path),
        }

    manifest["n_runs_total"] = sum(
        d["n_runs"] for d in manifest["datasets"].values())
    manifest["n_records_total"] = sum(
        d["n_records"] for d in manifest["datasets"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bench_dir",
                    help="path to the trail-benchmark repo's benchmarking/ directory")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.bench_dir, args.out)
    print(
        f"{len(manifest['datasets'])} benchmarks, "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
