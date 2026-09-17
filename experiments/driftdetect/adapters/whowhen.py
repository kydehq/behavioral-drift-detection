"""Who&When multi-agent failure logs -> boundary call record ledgers.

Source: the HF dataset ``Kevin355/Who_and_When`` (arXiv:2505.00212) —
184 failed multi-agent runs with a human failure attribution per run
(``mistake_agent``, ``mistake_step``, ``mistake_reason``). Two variants
under ``Who&When/``:

- ``Algorithm-Generated`` (126 runs): AG2-style expert teams on GAIA
  questions. Each ``history`` entry carries the speaking agent in
  ``name`` (``Excel_Expert``, ``Computer_terminal``, ... — 191 distinct
  across the corpus, teams are assembled per question).
- ``Hand-Crafted`` (58 runs): Magentic-One runs. There is no ``name``;
  the ``role`` string itself encodes the seam — speaker and routing
  target — e.g. ``Orchestrator (-> WebSurfer)``, ``WebSurfer``,
  ``Orchestrator (thought)``.

Why this corpus: Table 2 calls multi-agent drift "partial: visible if
the seam itself crosses the boundary (tool and delegation routing)".
Here the delegation seam IS the record: every history entry is one
message crossing it, and the ground truth names the agent and step
responsible for the failure.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per ``history`` entry, in order. ``tool`` is the seam
  label verbatim: the ``name`` field (Algorithm-Generated, falling back
  to ``role`` when absent) or the ``role`` string (Hand-Crafted,
  routing target included). Deriving the plain speaker from a
  Hand-Crafted label ("Orchestrator (-> WebSurfer)" -> "Orchestrator")
  is a canonicalization and lives in the eval, not here.
- The source has NO timestamps, NO per-message status, NO model or
  duration fields: ``ts`` is a synthetic ``TS_BASE + step_index``
  (no detector reads ``ts``), ``status`` is always "ok",
  ``duration_ms`` 0.0, ``model``/``model_version`` "".
- ``params_hash`` covers the message content (content itself never
  enters the ledger).
- ``agent_id`` is the variant key ("algorithm-generated" /
  "hand-crafted") — the deployment identity is the scaffold family.
- ``run_id`` = "<variant>/<file stem>"; ``goal_id`` = the source
  ``question_ID``.

Ground truth goes to a labels sidecar per variant, keyed by run_id,
with the attribution fields verbatim (``mistake_agent``,
``mistake_step`` — a string in the source, ``mistake_reason``), the
correctness field under its source spelling (``is_correct`` in
Algorithm-Generated, ``is_corrected`` in Hand-Crafted; every run in
the corpus is a failure), ``level`` where present, and ``n_calls``.

CLI::

    python3 -m driftdetect.adapters.whowhen "<who-and-when>/Who&When" -o <outdir>

writes ``<outdir>/{algorithm-generated,hand-crafted}.jsonl``,
``.labels.json`` and a ``manifest.json`` with the sha256 of every
output file — the fingerprint a verdict names its input by.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from ..records import CallRecord, write_jsonl

# (directory name, ledger/variant key)
VARIANTS = (("Algorithm-Generated", "algorithm-generated"),
            ("Hand-Crafted", "hand-crafted"))
TS_BASE = 1_760_000_000.0   # synthetic: the source has no timestamps


def _params_hash(content) -> str:
    canon = json.dumps({"content": content}, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:12]


def _seam_label(entry: dict) -> str:
    return str(entry.get("name") or entry.get("role") or "")


def convert_run(doc: dict, variant_key: str, run_id: str
                ) -> tuple[list[CallRecord], dict]:
    """One Who&When JSON file -> (records, label)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("history"), list):
        raise ValueError("not a Who&When run")
    goal_id = str(doc.get("question_ID") or "")
    if not goal_id:
        raise ValueError("run without question_ID")

    records: list[CallRecord] = []
    for step_index, entry in enumerate(doc["history"]):
        if not isinstance(entry, dict):
            raise ValueError("malformed history entry")
        tool = _seam_label(entry)
        if not tool:
            continue
        records.append(CallRecord(
            ts=TS_BASE + step_index,
            run_id=run_id,
            agent_id=variant_key,
            model="",
            model_version="",
            goal_id=goal_id,
            step_index=step_index,
            tool=tool,
            params_hash=_params_hash(entry.get("content")),
            status="ok",
            duration_ms=0.0,
        ))

    label = {
        "question_ID": goal_id,
        "variant": variant_key,
        "is_correct": doc.get("is_correct"),
        "is_corrected": doc.get("is_corrected"),
        "level": doc.get("level"),
        "mistake_agent": doc.get("mistake_agent"),
        "mistake_step": doc.get("mistake_step"),
        "mistake_reason": doc.get("mistake_reason"),
        "n_calls": len(records),
    }
    return records, label


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(root_dir: str, out_dir: str) -> dict:
    """Convert both variant directories under root_dir, one ledger each."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(root_dir), "variants": {},
                      "n_skipped": 0}

    for dir_name, key in VARIANTS:
        vdir = os.path.join(root_dir, dir_name)
        if not os.path.isdir(vdir):
            continue
        records: list[CallRecord] = []
        labels: dict[str, dict] = {}
        for fname in sorted(os.listdir(vdir),
                            key=lambda n: (len(n), n)):   # 1.json, 2.json, ...
            if not fname.endswith(".json"):
                continue
            run_id = f"{key}/{fname[: -len('.json')]}"
            try:
                with open(os.path.join(vdir, fname), encoding="utf-8") as fh:
                    doc = json.load(fh)
                recs, label = convert_run(doc, key, run_id)
            except (OSError, ValueError, json.JSONDecodeError,
                    UnicodeDecodeError, KeyError, TypeError):
                # one malformed run must not kill the corpus
                manifest["n_skipped"] += 1
                continue
            if not recs:
                manifest["n_skipped"] += 1
                continue
            records.extend(recs)
            labels[run_id] = label

        if not records:
            continue
        ledger_path = os.path.join(out_dir, f"{key}.jsonl")
        labels_path = os.path.join(out_dir, f"{key}.labels.json")
        n = write_jsonl(records, ledger_path)
        with open(labels_path, "w", encoding="utf-8") as fh:
            json.dump(labels, fh, sort_keys=True, indent=1)
        manifest["variants"][key] = {
            "ledger": os.path.basename(ledger_path),
            "labels": os.path.basename(labels_path),
            "n_runs": len(labels),
            "n_records": n,
            "sha256_ledger": _sha256_file(ledger_path),
            "sha256_labels": _sha256_file(labels_path),
        }

    manifest["n_runs_total"] = sum(
        v["n_runs"] for v in manifest["variants"].values())
    manifest["n_records_total"] = sum(
        v["n_records"] for v in manifest["variants"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root_dir",
                    help="path to the dataset's Who&When directory "
                         "(contains Algorithm-Generated/ and Hand-Crafted/)")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.root_dir, args.out)
    print(
        f"{len(manifest['variants'])} variants, "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
