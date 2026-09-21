"""Unit tests for the SWE-chat adapter, on a synthetic mini export."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.swechat import agent_slug, convert_event, convert_export
from driftdetect.records import read_jsonl


SESSION_META = {
    "user_id": "user-1", "repo_id": "repo-a", "agent": "Claude Code",
    "cli_version": "2.1.79", "created_at_us": 1_770_000_000_000_000,
}


def event(session_id="s1", turn_number=1, ts_us=1_770_000_000_000_000,
          tool_name="Read", command_head=None, params_sha256="ab" * 32,
          model="claude-opus-4-6", status="ok", duration_ms=12.5,
          tool_call_id="toolu_1"):
    return {
        "session_id": session_id, "turn_number": turn_number, "ts_us": ts_us,
        "tool_name": tool_name, "tool_call_id": tool_call_id,
        "command_head": command_head, "params_sha256": params_sha256,
        "params_len": 42, "model": model, "status": status,
        "duration_ms": duration_ms,
    }


class TestConvertEvent(unittest.TestCase):
    def test_field_mapping(self):
        rec = convert_event(event(), SESSION_META)
        self.assertEqual(rec.run_id, "s1")
        self.assertEqual(rec.agent_id, "user-1")
        self.assertEqual(rec.goal_id, "repo-a")
        self.assertEqual(rec.model, "claude-opus-4-6")
        self.assertEqual(rec.model_version, "2.1.79")
        self.assertEqual(rec.tool, "Read")
        self.assertEqual(rec.params_hash, "ab" * 6)  # truncated to 12 chars
        self.assertEqual(rec.status, "ok")
        self.assertAlmostEqual(rec.ts, 1_770_000_000.0)
        self.assertAlmostEqual(rec.duration_ms, 12.5)

    def test_bash_uses_leading_command_token(self):
        rec = convert_event(event(tool_name="Bash", command_head="git"),
                            SESSION_META)
        self.assertEqual(rec.tool, "git")
        rec = convert_event(event(tool_name="bash", command_head="npm"),
                            SESSION_META)
        self.assertEqual(rec.tool, "npm")
        # Bash without a command head keeps its name
        rec = convert_event(event(tool_name="Bash", command_head=None),
                            SESSION_META)
        self.assertEqual(rec.tool, "Bash")
        # non-Bash tools never take the command head
        rec = convert_event(event(tool_name="Grep", command_head="git"),
                            SESSION_META)
        self.assertEqual(rec.tool, "Grep")

    def test_event_without_timestamp_is_dropped(self):
        self.assertIsNone(convert_event(event(ts_us=None), SESSION_META))

    def test_error_status_and_missing_duration(self):
        rec = convert_event(event(status="error", duration_ms=None),
                            SESSION_META)
        self.assertEqual(rec.status, "error")
        self.assertEqual(rec.duration_ms, 0.0)


class TestAgentSlug(unittest.TestCase):
    def test_slugs(self):
        self.assertEqual(agent_slug("Claude Code"), "claude-code")
        self.assertEqual(agent_slug("Gemini CLI"), "gemini-cli")
        self.assertEqual(agent_slug("opencode"), "opencode")
        self.assertEqual(agent_slug(None), "unknown")
        self.assertEqual(agent_slug(""), "unknown")


class TestConvertExport(unittest.TestCase):
    def _write_export(self, tmp, events, sessions):
        with open(os.path.join(tmp, "swechat-events.jsonl"), "w") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")
        with open(os.path.join(tmp, "swechat-sessions.json"), "w") as fh:
            json.dump(sessions, fh)

    def test_export_roundtrip(self):
        sessions = {
            "s1": dict(SESSION_META),
            "s2": dict(SESSION_META, agent="OpenCode", user_id="user-2"),
        }
        events = [
            # s1 out of turn order on purpose; one event without ts
            event(session_id="s1", turn_number=3, tool_name="Edit",
                  ts_us=1_770_000_002_000_000, tool_call_id="t3"),
            event(session_id="s1", turn_number=1, tool_name="Bash",
                  command_head="git", tool_call_id="t1"),
            event(session_id="s1", turn_number=2, ts_us=None, tool_call_id="t2"),
            event(session_id="s2", turn_number=1, tool_name="read",
                  tool_call_id="t4"),
            event(session_id="missing", turn_number=1, tool_call_id="t5"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ledger")
            self._write_export(tmp, events, sessions)
            manifest = convert_export(tmp, out)

            self.assertEqual(manifest["n_skipped_no_ts"], 1)
            self.assertEqual(manifest["n_missing_session_meta"], 1)
            self.assertEqual(set(manifest["agents"]), {"claude-code", "opencode"})
            self.assertEqual(manifest["agents"]["claude-code"]["n_records"], 2)

            recs = list(read_jsonl(os.path.join(out, "claude-code.jsonl")))
            # turn order restored, step indices renumbered over survivors
            self.assertEqual([r.tool for r in recs], ["git", "Edit"])
            self.assertEqual([r.step_index for r in recs], [0, 1])

            with open(os.path.join(out, "swechat.sessions.json")) as fh:
                sidecar = json.load(fh)
            self.assertEqual(sidecar["s1"]["n_records"], 2)
            self.assertEqual(sidecar["s1"]["agent"], "claude-code")
            self.assertEqual(sidecar["s2"]["agent"], "opencode")

            with open(os.path.join(out, "manifest.json")) as fh:
                on_disk = json.load(fh)
            self.assertEqual(on_disk["n_records_total"], 3)


if __name__ == "__main__":
    unittest.main()
