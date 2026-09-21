"""Who&When content sidecars: the L3 rung next to the L0 ledgers.

Follow-up-paper infrastructure (../../paper-followup/): the L0 ledgers
written by ``whowhen.py`` stay untouched and citable; this module walks
the same ``Who&When/`` tree and emits one content sidecar line per L0
record, aligned by (run_id, step_index):

    {"run_id", "step_index", "tool", "l3_text"}

- ``tool`` — the seam label, the same expression as the L0 adapter
  (``name`` falling back to ``role``).
- ``l3_text`` — the history entry's ``content`` verbatim (non-string
  content as canonical JSON, "" when null). On this corpus the seam
  message IS the content: there is no separate parameter or
  tool-output channel, so the sidecar carries a single rung — the
  message text a delegation-seam monitor would store.

Alignment is guaranteed by construction: the entry enumeration is the
same expression as ``whowhen.convert_run`` (history order, entries
without a seam label skipped, ``step_index`` = source history index —
holes included); the unit tests convert the same synthetic run through
both modules and assert index-by-index agreement.

Sidecars contain raw source content. Like the ledgers they live
outside the repository (datasets/raw-fetch/ledger/...), fingerprinted
in a manifest.

CLI::

    python3 -m driftdetect.adapters.whowhen_content "<who-and-when>/Who&When" -o <outdir>

writes ``<outdir>/{algorithm-generated,hand-crafted}.content.jsonl``
and a ``manifest.json`` with the sha256 of every output file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

from .whowhen import VARIANTS, _seam_label


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def content_lines(doc: dict, run_id: str) -> list[dict]:
    """One Who&When run document -> sidecar lines aligned with the L0
    records."""
    if not isinstance(doc, dict) or not isinstance(doc.get("history"), list):
        raise ValueError("not a Who&When run")
    lines: list[dict] = []
    for step_index, entry in enumerate(doc["history"]):
        if not isinstance(entry, dict):
            raise ValueError("malformed history entry")
        tool = _seam_label(entry)
        if not tool:
            continue
        lines.append({
            "run_id": run_id,
            "step_index": step_index,
            "tool": tool,
            "l3_text": _text(entry.get("content")),
        })
    return lines


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(root_dir: str, out_dir: str) -> dict:
    """Walk Who&When/ exactly like the L0 adapter, one sidecar per
    variant."""
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(root_dir), "variants": {},
                      "n_skipped": 0}

    for dir_name, key in VARIANTS:
        vdir = os.path.join(root_dir, dir_name)
        if not os.path.isdir(vdir):
            continue
        path = os.path.join(out_dir, f"{key}.content.jsonl")
        n_lines = 0
        n_runs = 0
        with open(path, "w", encoding="utf-8") as out:
            for fname in sorted(os.listdir(vdir),
                                key=lambda n: (len(n), n)):  # 1.json, 2.json
                if not fname.endswith(".json"):
                    continue
                run_id = f"{key}/{fname[: -len('.json')]}"
                try:
                    with open(os.path.join(vdir, fname),
                              encoding="utf-8") as fh:
                        doc = json.load(fh)
                    lines = content_lines(doc, run_id)
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
        manifest["variants"][key] = {
            "sidecar": os.path.basename(path),
            "n_runs": n_runs,
            "n_lines": n_lines,
            "sha256_sidecar": _sha256_file(path),
        }

    manifest["n_lines_total"] = sum(
        v["n_lines"] for v in manifest["variants"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root_dir",
                    help="path to the dataset's Who&When directory")
    ap.add_argument("-o", "--out", required=True,
                    help="output directory for sidecars")
    args = ap.parse_args(argv)
    manifest = convert_tree(args.root_dir, args.out)
    print(
        f"{len(manifest['variants'])} variants, "
        f"{manifest['n_lines_total']} sidecar lines "
        f"({manifest['n_skipped']} skipped) -> {args.out}"
    )


if __name__ == "__main__":
    main()
