"""Unit tests for the AgentDojo adapter, on a synthetic mini runs/ tree."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.agentdojo import convert_run, convert_tree
from driftdetect.records import read_jsonl


def run_doc(pipeline="model-a", suite="travel", task="user_task_1",
            attack=None, injection=None, security=True, utility=True,
            duration=10.0, calls=(("tool_x", {"a": 1}, None), ("tool_y", {}, None))):
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    for i, (fn, args, error) in enumerate(calls):
        cid = f"call_{i}"
        messages.append({"role": "assistant", "content": "",
                         "tool_calls": [{"function": fn, "args": args, "id": cid,
                                         "placeholder_args": None}]})
        messages.append({"role": "tool", "content": "result", "tool_call_id": cid,
                         "tool_call": {}, "error": error})
    return {
        "suite_name": suite, "pipeline_name": pipeline, "user_task_id": task,
        "injection_task_id": injection, "attack_type": attack, "injections": {},
        "error": None, "utility": utility, "security": security,
        "duration": duration, "messages": messages,
    }


class TestConvertRun(unittest.TestCase):
    def test_records_follow_transcript_order(self):
        recs, label = convert_run(run_doc(), "model-a/travel/user_task_1/none/none", 0)
        self.assertEqual([r.tool for r in recs], ["tool_x", "tool_y"])
        self.assertEqual([r.step_index for r in recs], [0, 1])
        self.assertEqual({r.goal_id for r in recs}, {"travel/user_task_1"})
        self.assertEqual({r.status for r in recs}, {"ok"})
        self.assertEqual(label["attacked"], False)
        self.assertEqual(label["injection_success"], False)
        self.assertEqual(label["n_calls"], 2)

    def test_tool_error_maps_to_error_status(self):
        doc = run_doc(calls=(("tool_x", {}, "ValueError: boom"), ("tool_y", {}, None)))
        recs, _ = convert_run(doc, "rid", 0)
        self.assertEqual([r.status for r in recs], ["error", "ok"])

    def test_string_none_error_is_not_an_error(self):
        doc = run_doc(calls=(("tool_x", {}, "None"),))
        recs, _ = convert_run(doc, "rid", 0)
        self.assertEqual(recs[0].status, "ok")

    def test_injection_success_needs_attack_and_security_true(self):
        # AgentDojo's `security` is True when the injection goal WAS executed
        # (see adapter docstring) — the name suggests the opposite.
        doc = run_doc(attack="important_instructions", injection="injection_task_4",
                      security=True)
        _, label = convert_run(doc, "rid", 0)
        self.assertTrue(label["attacked"])
        self.assertTrue(label["injection_success"])
        # attacked but the injection goal was not reached:
        _, label2 = convert_run(run_doc(attack="important_instructions",
                                        security=False), "rid", 0)
        self.assertFalse(label2["injection_success"])
        # benign runs carry security=True vacuously; never a success:
        _, label3 = convert_run(run_doc(security=True), "rid", 0)
        self.assertFalse(label3["injection_success"])

    def test_params_hash_is_deterministic_and_content_free(self):
        recs1, _ = convert_run(run_doc(), "rid", 0)
        recs2, _ = convert_run(run_doc(), "rid", 0)
        self.assertEqual(recs1[0].params_hash, recs2[0].params_hash)
        self.assertNotIn("a", recs1[0].params_hash)  # 12-hex-digit hash, no content
        self.assertEqual(len(recs1[0].params_hash), 12)

    def test_duration_spread_uniformly(self):
        recs, _ = convert_run(run_doc(duration=10.0), "rid", 0)
        self.assertEqual([r.duration_ms for r in recs], [5000.0, 5000.0])


class TestConvertTree(unittest.TestCase):
    def test_tree_conversion_writes_ledger_labels_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = os.path.join(tmp, "runs")
            benign = os.path.join(runs, "model-a", "travel", "user_task_1", "none")
            attacked = os.path.join(runs, "model-a", "travel", "user_task_1",
                                    "important_instructions")
            os.makedirs(benign)
            os.makedirs(attacked)
            with open(os.path.join(benign, "none.json"), "w") as fh:
                json.dump(run_doc(), fh)
            with open(os.path.join(attacked, "injection_task_1.json"), "w") as fh:
                json.dump(run_doc(attack="important_instructions",
                                  injection="injection_task_1", security=True), fh)

            out = os.path.join(tmp, "out")
            manifest = convert_tree(runs, out)

            self.assertEqual(manifest["n_runs_total"], 2)
            self.assertEqual(manifest["n_records_total"], 4)
            recs = list(read_jsonl(os.path.join(out, "model-a.jsonl")))
            self.assertEqual(len(recs), 4)
            self.assertEqual(len({r.run_id for r in recs}), 2)
            with open(os.path.join(out, "model-a.labels.json")) as fh:
                labels = json.load(fh)
            self.assertEqual(len(labels), 2)
            self.assertEqual(sum(1 for l in labels.values() if l["injection_success"]), 1)
            # manifest names its outputs by hash
            entry = manifest["pipelines"]["model-a"]
            self.assertEqual(len(entry["sha256_ledger"]), 64)

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = os.path.join(tmp, "runs")
            d = os.path.join(runs, "model-a", "travel", "user_task_1", "none")
            os.makedirs(d)
            with open(os.path.join(d, "none.json"), "w") as fh:
                json.dump(run_doc(), fh)
            m1 = convert_tree(runs, os.path.join(tmp, "out1"))
            m2 = convert_tree(runs, os.path.join(tmp, "out2"))
            self.assertEqual(m1["pipelines"]["model-a"]["sha256_ledger"],
                             m2["pipelines"]["model-a"]["sha256_ledger"])


if __name__ == "__main__":
    unittest.main()
