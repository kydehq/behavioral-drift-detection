"""TRACE content sidecars: the L1/L3 rungs next to the TRACE ledger.

Follow-up-paper infrastructure (../../paper-followup/), the TRACE
analogue of ``terminalwrench_content``: the L0 ledger written by
``trace.py`` stays untouched and citable; this module walks the same
exported ``trajectories.jsonl`` and emits one content sidecar line per
L0 record, aligned by (run_id, step_index):

    {"run_id", "step_index", "tool", "l1_text", "l3_text"}

- ``l1_text`` — the plain-text call parameters the L0 record only
  hashed: every string-valued entry of the call's ``parameters``, in
  sorted key order, joined by newlines. For ``Bash`` that is the
  command (plus the scaffold's ``description`` — it *is* a plain-text
  parameter); for ``Edit``/``Write`` it includes the file path and the
  written content. Non-string parameters (timeouts, booleans) are not
  text and are omitted.
- ``l3_text`` — the assistant message's ``content`` for the step the
  call belongs to, verbatim. Messages with several calls repeat their
  content on each call's line, so every sidecar line is self-contained.

Alignment is guaranteed by construction: iteration order, the
assistant-message filter, and the empty-tool skip are the same
invariants as ``trace.convert_trajectory`` (its ``_tool_name`` is
imported, not reimplemented); the unit tests convert the same synthetic
export through both modules and assert index-by-index agreement.

Sidecars contain raw source content. Like the ledgers they live outside
the repository (datasets/raw-fetch/ledger/...), fingerprinted in a
manifest.

CLI::

    python3 -m driftdetect.adapters.trace_content <trace-rewardhack>/trajectories.jsonl -o <outdir>

writes ``<outdir>/trace.content.jsonl`` and a ``manifest.json`` with
the sha256 of the output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from .trace import AGENT_ID, _tool_name


def l1_text(call: dict) -> str:
    """Plain-text parameters: string values in sorted key order."""
    params = call.get("parameters") or {}
    return "\n".join(v for _, v in sorted(params.items())
                     if isinstance(v, str))


def content_lines(doc: dict) -> list[dict]:
    """One exported trajectory -> sidecar lines aligned with the L0 records."""
    if not isinstance(doc, dict) or not isinstance(doc.get("conversation"), list):
        raise ValueError("not an exported TRACE trajectory")
    run_id = str(doc.get("trajectory_id") or "")
    if not run_id:
        raise ValueError("trajectory without trajectory_id")

    lines: list[dict] = []
    step_index = 0
    for message in doc["conversation"]:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        l3 = content if isinstance(content, str) else ""
        for call in message.get("tool_calls") or []:
            tool = _tool_name(call)
            if not tool:
                continue
            lines.append({
                "run_id": run_id,
                "step_index": step_index,
                "tool": tool,
                "l1_text": l1_text(call),
                "l3_text": l3,
            })
            step_index += 1
    return lines


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_export(export_path: str, out_dir: str) -> dict:
    """Walk the export exactly like the L0 adapter, one sidecar file."""
    os.makedirs(out_dir, exist_ok=True)
    all_lines: list[dict] = []
    n_skipped = 0

    with open(export_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                lines = content_lines(json.loads(line))
            except (ValueError, json.JSONDecodeError, KeyError, TypeError):
                n_skipped += 1
                continue
            if not lines:
                n_skipped += 1
                continue
            all_lines.extend(lines)

    path = os.path.join(out_dir, f"{AGENT_ID}.content.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for line_doc in all_lines:
            fh.write(json.dumps(line_doc, sort_keys=True) + "\n")

    manifest = {
        "source": os.path.abspath(export_path),
        "sha256_source": _sha256_file(export_path),
        "models": {
            AGENT_ID: {
                "sidecar": os.path.basename(path),
                "n_lines": len(all_lines),
                "sha256_sidecar": _sha256_file(path),
            }
        },
        "n_skipped": n_skipped,
        "n_lines_total": len(all_lines),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export_path",
                    help="trajectories.jsonl written by export_trace_jsonl.py")
    ap.add_argument("-o", "--out", required=True,
                    help="output directory for the sidecar")
    args = ap.parse_args(argv)
    manifest = convert_export(args.export_path, args.out)
    print(
        f"{manifest['n_lines_total']} sidecar lines "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
