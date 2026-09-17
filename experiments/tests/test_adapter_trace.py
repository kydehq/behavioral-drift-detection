"""Unit tests for the TRACE adapter, on a synthetic mini export."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.trace import convert_export, convert_trajectory
from driftdetect.records import read_jsonl


def traj_doc(trajectory_id="trajectory_0001", label="0",
             calls=(("Glob", {"pattern": "**/*.js"}),
                    ("Bash", {"command": "cd /srv && npm test",
                              "description": "run tests"}),
                    ("Edit", {"file_path": "/srv/a.js"}))):
    conversation = [{"role": "user", "content": "task"}]
    for name, params in calls:
        conversation.append({
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [{"name": name, "parameters": params}],
            "tool_results": [{"output": "ok"}],
        })
    conversation.append({"role": "assistant", "content": "done"})
    return {"trajectory_id": trajectory_id, "label": label,
            "conversation": conversation}


class TestConvertTrajectory(unittest.TestCase):
    def test_bash_tool_is_leading_command_token(self):
        recs, label = convert_trajectory(traj_doc())
        self.assertEqual([r.tool for r in recs], ["Glob", "cd", "Edit"])
        self.assertEqual([r.step_index for r in recs], [0, 1, 2])
        self.assertEqual({r.run_id for r in recs}, {"trajectory_0001"})
        self.assertEqual({r.goal_id for r in recs}, {"trajectory_0001"})
        self.assertEqual({r.agent_id for r in recs}, {"trace"})
        self.assertEqual({r.status for r in recs}, {"ok"})
        self.assertTrue(all(a.ts < b.ts for a, b in zip(recs, recs[1:])))
        self.assertEqual(label["n_calls"], 3)

    def test_benign_and_hacked_labels(self):
        _, benign = convert_trajectory(traj_doc(label="0"))
        self.assertFalse(benign["hacked"])
        self.assertEqual(benign["codes"], [])
        _, hacked = convert_trajectory(traj_doc(label="1.1.2, 1.2.1"))
        self.assertTrue(hacked["hacked"])
        self.assertEqual(hacked["codes"], ["1.1.2", "1.2.1"])
        self.assertEqual(hacked["label"], "1.1.2, 1.2.1")

    def test_user_messages_produce_no_records(self):
        doc = traj_doc()
        doc["conversation"].insert(1, {"role": "user", "content": "hint",
                                       "tool_calls": [{"name": "X"}]})
        recs, _ = convert_trajectory(doc)
        self.assertEqual(len(recs), 3)

    def test_non_export_document_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_trajectory({"foo": 1})
        with self.assertRaises(ValueError):
            convert_trajectory({"conversation": [], "label": "0"})

    def test_params_hash_is_deterministic(self):
        recs1, _ = convert_trajectory(traj_doc())
        recs2, _ = convert_trajectory(traj_doc())
        self.assertEqual(recs1[1].params_hash, recs2[1].params_hash)
        self.assertEqual(len(recs1[1].params_hash), 12)


class TestConvertExport(unittest.TestCase):
    def _write(self, path, docs):
        with open(path, "w", encoding="utf-8") as fh:
            for doc in docs:
                fh.write((doc if isinstance(doc, str) else json.dumps(doc))
                         + "\n")

    def test_export_conversion_writes_ledger_labels_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = os.path.join(tmp, "trajectories.jsonl")
            self._write(export, [traj_doc("trajectory_0001", "0"),
                                 traj_doc("trajectory_0002", "1.1.1")])
            out = os.path.join(tmp, "out")
            manifest = convert_export(export, out)

            self.assertEqual(manifest["n_runs_total"], 2)
            self.assertEqual(manifest["n_records_total"], 6)
            recs = list(read_jsonl(os.path.join(out, "trace.jsonl")))
            self.assertEqual({r.run_id for r in recs},
                             {"trajectory_0001", "trajectory_0002"})
            with open(os.path.join(out, "trace.labels.json")) as fh:
                labels = json.load(fh)
            self.assertFalse(labels["trajectory_0001"]["hacked"])
            self.assertTrue(labels["trajectory_0002"]["hacked"])
            entry = manifest["models"]["trace"]
            self.assertEqual(len(entry["sha256_ledger"]), 64)
            self.assertEqual(len(manifest["sha256_source"]), 64)

    def test_malformed_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = os.path.join(tmp, "trajectories.jsonl")
            self._write(export, [traj_doc(), "not json"])
            manifest = convert_export(export, os.path.join(tmp, "out"))
            self.assertEqual(manifest["n_runs_total"], 1)
            self.assertEqual(manifest["n_skipped"], 1)

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = os.path.join(tmp, "trajectories.jsonl")
            self._write(export, [traj_doc()])
            m1 = convert_export(export, os.path.join(tmp, "out1"))
            m2 = convert_export(export, os.path.join(tmp, "out2"))
            self.assertEqual(m1["models"]["trace"]["sha256_ledger"],
                             m2["models"]["trace"]["sha256_ledger"])


if __name__ == "__main__":
    unittest.main()
