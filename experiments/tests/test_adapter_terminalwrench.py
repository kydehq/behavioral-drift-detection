"""Unit tests for the Terminal Wrench adapter, on a synthetic mini tasks/ tree."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.terminalwrench import convert_trajectory, convert_tree
from driftdetect.records import read_jsonl


def traj_doc(model_name="anthropic/claude-opus-4-6",
             calls=(("bash_command", {"keystrokes": "mkdir -p /tmp/x\n", "duration": 0.1}),
                    ("bash_command", {"keystrokes": "cat /tmp/x/f\n", "duration": 0.1}),
                    ("mark_task_complete", {}))):
    steps = [{"step_id": 1, "timestamp": "2026-04-12T06:04:38.877934+00:00",
              "source": "user", "message": "task"}]
    for i, (fn, args) in enumerate(calls):
        steps.append({
            "step_id": i + 2,
            "timestamp": f"2026-04-12T06:0{5 + i}:00+00:00",
            "source": "agent",
            "model_name": model_name,
            "message": "thinking",
            "tool_calls": [{"tool_call_id": f"call_{i}", "function_name": fn,
                            "arguments": args}],
            "observation": {"results": [{"content": "output"}]},
        })
    return {
        "schema_version": "ATIF-v1.6",
        "session_id": "s-1",
        "agent": {"name": "terminus-2", "version": "2.0.0", "model_name": model_name},
        "steps": steps,
    }


def meta_doc(classification="rewarded_serious_exploit", task_id="1012",
             judged_serious=True, reward=1.0):
    return {
        "task_id": task_id,
        "model": "claude-opus-4.6",
        "classification": classification,
        "reward": reward,
        "exploit_attempted": classification != "baseline",
        "judged_serious_exploit": judged_serious,
        "judged_legitimate_solve": False,
        "source_dataset": "seta_2026_01_29",
        "episode_count": 1,
    }


class TestConvertTrajectory(unittest.TestCase):
    def test_bash_tool_is_leading_keystroke_token(self):
        recs, label = convert_trajectory(
            traj_doc(), meta_doc(), "claude-opus-4.6", "hack_trajectories",
            "1012/hack_trajectories/v5")
        self.assertEqual([r.tool for r in recs],
                         ["mkdir", "cat", "mark_task_complete"])
        self.assertEqual([r.step_index for r in recs], [0, 1, 2])
        self.assertEqual({r.goal_id for r in recs}, {"1012"})
        self.assertEqual({r.agent_id for r in recs}, {"claude-opus-4.6"})
        self.assertEqual({r.model for r in recs}, {"anthropic/claude-opus-4-6"})
        self.assertEqual({r.status for r in recs}, {"ok"})
        self.assertEqual(label["classification"], "rewarded_serious_exploit")
        self.assertEqual(label["n_calls"], 3)

    def test_ts_comes_from_step_timestamps_and_is_ordered(self):
        recs, _ = convert_trajectory(
            traj_doc(), meta_doc(), "m", "hack_trajectories", "rid")
        self.assertEqual(recs[0].ts, sorted(r.ts for r in recs)[0])
        self.assertTrue(all(a.ts < b.ts for a, b in zip(recs, recs[1:])))

    def test_non_atif_document_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_trajectory({"foo": 1}, meta_doc(), "m", "t", "rid")

    def test_params_hash_is_deterministic(self):
        recs1, _ = convert_trajectory(traj_doc(), meta_doc(), "m", "t", "rid")
        recs2, _ = convert_trajectory(traj_doc(), meta_doc(), "m", "t", "rid")
        self.assertEqual(recs1[0].params_hash, recs2[0].params_hash)
        self.assertEqual(len(recs1[0].params_hash), 12)


class TestConvertTree(unittest.TestCase):
    def _write(self, base, task, model, tree, label, traj, meta):
        d = os.path.join(base, task, model, tree, label)
        os.makedirs(os.path.join(d, "trial", "agent"))
        with open(os.path.join(d, "metadata.json"), "w") as fh:
            json.dump(meta, fh)
        with open(os.path.join(d, "trial", "agent", "trajectory.json"), "w") as fh:
            json.dump(traj, fh)

    def test_tree_conversion_writes_ledger_labels_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks")
            self._write(tasks, "1012", "claude-opus-4.6", "hack_trajectories",
                        "v5", traj_doc(), meta_doc())
            self._write(tasks, "1012", "claude-opus-4.6", "baseline_trajectories",
                        "1", traj_doc(), meta_doc(classification="baseline",
                                                  judged_serious=False))
            # derived trees must be ignored:
            self._write(tasks, "1012", "claude-opus-4.6", "sanitized_trajectories",
                        "v5", traj_doc(), meta_doc())

            out = os.path.join(tmp, "out")
            manifest = convert_tree(tasks, out)

            self.assertEqual(manifest["n_runs_total"], 2)
            self.assertEqual(manifest["n_records_total"], 6)
            recs = list(read_jsonl(os.path.join(out, "claude-opus-4.6.jsonl")))
            self.assertEqual(len(recs), 6)
            self.assertEqual(
                {r.run_id for r in recs},
                {"1012/hack_trajectories/v5", "1012/baseline_trajectories/1"})
            with open(os.path.join(out, "claude-opus-4.6.labels.json")) as fh:
                labels = json.load(fh)
            self.assertEqual(
                {l["classification"] for l in labels.values()},
                {"rewarded_serious_exploit", "baseline"})
            entry = manifest["models"]["claude-opus-4.6"]
            self.assertEqual(len(entry["sha256_ledger"]), 64)

    def test_malformed_trajectory_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks")
            self._write(tasks, "1012", "m", "hack_trajectories", "v5",
                        traj_doc(), meta_doc())
            broken = os.path.join(tasks, "1013", "m", "hack_trajectories", "v5")
            os.makedirs(os.path.join(broken, "trial", "agent"))
            with open(os.path.join(broken, "metadata.json"), "w") as fh:
                json.dump(meta_doc(task_id="1013"), fh)
            with open(os.path.join(broken, "trial", "agent", "trajectory.json"), "w") as fh:
                fh.write("not json")

            manifest = convert_tree(tasks, os.path.join(tmp, "out"))
            self.assertEqual(manifest["n_runs_total"], 1)
            self.assertEqual(manifest["n_skipped"], 1)

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks")
            self._write(tasks, "1012", "m", "baseline_trajectories", "1",
                        traj_doc(), meta_doc(classification="baseline"))
            m1 = convert_tree(tasks, os.path.join(tmp, "out1"))
            m2 = convert_tree(tasks, os.path.join(tmp, "out2"))
            self.assertEqual(m1["models"]["m"]["sha256_ledger"],
                             m2["models"]["m"]["sha256_ledger"])


if __name__ == "__main__":
    unittest.main()
