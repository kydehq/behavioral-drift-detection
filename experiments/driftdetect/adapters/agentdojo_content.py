"""AgentDojo content sidecars: the L1/L2/L3 rungs next to the L0 ledgers.

Follow-up-paper infrastructure (../../paper-followup/): the L0 ledgers
written by ``agentdojo.py`` stay untouched and citable; this module
walks the same ``runs/`` tree and emits one content sidecar line per L0
record, aligned by (run_id, step_index):

    {"run_id", "step_index", "tool", "l1_text", "l2_text", "l3_text"}

- ``l1_text`` — the call arguments the L0 record only hashed, as their
  canonical JSON (AgentDojo args are nested structures; canonical JSON
  is their plain-text form, and it is exactly the string the L0
  ``params_hash`` fingerprints).
- ``l2_text`` — the *inbound tool result* for this call: string content
  verbatim, content-block lists (the Llama/SecAlign transcript shape)
  as their concatenated text, anything else as canonical JSON; "" when
  the run ended before a result arrived. Matching is by
  ``tool_call_id`` where the transcript carries one, and positional
  (first unanswered call in transcript order) where it does not —
  several pipeline families (gemini, command-r, Llama, SecAlign) write
  ``tool_call_id`` as ``""``/``None``, so a pure id lookup would leave
  their entire L2 rung empty. This is the rung where AgentDojo's cause
  crosses the boundary — the injected text arrives in a tool result
  (companion paper, Section 2.3).
- ``l3_text`` — the ``content`` of the assistant message that carried
  the call, verbatim ("" when null); messages with several calls repeat
  it per call, so every sidecar line is self-contained.

Alignment is guaranteed by construction: the call enumeration is the
same expression as ``agentdojo.convert_run`` (assistant messages in
transcript order, ``tool_calls`` in message order); the unit tests
convert the same synthetic run through both modules and assert
index-by-index agreement.

Alongside each sidecar the adapter writes
``<pipeline>.injections.json`` — run_id -> the run's ground-truth
injected strings (the source's ``injections`` field, attacked runs
only). The L2 experiment uses it exclusively as an *evaluation
denominator* (did the injected content ever cross the boundary into a
tool result?), never as detector input.

Sidecars contain raw source content — including the injected strings.
Like the ledgers they live outside the repository
(datasets/raw-fetch/ledger/...), fingerprinted in a manifest.

CLI::

    python3 -m driftdetect.adapters.agentdojo_content <agentdojo-repo>/runs -o <outdir>

writes ``<outdir>/<pipeline>.content.jsonl``,
``<pipeline>.injections.json`` and a ``manifest.json`` with the sha256
of every output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os


def _canon(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _result_text(content) -> str:
    """A tool message's content as plain text (module docstring)."""
    if content is None:
        return ""
    if isinstance(content, list):
        parts = [blk.get("content") or blk.get("text")
                 for blk in content if isinstance(blk, dict)]
        if len(parts) == len(content) and all(isinstance(p, str) for p in parts):
            return "\n".join(parts)
    return _canon(content)


def _paired_result_texts(doc: dict) -> list[str]:
    """One inbound result text per call, in call enumeration order.

    By ``tool_call_id`` where present, else the first unanswered call
    in transcript order; "" for calls no result ever arrived for.
    """
    slots: list[str] = []
    slot_by_id: dict[str, int] = {}
    unanswered: list[int] = []
    for msg in doc.get("messages", []):
        role = msg.get("role")
        if role == "assistant":
            for call in msg.get("tool_calls") or []:
                index = len(slots)
                slots.append("")
                if call.get("id"):
                    slot_by_id[call["id"]] = index
                unanswered.append(index)
        elif role == "tool":
            text = _result_text(msg.get("content"))
            call_id = msg.get("tool_call_id")
            if call_id and call_id in slot_by_id:
                index = slot_by_id[call_id]
                slots[index] = text
                if index in unanswered:
                    unanswered.remove(index)
            elif unanswered:
                slots[unanswered.pop(0)] = text
    return slots


def injected_strings(doc: dict) -> list[str]:
    """The run's ground-truth injected strings — attacked runs only, else []."""
    attack_type = doc.get("attack_type")
    if attack_type is None or attack_type == "None":
        return []
    return sorted(set(doc.get("injections", {}).values()))


def content_lines(doc: dict, run_id: str) -> list[dict]:
    """One AgentDojo run document -> sidecar lines aligned with the L0 records."""
    results = _paired_result_texts(doc)

    lines: list[dict] = []
    step = 0
    for msg in doc.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        l3 = content if isinstance(content, str) else ""
        for call in msg.get("tool_calls") or []:
            lines.append({
                "run_id": run_id,
                "step_index": step,
                "tool": call["function"],
                "l1_text": _canon(call.get("args") or {}),
                "l2_text": results[step],
                "l3_text": l3,
            })
            step += 1
    return lines


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(runs_dir: str, out_dir: str) -> dict:
    """Walk runs_dir exactly like the L0 adapter, one sidecar per pipeline."""
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
        path = os.path.join(out_dir, f"{pipeline}.content.jsonl")
        injections_path = os.path.join(out_dir, f"{pipeline}.injections.json")
        injections: dict[str, list[str]] = {}
        n_lines = 0
        with open(path, "w", encoding="utf-8") as out:
            for rel in run_files:
                with open(os.path.join(runs_dir, rel), encoding="utf-8") as fh:
                    doc = json.load(fh)
                run_id = rel[: -len(".json")]
                for line in content_lines(doc, run_id):
                    out.write(json.dumps(line, sort_keys=True) + "\n")
                    n_lines += 1
                strings = injected_strings(doc)
                if strings:
                    injections[run_id] = strings
        with open(injections_path, "w", encoding="utf-8") as fh:
            json.dump(injections, fh, sort_keys=True, indent=1)

        manifest["pipelines"][pipeline] = {
            "sidecar": os.path.basename(path),
            "injections": os.path.basename(injections_path),
            "n_runs": len(run_files),
            "n_attacked": len(injections),
            "n_lines": n_lines,
            "sha256_sidecar": _sha256_file(path),
            "sha256_injections": _sha256_file(injections_path),
        }

    manifest["n_lines_total"] = sum(
        p["n_lines"] for p in manifest["pipelines"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs_dir", help="path to the agentdojo repo's runs/ directory")
    ap.add_argument("-o", "--out", required=True,
                    help="output directory for sidecars")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.runs_dir, args.out)
    print(
        f"{len(manifest['pipelines'])} pipelines, "
        f"{manifest['n_lines_total']} sidecar lines -> {args.out}"
    )


if __name__ == "__main__":
    main()
