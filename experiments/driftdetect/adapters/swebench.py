"""SWE-bench submission trajectories -> boundary call record ledgers.

Source: the ``swe-bench-submissions`` S3 bucket, synced locally as
``<root>/<submission>/trajs/...`` (this adapter reads the local sync, it
does not talk to S3). 139 verified submissions, heterogeneous trajectory
formats; this adapter parses the two well-defined families and reports
everything else as skipped rather than guessing:

- ``sweagent``: one ``<instance_id>.traj`` JSON per instance with a
  ``trajectory`` list of ``{action, observation, ...}`` steps (SWE-agent
  and derivatives; 2024-2025). The tool is the leading token of the
  action command (``edit``, ``open``, ``python``, ``submit``, ...), the
  parameter hash covers the full action string.
- ``openai_messages``: one ``<instance_id>.json`` per instance holding a
  chat message list; assistant messages carry ``tool_calls`` with
  ``function.name`` / ``function.arguments`` (OpenHands and other
  OpenAI-tool-format agents). The tool is the function name, the
  parameter hash covers the arguments string.

Mapping decisions (nothing the source does not provide is invented):

- run_id = instance id (file stem), goal_id = the task's repository
  (``astropy__astropy-12907`` -> ``astropy__astropy``) — goal-conditioned
  baselines then condition on the repo being worked on.
- agent_id and model carry the submission name verbatim (that is the
  published identity; version-drift experiments segment by submission at
  the experiment level).
- Neither format flags per-step errors explicitly; ``status`` is always
  "ok" and error-rate-based detectors (context decay) are out of scope
  for this source. Documented, not patched over.
- ``ts`` is deterministic: the submission's date prefix (YYYYMMDD_) as
  the epoch base, plus run index * spacing + step. Ordering only.

CLI::

    python3 -m driftdetect.adapters.swebench <root> -o <outdir>
        [--only sub1,sub2] [--max-runs N]

writes ``<outdir>/<submission>.jsonl`` plus ``manifest.json`` with sha256
fingerprints, per-submission format, run/record counts, and the skipped
submissions with reasons.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re

from ..records import CallRecord, write_jsonl

TS_RUN_SPACING = 1_000.0


def _params_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _goal_id(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0] if "-" in instance_id else instance_id


def _submission_epoch(submission: str) -> float:
    m = re.match(r"(\d{4})(\d{2})(\d{2})_", submission)
    if not m:
        return 1_760_000_000.0
    y, mo, d = (int(g) for g in m.groups())
    return datetime.datetime(y, mo, d, tzinfo=datetime.timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# Per-format parsers: path -> list of (tool, params_payload)
# ---------------------------------------------------------------------------

def parse_sweagent(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    # Bespoke formats reuse the .traj extension (epam: UUID event maps or a
    # top-level list; Lingxi: plain text, fails json.load above) — reject
    # anything without the SWE-agent trajectory list instead of guessing.
    if not isinstance(doc, dict) or not isinstance(doc.get("trajectory"), list):
        raise ValueError("not a sweagent trajectory")
    steps = []
    for step in doc["trajectory"]:
        if not isinstance(step, dict):
            continue
        action = (step.get("action") or "").strip()
        if not action:
            continue
        steps.append((action.split()[0], action))
    return steps


def parse_openai_messages(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, list):
        raise ValueError("not a message list")
    steps = []
    for msg in doc:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name")
            if name:
                steps.append((name, str(fn.get("arguments") or "")))
    return steps


PARSERS = {
    "sweagent": (".traj", parse_sweagent),
    "openai_messages": (".json", parse_openai_messages),
}


def detect_format(traj_dir: str) -> str | None:
    """Pick a parser from the files directly under trajs/ (depth 1 only)."""
    try:
        files = sorted(os.listdir(traj_dir))
    except FileNotFoundError:
        return None
    names = [f for f in files if os.path.isfile(os.path.join(traj_dir, f))]
    if any(f.endswith(".traj") for f in names):
        return "sweagent"
    sample = next((f for f in names if f.endswith(".json")), None)
    if sample is None:
        return None
    try:
        steps = parse_openai_messages(os.path.join(traj_dir, sample))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return "openai_messages" if steps else None


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_submission(
    root: str, submission: str, max_runs: int | None = None
) -> tuple[list[CallRecord], dict] | tuple[None, str]:
    """Returns (records, info) or (None, skip-reason)."""
    traj_dir = os.path.join(root, submission, "trajs")
    fmt = detect_format(traj_dir)
    if fmt is None:
        return None, "unsupported trajectory format (or no trajs/)"
    ext, parser = PARSERS[fmt]

    files = sorted(
        f for f in os.listdir(traj_dir)
        if f.endswith(ext) and os.path.isfile(os.path.join(traj_dir, f))
    )
    if max_runs is not None:
        files = files[:max_runs]

    epoch = _submission_epoch(submission)
    records: list[CallRecord] = []
    n_runs = n_empty = n_failed = 0
    for run_index, fname in enumerate(files):
        instance_id = fname[: -len(ext)]
        try:
            steps = parser(os.path.join(traj_dir, fname))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError,
                AttributeError, KeyError, TypeError):
            # one malformed file must not kill a 139-submission conversion
            n_failed += 1
            continue
        if not steps:
            n_empty += 1
            continue
        n_runs += 1
        for step_index, (tool, payload) in enumerate(steps):
            records.append(CallRecord(
                ts=epoch + run_index * TS_RUN_SPACING + step_index,
                run_id=instance_id,
                agent_id=submission,
                model=submission,
                model_version="",
                goal_id=_goal_id(instance_id),
                step_index=step_index,
                tool=tool,
                params_hash=_params_hash(payload),
                status="ok",
                duration_ms=0.0,
            ))
    if n_runs == 0:
        return None, (
            f"format '{fmt}' detected but no parsable runs "
            f"({n_failed} parse failures, {n_empty} empty)"
        )
    info = {
        "format": fmt,
        "n_runs": n_runs,
        "n_records": len(records),
        "n_empty_runs": n_empty,
        "n_parse_failures": n_failed,
    }
    return records, info


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_tree(root: str, out_dir: str, only: list[str] | None = None,
                 max_runs: int | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    manifest: dict = {"source": os.path.abspath(root), "submissions": {}, "skipped": {}}

    submissions = sorted(
        d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
    )
    if only:
        submissions = [s for s in submissions if s in only]

    for sub in submissions:
        records, info = convert_submission(root, sub, max_runs=max_runs)
        if records is None:
            manifest["skipped"][sub] = info
            print(f"  - {sub}: {info}")
            continue
        ledger_path = os.path.join(out_dir, f"{sub}.jsonl")
        write_jsonl(records, ledger_path)
        info["ledger"] = os.path.basename(ledger_path)
        info["sha256_ledger"] = _sha256_file(ledger_path)
        manifest["submissions"][sub] = info
        print(f"  + {sub}: {info['format']}, {info['n_runs']} runs, {info['n_records']} records")

    manifest["n_runs_total"] = sum(s["n_runs"] for s in manifest["submissions"].values())
    manifest["n_records_total"] = sum(s["n_records"] for s in manifest["submissions"].values())
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", help="local sync of the verified/ prefix (one dir per submission)")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    ap.add_argument("--only", help="comma-separated submission names to convert")
    ap.add_argument("--max-runs", type=int, help="cap runs per submission (smoke tests)")
    args = ap.parse_args(argv)

    manifest = convert_tree(
        args.root, args.out,
        only=args.only.split(",") if args.only else None,
        max_runs=args.max_runs,
    )
    print(
        f"{len(manifest['submissions'])} submissions converted "
        f"({len(manifest['skipped'])} skipped), "
        f"{manifest['n_runs_total']} runs, "
        f"{manifest['n_records_total']} records -> {args.out}"
    )


if __name__ == "__main__":
    main()
