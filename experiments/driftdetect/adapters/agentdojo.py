"""AgentDojo run files -> boundary call record ledgers.

Source: github.com/ethz-spylab/agentdojo, ``runs/<pipeline>/<suite>/
<user_task>/<attack_type>/<injection_task|none>.json`` — one JSON per run:
the full message transcript plus run-level ground truth (``utility``,
``security``, ``attack_type``). 36,679 runs across 29 pipelines.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per assistant tool call, in transcript order. ``status`` is
  "error" iff the tool-result message matched via ``tool_call_id`` carries a
  non-null error. The source has no abort notion; "abort" never occurs.
- The source has no per-call timestamps. ``ts`` is a deterministic ordering
  index (run index within the pipeline * spacing + step). No detector reads
  ``ts``; it exists so the ledger stays totally ordered and reproducible.
- ``duration`` exists only per run; ``duration_ms`` spreads it uniformly
  over the run's calls.
- ``model`` carries the pipeline name verbatim (that is the model identity
  as published, including defense-variant suffixes); ``model_version`` stays
  "" because the source records none separately.
- ``goal_id`` = "<suite>/<user_task>" — the declared objective of the run.
- Call parameters are hashed (sha256 over canonical JSON of ``args``);
  content never enters the ledger.

Ground truth goes to a labels sidecar per pipeline, keyed by ``run_id``.
Despite its name, AgentDojo's ``security`` field is True when the injection
goal WAS executed (``BaseInjectionTask.security`` docstring: "Returns True if
the injection was executed correctly"), hence ``injection_success = attacked
and security is True``. Verified against the published per-model attack
success rates (GPT-4o ~29%, Claude 3.5 Sonnet ~1%, defenses lowering the
base rate); the opposite reading yields impossible rates near 99%. Benign
runs carry ``security=True`` vacuously and are never read.

CLI::

    python3 -m driftdetect.adapters.agentdojo <agentdojo-repo>/runs -o <outdir>

writes ``<outdir>/<pipeline>.jsonl``, ``<pipeline>.labels.json`` and a
``manifest.json`` with the sha256 of every output file — the fingerprint a
verdict names its input by.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from ..records import CallRecord, write_jsonl

TS_BASE = 1_760_000_000.0   # arbitrary fixed origin; ts is ordering only
TS_RUN_SPACING = 1_000.0    # keeps runs non-overlapping in ts


def _params_hash(args: dict) -> str:
    canon = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _has_error(value) -> bool:
    return value is not None and value != "None" and value != ""


def convert_run(doc: dict, run_id: str, run_index: int) -> tuple[list[CallRecord], dict]:
    """One AgentDojo run document -> (records, label)."""
    errors_by_call_id: dict[str, bool] = {}
    for msg in doc.get("messages", []):
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            errors_by_call_id[msg["tool_call_id"]] = _has_error(msg.get("error"))

    calls = [
        tc
        for msg in doc.get("messages", [])
        if msg.get("role") == "assistant"
        for tc in (msg.get("tool_calls") or [])
    ]

    pipeline = doc["pipeline_name"]
    goal_id = f"{doc['suite_name']}/{doc['user_task_id']}"
    per_call_ms = (float(doc.get("duration") or 0.0) * 1000.0 / len(calls)) if calls else 0.0

    records = [
        CallRecord(
            ts=TS_BASE + run_index * TS_RUN_SPACING + step,
            run_id=run_id,
            agent_id=pipeline,
            model=pipeline,
            model_version="",
            goal_id=goal_id,
            step_index=step,
            tool=call["function"],
            params_hash=_params_hash(call.get("args") or {}),
            status="error" if errors_by_call_id.get(call.get("id")) else "ok",
            duration_ms=per_call_ms,
        )
        for step, call in enumerate(calls)
    ]

    attack_type = doc.get("attack_type")
    attacked = attack_type is not None and attack_type != "None"
    label = {
        "suite": doc["suite_name"],
        "user_task": doc["user_task_id"],
        "attack_type": attack_type if attacked else None,
        "injection_task_id": doc.get("injection_task_id") if attacked else None,
        "attacked": attacked,
        "injection_success": bool(attacked and doc.get("security") is True),
        "utility": bool(doc.get("utility")),
        "run_error": doc.get("error"),
        "n_calls": len(calls),
    }
    return records, label


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(runs_dir: str, out_dir: str) -> dict:
    """Convert all pipelines under runs_dir; returns the manifest."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(runs_dir), "pipelines": {}}

    for pipeline in sorted(os.listdir(runs_dir)):
        pdir = os.path.join(runs_dir, pipeline)
        if not os.path.isdir(pdir):
            continue
        run_files = sorted(
            os.path.relpath(os.path.join(root, f), runs_dir)
            for root, _, files in os.walk(pdir)
            for f in files
            if f.endswith(".json")
        )
        records: list[CallRecord] = []
        labels: dict[str, dict] = {}
        for run_index, rel in enumerate(run_files):
            with open(os.path.join(runs_dir, rel), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            run_id = rel[: -len(".json")]
            recs, label = convert_run(doc, run_id, run_index)
            records.extend(recs)
            labels[run_id] = label

        ledger_path = os.path.join(out_dir, f"{pipeline}.jsonl")
        labels_path = os.path.join(out_dir, f"{pipeline}.labels.json")
        n = write_jsonl(records, ledger_path)
        with open(labels_path, "w", encoding="utf-8") as fh:
            json.dump(labels, fh, sort_keys=True, indent=1)

        manifest["pipelines"][pipeline] = {
            "ledger": os.path.basename(ledger_path),
            "labels": os.path.basename(labels_path),
            "n_runs": len(run_files),
            "n_records": n,
            "sha256_ledger": _sha256_file(ledger_path),
            "sha256_labels": _sha256_file(labels_path),
        }

    manifest["n_runs_total"] = sum(p["n_runs"] for p in manifest["pipelines"].values())
    manifest["n_records_total"] = sum(p["n_records"] for p in manifest["pipelines"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs_dir", help="path to the agentdojo repo's runs/ directory")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.runs_dir, args.out)
    print(
        f"{len(manifest['pipelines'])} pipelines, "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records -> {args.out}"
    )


if __name__ == "__main__":
    main()
