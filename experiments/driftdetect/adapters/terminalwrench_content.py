"""Terminal Wrench content sidecars: the L1/L3 rungs next to the L0 ledger.

Follow-up-paper infrastructure (../../paper-followup/): the L0 boundary
ledgers written by ``terminalwrench.py`` stay untouched and citable; this
module walks the same ``tasks/`` tree and emits one *content sidecar* line
per L0 record, aligned by (run_id, step_index):

    {"run_id", "step_index", "tool", "l1_text", "l3_text"}

- ``l1_text`` — the plain-text call parameters the L0 record only hashed:
  the full ``keystrokes`` string for ``bash_command`` calls, "" for calls
  without free-text parameters (``mark_task_complete``).
- ``l3_text`` — the agent's visible message for the step the call belongs
  to (ATIF ``message``; the scaffold's "thinking" channel), verbatim.
  Steps with several calls repeat their message on each call's line, so
  every sidecar line is self-contained.

Alignment is guaranteed by construction: iteration order, the agent-step
filter, and the empty-tool skip are the same invariants as the L0
adapter's ``convert_trajectory`` (its ``_tool_name`` is imported, not
reimplemented). A drifting copy would silently misalign the rungs, so the
unit tests convert the same synthetic tree through both modules and
assert index-by-index agreement.

Sidecars contain raw source content. Like the ledgers they live outside
the repository (datasets/raw-fetch/ledger/...), fingerprinted in a
manifest.

CLI::

    python3 -m driftdetect.adapters.terminalwrench_content <repo>/tasks -o <outdir>

writes ``<outdir>/<model>.content.jsonl`` and a ``manifest.json`` with
the sha256 of every output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from .terminalwrench import TREES, _tool_name


def content_lines(traj: dict, run_id: str) -> list[dict]:
    """One ATIF trajectory -> sidecar lines aligned with the L0 records."""
    if not isinstance(traj, dict) or not isinstance(traj.get("steps"), list):
        raise ValueError("not an ATIF trajectory")
    lines: list[dict] = []
    step_index = 0
    for step in traj["steps"]:
        if not isinstance(step, dict) or step.get("source") != "agent":
            continue
        message = step.get("message")
        l3_text = message if isinstance(message, str) else ""
        for call in step.get("tool_calls") or []:
            tool = _tool_name(call)
            if not tool:
                continue
            keystrokes = (call.get("arguments") or {}).get("keystrokes")
            lines.append({
                "run_id": run_id,
                "step_index": step_index,
                "tool": tool,
                "l1_text": keystrokes if isinstance(keystrokes, str) else "",
                "l3_text": l3_text,
            })
            step_index += 1
    return lines


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(tasks_dir: str, out_dir: str) -> dict:
    """Walk tasks_dir exactly like the L0 adapter, one sidecar per model."""
    os.makedirs(out_dir, exist_ok=True)
    by_model: dict[str, list[dict]] = {}
    n_skipped = 0

    for task_id in sorted(os.listdir(tasks_dir)):
        tdir = os.path.join(tasks_dir, task_id)
        if not os.path.isdir(tdir):
            continue
        for model_dir in sorted(os.listdir(tdir)):
            mdir = os.path.join(tdir, model_dir)
            if not os.path.isdir(mdir):
                continue
            for tree in TREES:
                trdir = os.path.join(mdir, tree)
                if not os.path.isdir(trdir):
                    continue
                for label_dir in sorted(os.listdir(trdir)):
                    traj_path = os.path.join(trdir, label_dir, "trial",
                                             "agent", "trajectory.json")
                    run_id = f"{task_id}/{tree}/{label_dir}"
                    try:
                        with open(traj_path, encoding="utf-8") as fh:
                            traj = json.load(fh)
                        lines = content_lines(traj, run_id)
                    except (OSError, ValueError, json.JSONDecodeError,
                            UnicodeDecodeError, KeyError, TypeError):
                        n_skipped += 1
                        continue
                    if not lines:
                        n_skipped += 1
                        continue
                    by_model.setdefault(model_dir, []).extend(lines)

    manifest: dict = {"source": os.path.abspath(tasks_dir), "models": {},
                      "n_skipped": n_skipped}
    for model_dir in sorted(by_model):
        path = os.path.join(out_dir, f"{model_dir}.content.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for line in by_model[model_dir]:
                fh.write(json.dumps(line, sort_keys=True) + "\n")
        manifest["models"][model_dir] = {
            "sidecar": os.path.basename(path),
            "n_lines": len(by_model[model_dir]),
            "sha256_sidecar": _sha256_file(path),
        }

    manifest["n_lines_total"] = sum(
        m["n_lines"] for m in manifest["models"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tasks_dir", help="path to the terminal-wrench repo's tasks/ directory")
    ap.add_argument("-o", "--out", required=True, help="output directory for sidecars")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.tasks_dir, args.out)
    print(
        f"{len(manifest['models'])} models, "
        f"{manifest['n_lines_total']} sidecar lines "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
