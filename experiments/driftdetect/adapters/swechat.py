"""SWE-chat real user sessions -> boundary call record ledgers.

Source: the HF dataset ``SALT-NLP/SWE-chat`` (ODC-BY) — 5,851 real
working sessions of 190 users across 205 repositories, recorded from
production coding-agent use (Claude Code 4,852 sessions, OpenCode 623,
Codex 213, ...), with real wall-clock timestamps. This is the corpus
that removes the composed-timeline caveat: every other ledger in this
tree orders runs by seeded shuffling because its source has no
temporal meaning; here the timeline is the ground truth.

The adapter reads the two files materialized once by
``datasets/scripts/export_swechat_jsonl.py`` (Parquet is outside the
stdlib-only rule of this tree): ``swechat-events.jsonl`` — one line per
``tool_use`` turn, already reduced to the boundary (parameters as
sha256 + length, Bash commands as their leading token) — and
``swechat-sessions.json`` with per-session metadata.

Mapping decisions (nothing the source does not provide is invented):

- One CallRecord per ``tool_use`` event. ``ts`` is the real event
  timestamp; events without one are skipped and counted (the OpenCode
  scaffold logs no per-turn timestamps — its 22,850 tool calls all
  drop, leaving a vestigial ledger; every Claude Code event has one).
- One ledger per scaffold (the ``agent`` field of the session,
  slugified): scaffolds do not share tool vocabularies, and mixing
  them would manufacture trivial drift. Sessions whose agent is
  missing go to ``unknown``.
- ``run_id`` = session_id; ``agent_id`` = the *user* id — the
  deployment under observation is one human's agent use, which is what
  a per-deployment baseline would be frozen on. ``goal_id`` = repo_id
  (the closest thing to a task grouping the source has).
- ``model`` is the per-turn model string (users switch models
  mid-timeline); ``model_version`` is the session's CLI version — the
  field real in-deployment version drift is read off (48 distinct
  versions, 45 users with more than one).
- ``tool`` is the tool name verbatim, except Bash/bash calls, which
  use the leading command token (``git``, ``npm``, ``cargo``, ... —
  the same convention as the sweagent, terminal-wrench and trace
  adapters). ``params_hash`` is the export's sha256 truncated to 12
  hex chars; ``status`` is "error" iff the raw transcript marked the
  paired tool_result ``is_error`` (Claude Code only — other scaffolds'
  transcripts were not scanned, their status is uniformly "ok").
- ``step_index`` numbers the surviving events of a session in
  turn-number order.

The sessions sidecar (``swechat.sessions.json``) carries per-session
{user_id, agent (slug), cli_version, created_at_us, n_records} so
evaluations can order sessions chronologically without re-deriving it.

CLI::

    python3 -m driftdetect.adapters.swechat <swe-chat-dir> -o <outdir>

writes ``<outdir>/<agent-slug>.jsonl`` per scaffold, plus
``swechat.sessions.json`` and a ``manifest.json`` with the sha256 of
every output file — the fingerprint a verdict names its input by.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict

from ..records import CallRecord, write_jsonl

BASH_NAMES = ("Bash", "bash")


def agent_slug(agent: str | None) -> str:
    slug = "-".join(str(agent or "unknown").lower().split())
    return slug or "unknown"


def convert_event(ev: dict, sess: dict) -> CallRecord | None:
    """One export line + its session metadata -> CallRecord or None.

    Returns None for events without a timestamp (a real-timeline ledger
    has no place for unordered events; the caller counts them).
    """
    if ev.get("ts_us") is None:
        return None
    tool = ev.get("tool_name") or ""
    if tool in BASH_NAMES and ev.get("command_head"):
        tool = ev["command_head"]
    if not tool:
        return None
    return CallRecord(
        ts=ev["ts_us"] / 1e6,
        run_id=str(ev["session_id"]),
        agent_id=str(sess.get("user_id") or ""),
        model=str(ev.get("model") or ""),
        model_version=str(sess.get("cli_version") or ""),
        goal_id=str(sess.get("repo_id") or ""),
        step_index=-1,  # assigned after the session is complete
        tool=tool,
        params_hash=str(ev.get("params_sha256") or "")[:12],
        status=str(ev.get("status") or "ok"),
        duration_ms=float(ev["duration_ms"]) if ev.get("duration_ms") is not None else 0.0,
    )


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_export(src_dir: str, out_dir: str) -> dict:
    """Convert the exported events into per-scaffold ledgers."""
    events_path = os.path.join(src_dir, "swechat-events.jsonl")
    sessions_path = os.path.join(src_dir, "swechat-sessions.json")
    os.makedirs(out_dir, exist_ok=True)

    with open(sessions_path, encoding="utf-8") as fh:
        sessions_meta = json.load(fh)

    # session_id -> [(turn_number, CallRecord)] so step indices follow
    # the source turn order even if the export were unsorted.
    per_session: dict[str, list[tuple[int, CallRecord]]] = defaultdict(list)
    n_skipped_no_ts = 0
    n_missing_session = 0
    with open(events_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            sess = sessions_meta.get(ev.get("session_id"))
            if sess is None:
                n_missing_session += 1
                continue
            rec = convert_event(ev, sess)
            if rec is None:
                n_skipped_no_ts += 1
                continue
            per_session[rec.run_id].append((int(ev.get("turn_number") or 0), rec))

    from dataclasses import replace
    by_agent: dict[str, list[CallRecord]] = defaultdict(list)
    sessions_out: dict[str, dict] = {}
    for sid in sorted(per_session):
        rows = sorted(per_session[sid], key=lambda t: t[0])
        sess = sessions_meta[sid]
        slug = agent_slug(sess.get("agent"))
        recs = [replace(rec, step_index=i) for i, (_, rec) in enumerate(rows)]
        by_agent[slug].extend(recs)
        sessions_out[sid] = {
            "user_id": sess.get("user_id"),
            "agent": slug,
            "cli_version": sess.get("cli_version"),
            "created_at_us": sess.get("created_at_us"),
            "n_records": len(recs),
        }

    manifest_agents = {}
    for slug in sorted(by_agent):
        recs = sorted(by_agent[slug], key=lambda r: (r.run_id, r.step_index))
        ledger_path = os.path.join(out_dir, f"{slug}.jsonl")
        n = write_jsonl(recs, ledger_path)
        manifest_agents[slug] = {
            "ledger": os.path.basename(ledger_path),
            "n_runs": len({r.run_id for r in recs}),
            "n_users": len({r.agent_id for r in recs}),
            "n_records": n,
            "sha256_ledger": _sha256_file(ledger_path),
        }

    sidecar_path = os.path.join(out_dir, "swechat.sessions.json")
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        json.dump(sessions_out, fh, sort_keys=True, indent=1)

    manifest = {
        "source_events": os.path.abspath(events_path),
        "sha256_source_events": _sha256_file(events_path),
        "source_sessions": os.path.abspath(sessions_path),
        "sha256_source_sessions": _sha256_file(sessions_path),
        "agents": manifest_agents,
        "sessions_sidecar": os.path.basename(sidecar_path),
        "sha256_sessions_sidecar": _sha256_file(sidecar_path),
        "n_skipped_no_ts": n_skipped_no_ts,
        "n_missing_session_meta": n_missing_session,
        "n_runs_total": len(sessions_out),
        "n_records_total": sum(a["n_records"] for a in manifest_agents.values()),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=1)
    return manifest


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src_dir",
                    help="directory with swechat-events.jsonl + swechat-sessions.json")
    ap.add_argument("-o", "--out", required=True, help="output directory for ledgers")
    args = ap.parse_args(argv)
    manifest = convert_export(args.src_dir, args.out)
    print(
        f"{manifest['n_runs_total']} sessions, "
        f"{manifest['n_records_total']} records "
        f"({manifest['n_skipped_no_ts']} without timestamp skipped) -> {args.out}"
    )
    for slug, info in manifest["agents"].items():
        print(f"  {slug}: {info['n_runs']} runs, {info['n_users']} users, "
              f"{info['n_records']} records")


if __name__ == "__main__":
    main()
