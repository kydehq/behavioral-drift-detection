"""TRACE coding trajectories -> boundary call record ledgers.

Source: the gated HF dataset ``PatronusAI/trace-dataset`` (CC-BY-SA-4.0,
arXiv:2601.20103) — 517 coding trajectories, 249 benign and 268 reward-
hacked, each a ChatML conversation whose assistant messages carry
``tool_calls`` (``{name, parameters}``) and ``tool_results``
(``{output}``). The dataset ships as one Parquet file; this adapter
reads the JSONL materialization written once by
``datasets/scripts/export_trace_jsonl.py`` (one line per trajectory:
``{"trajectory_id", "label", "conversation"}``, row order preserved) —
Parquet itself is outside the stdlib-only rule of this tree.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per ``tool_calls`` entry of each assistant message, in
  message order. Exactly one call in the corpus sits on a *user*
  message (trajectory_0018 — the human running a command themselves);
  it is not agent behavior and is excluded, so the corpus's 10,324
  calls become 10,323 records. For ``Bash`` the tool is the leading token of
  ``parameters.command`` (``cd``, ``cargo``, ``kubectl``, ... — 74
  distinct tokens) — the same convention as the sweagent and Terminal
  Wrench adapters; the tool name alone is a 10-word vocabulary. All
  other tools (``Edit``, ``Read``, ``Write``, ``Grep``, ``Glob``, ...)
  keep their name verbatim. The parameter hash covers the canonical
  JSON of the full ``parameters``.
- The source has NO timestamps; ``ts`` is a synthetic
  ``TS_BASE + step_index`` so the ledger is totally ordered.
  No detector reads ``ts``.
- ``tool_results`` carry only an ``output`` string — no status field of
  any kind — so ``status`` is always "ok" and error-rate detectors are
  out of scope for this corpus. ``duration_ms`` stays 0.0.
- The records name neither a model nor a scaffold (the toolset is
  Claude-Code-shaped, but that is an observation, not a field), so
  ``agent_id`` is the corpus key "trace" — one undifferentiated
  deployment — and ``model``/``model_version`` stay "".
- ``run_id`` = ``goal_id`` = trajectory id: one run per task, no task
  grouping in the source.

Ground truth goes to the labels sidecar, keyed by run_id, with the
source ``label`` verbatim: "0" is benign; anything else is a comma-
separated list of reward-hacking subcategory codes ("1.1.2, 1.2.1").
The sidecar adds the parsed ``codes`` list and ``hacked`` boolean;
which side an experiment counts a run on stays an experiment decision
(``eval_trace``).

CLI::

    python3 -m driftdetect.adapters.trace <trace-rewardhack>/trajectories.jsonl -o <outdir>

writes ``<outdir>/trace.jsonl``, ``trace.labels.json`` and a
``manifest.json`` with the sha256 of every output file — the
fingerprint a verdict names its input by.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from ..records import CallRecord, write_jsonl

TS_BASE = 1_760_000_000.0   # synthetic: the source has no timestamps
AGENT_ID = "trace"


def _params_hash(params: dict) -> str:
    canon = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _tool_name(call: dict) -> str:
    name = call.get("name") or ""
    command = (call.get("parameters") or {}).get("command")
    if name == "Bash" and isinstance(command, str) and command.split():
        return command.split()[0]
    return name


def convert_trajectory(doc: dict) -> tuple[list[CallRecord], dict]:
    """One exported trajectory line -> (records, label)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("conversation"), list):
        raise ValueError("not an exported TRACE trajectory")
    run_id = str(doc.get("trajectory_id") or "")
    if not run_id:
        raise ValueError("trajectory without trajectory_id")

    records: list[CallRecord] = []
    step_index = 0
    for message in doc["conversation"]:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            tool = _tool_name(call)
            if not tool:
                continue
            records.append(CallRecord(
                ts=TS_BASE + step_index,
                run_id=run_id,
                agent_id=AGENT_ID,
                model="",
                model_version="",
                goal_id=run_id,
                step_index=step_index,
                tool=tool,
                params_hash=_params_hash(call.get("parameters") or {}),
                status="ok",
                duration_ms=0.0,
            ))
            step_index += 1

    raw_label = str(doc.get("label"))
    hacked = raw_label != "0"
    label = {
        "label": raw_label,
        "hacked": hacked,
        "codes": [c.strip() for c in raw_label.split(",")] if hacked else [],
        "n_messages": len(doc["conversation"]),
        "n_calls": len(records),
    }
    return records, label


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_export(export_path: str, out_dir: str) -> dict:
    """Convert the exported trajectories.jsonl into one ledger."""
    os.makedirs(out_dir, exist_ok=True)
    records: list[CallRecord] = []
    labels: dict[str, dict] = {}
    n_skipped = 0

    with open(export_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                recs, label = convert_trajectory(json.loads(line))
            except (ValueError, json.JSONDecodeError, KeyError, TypeError):
                # one malformed trajectory must not kill the corpus
                n_skipped += 1
                continue
            if not recs:
                n_skipped += 1
                continue
            records.extend(recs)
            labels[recs[0].run_id] = label

    ledger_path = os.path.join(out_dir, f"{AGENT_ID}.jsonl")
    labels_path = os.path.join(out_dir, f"{AGENT_ID}.labels.json")
    n = write_jsonl(records, ledger_path)
    with open(labels_path, "w", encoding="utf-8") as fh:
        json.dump(labels, fh, sort_keys=True, indent=1)

    manifest = {
        "source": os.path.abspath(export_path),
        "sha256_source": _sha256_file(export_path),
        "models": {
            AGENT_ID: {
                "ledger": os.path.basename(ledger_path),
                "labels": os.path.basename(labels_path),
                "n_runs": len(labels),
                "n_records": n,
                "sha256_ledger": _sha256_file(ledger_path),
                "sha256_labels": _sha256_file(labels_path),
            }
        },
        "n_skipped": n_skipped,
        "n_runs_total": len(labels),
        "n_records_total": n,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_path",
                    help="trajectories.jsonl written by export_trace_jsonl.py")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_export(args.export_path, args.out)
    print(
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
