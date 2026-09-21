"""Unit tests for the AgentHallu adapter and E4b experiment (follow-up)."""

import json
import os
import tempfile
import unittest

from driftdetect import eval_l3_terminalwrench
from driftdetect.adapters.agenthallu import (
    _bool_label, content_lines, convert_tree, run_label,
)
from driftdetect.eval_agenthallu import (
    final_message, is_dev, is_worker_local, unacknowledged_error,
)


def trajectory(is_hallucination="true", step="1", with_tools=True):
    entry = {"step": "1", "role": "assistant", "content": ""}
    if with_tools:
        entry["tool_calls"] = "[{'name': 'mv', 'arguments': {}}]"
        entry["tool_responses"] = ('[\'{"error": "mv: cannot move"}\']')
    return {
        "agent_type": "BFCL", "model_id": "m", "question": "q",
        "question_domain": "d", "question_source": "s",
        "agent_answer": "a", "true_answer": "t",
        "is_hallucination": is_hallucination,
        "hallucination_step": step,
        "hallucination_category": "Tool-Use Hallucination",
        "explanation": "why",
        "history": [entry,
                    {"step": "2", "role": "assistant",
                     "content": "All files moved successfully."}],
    }


class TestAdapter(unittest.TestCase):
    def test_string_labels_parse_to_real_bools(self):
        # The corpus stores "true"/"false" as strings; bool() on them
        # would label every run hallucinated (adapter docstring).
        self.assertTrue(_bool_label("true"))
        self.assertFalse(_bool_label("false"))
        self.assertFalse(_bool_label(None))
        label = run_label(trajectory(is_hallucination="false"), "bfcl")
        self.assertFalse(label["is_hallucination"])

    def test_channels_split_by_rung(self):
        lines = content_lines(trajectory(), "bfcl/000")
        self.assertEqual(len(lines), 2)
        first = lines[0]
        self.assertEqual(first["step_index"], 0)
        self.assertEqual(first["step_source"], 1)
        self.assertIn("mv", first["l1_text"])
        self.assertIn("error", first["l2_text"])
        self.assertEqual(first["l3_text"], "")
        self.assertEqual(lines[1]["l2_text"], "")
        self.assertIn("successfully", lines[1]["l3_text"])

    def test_label_keeps_step_as_int(self):
        label = run_label(trajectory(step="3"), "bfcl")
        self.assertEqual(label["hallucination_step"], 3)
        self.assertIsNone(run_label(trajectory(step=None), "bfcl")
                          ["hallucination_step"])

    def test_convert_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            fdir = os.path.join(tmp, "BFCL")
            os.makedirs(fdir)
            for i, hall in enumerate(("true", "false")):
                with open(os.path.join(fdir, f"{i:03d}.json"), "w") as fh:
                    json.dump(trajectory(is_hallucination=hall), fh)
            out = os.path.join(tmp, "out")
            manifest = convert_tree(tmp, out)
            entry = manifest["frameworks"]["bfcl"]
            self.assertEqual((entry["n_runs"], entry["n_hallucinated"],
                              entry["n_clean"]), (2, 1, 1))
            self.assertEqual(len(entry["sha256_ledger"]), 64)


class TestDetectionRule(unittest.TestCase):
    def _seq(self, doc):
        return content_lines(doc, "rid")

    def test_error_without_acknowledgment_is_flagged(self):
        self.assertTrue(unacknowledged_error(self._seq(trajectory())))

    def test_acknowledged_error_is_not_flagged(self):
        doc = trajectory()
        doc["history"][1]["content"] = ("The move failed with an error; "
                                        "I could not complete the request.")
        self.assertFalse(unacknowledged_error(self._seq(doc)))

    def test_clean_tool_responses_are_not_flagged(self):
        doc = trajectory()
        doc["history"][0]["tool_responses"] = "['{\"ok\": true}']"
        self.assertFalse(unacknowledged_error(self._seq(doc)))

    def test_text_only_run_cannot_fire(self):
        # Four frameworks log no tool responses at all: the rule's
        # channel does not exist there (module docstring).
        self.assertFalse(unacknowledged_error(
            self._seq(trajectory(with_tools=False))))

    def test_final_message_is_last_nonempty_l3(self):
        seq = self._seq(trajectory())
        self.assertIn("successfully", final_message(seq))

    def test_worker_local_spelling(self):
        self.assertFalse(is_worker_local("MagenticOneOrchestrator"))
        self.assertTrue(is_worker_local("WebSurfer"))
        self.assertFalse(is_worker_local("user"))

    def test_split_function_is_the_shared_one(self):
        self.assertIs(is_dev, eval_l3_terminalwrench.is_dev)


if __name__ == "__main__":
    unittest.main()
