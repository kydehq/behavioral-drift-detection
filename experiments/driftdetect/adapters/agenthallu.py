"""AgentHallu trajectories -> content ledgers (follow-up corpus).

Source: github.com/liuxuannan/AgentHallu (arXiv:2601.06818), checkout
``AgentHallu/<Framework>/<nnn>.json`` — 693 annotated trajectories
across 7 agent frameworks, **443 hallucinated / 250 clean**: the first
attribution-adjacent corpus with a clean side, so real detection rates
become possible for the multi-agent/attribution row.

USAGE RESTRICTION (decided 2026-09-21): paper measurements only. The
repository's LICENSE file says CC BY 4.0 while the project page says
CC BY-NC-SA 4.0; under either, the ledgers written here (they contain
the raw trajectory content) are derivatives — they live outside the
repository and are never redistributed. Results tables and fingerprints
only.

Why there is no L0 ledger: four of the seven frameworks (Magentic_One,
Octotools, OpenDeepSearch, SmolAgents) log *content only* — no tool
names, no per-call status, nothing a boundary record could be built
from without invention. That observation belongs in the paper's cost
section: public agent logs frequently do not even contain the boundary
layer. This adapter therefore writes a single *content* ledger per
framework, channels separated by rung:

    {"run_id", "step_index", "step_source", "role",
     "l1_text", "l2_text", "l3_text"}

- ``step_index`` — 0-based enumeration of the ``history`` list (the
  alignment key, as in every sidecar).
- ``step_source`` — the entry's own 1-based ``step`` as an integer
  (None when unparsable): the coordinate system the annotation's
  ``hallucination_step`` refers to.
- ``role`` — the entry's ``role`` verbatim ("" when absent; two
  frameworks log no role).
- ``l1_text`` — the entry's ``tool_calls`` field verbatim (the corpus
  stringifies Python literals; parsing them is a detector decision,
  not an adapter one), "" when absent: the call-parameter rung.
- ``l2_text`` — ``tool_responses`` verbatim, "" when absent: the
  tool-output rung.
- ``l3_text`` — ``content`` verbatim ("" when null): the agent-text
  rung.

Ground truth goes to a labels sidecar per framework, keyed by run_id:
``is_hallucination`` parsed to a real bool (the corpus stores the
STRING "true"/"false" — ``bool()`` on it would label every run
hallucinated), ``hallucination_step`` as int where parsable,
category/subcategory/reason/explanation verbatim, ``model_id``,
``question_domain`` and ``n_entries``. The free-text explanation and
reason are ground-truth material for reading results, never detector
input.

CLI::

    python3 -m driftdetect.adapters.agenthallu <agenthallu-repo>/AgentHallu -o <outdir>

writes ``<outdir>/<framework>.content.jsonl``, ``<framework>.labels.json``
and a ``manifest.json`` with the sha256 of every output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

# (directory name, ledger key)
FRAMEWORKS = (
    ("BFCL", "bfcl"),
    ("Camel", "camel"),
    ("Magentic_One", "magentic-one"),
    ("Octotools", "octotools"),
    ("OpenDeepSearch", "opendeepsearch"),
    ("OpenManus", "openmanus"),
    ("SmolAgents", "smolagents"),
)


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


def _bool_label(value) -> bool:
    """The corpus stores "true"/"false" as strings (module docstring)."""
    return str(value).strip().lower() == "true"


def content_lines(doc: dict, run_id: str) -> list[dict]:
    """One AgentHallu trajectory -> content ledger lines."""
    if not isinstance(doc, dict) or not isinstance(doc.get("history"), list):
        raise ValueError("not an AgentHallu trajectory")
    lines: list[dict] = []
    for step_index, entry in enumerate(doc["history"]):
        if not isinstance(entry, dict):
            raise ValueError("malformed history entry")
        lines.append({
            "run_id": run_id,
            "step_index": step_index,
            "step_source": _int_or_none(entry.get("step")),
            "role": str(entry.get("role") or ""),
            "l1_text": _text(entry.get("tool_calls")),
            "l2_text": _text(entry.get("tool_responses")),
            "l3_text": _text(entry.get("content")),
        })
    return lines


def run_label(doc: dict, framework_key: str) -> dict:
    return {
        "framework": framework_key,
        "model_id": doc.get("model_id"),
        "question_domain": doc.get("question_domain"),
        "is_hallucination": _bool_label(doc.get("is_hallucination")),
        "hallucination_step": _int_or_none(doc.get("hallucination_step")),
        "hallucination_category": doc.get("hallucination_category"),
        "hallucination_subcategory": doc.get("hallucination_subcategory"),
        "hallucination_reason": doc.get("hallucination_reason"),
        "explanation": doc.get("explanation"),
        "n_entries": len(doc.get("history") or []),
    }


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(root_dir: str, out_dir: str) -> dict:
    """Convert AgentHallu/<Framework>/ trees, one ledger per framework."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(root_dir), "frameworks": {},
                      "n_skipped": 0}

    for dir_name, key in FRAMEWORKS:
        fdir = os.path.join(root_dir, dir_name)
        if not os.path.isdir(fdir):
            continue
        ledger_path = os.path.join(out_dir, f"{key}.content.jsonl")
        labels_path = os.path.join(out_dir, f"{key}.labels.json")
        labels: dict[str, dict] = {}
        n_lines = 0
        with open(ledger_path, "w", encoding="utf-8") as out:
            for fname in sorted(os.listdir(fdir)):
                if not fname.endswith(".json"):
                    continue
                run_id = f"{key}/{fname[: -len('.json')]}"
                try:
                    with open(os.path.join(fdir, fname),
                              encoding="utf-8") as fh:
                        doc = json.load(fh)
                    lines = content_lines(doc, run_id)
                    label = run_label(doc, key)
                except (OSError, ValueError, json.JSONDecodeError,
                        UnicodeDecodeError, KeyError, TypeError):
                    manifest["n_skipped"] += 1
                    continue
                for line in lines:
                    out.write(json.dumps(line, sort_keys=True) + "\n")
                    n_lines += 1
                labels[run_id] = label
        if not labels:
            os.remove(ledger_path)
            continue
        with open(labels_path, "w", encoding="utf-8") as fh:
            json.dump(labels, fh, sort_keys=True, indent=1)
        n_hall = sum(l["is_hallucination"] for l in labels.values())
        manifest["frameworks"][key] = {
            "ledger": os.path.basename(ledger_path),
            "labels": os.path.basename(labels_path),
            "n_runs": len(labels),
            "n_hallucinated": n_hall,
            "n_clean": len(labels) - n_hall,
            "n_lines": n_lines,
            "sha256_ledger": _sha256_file(ledger_path),
            "sha256_labels": _sha256_file(labels_path),
        }

    manifest["n_runs_total"] = sum(
        f["n_runs"] for f in manifest["frameworks"].values())
    manifest["n_lines_total"] = sum(
        f["n_lines"] for f in manifest["frameworks"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root_dir",
                    help="path to the repo's AgentHallu/ data directory")
    ap.add_argument("-o", "--out", required=True,
                    help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.root_dir, args.out)
    print(
        f"{len(manifest['frameworks'])} frameworks, "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_lines_total']} lines "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
