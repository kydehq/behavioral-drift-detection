"""Unit tests for the AgentDojo content-sidecar adapter (follow-up)."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.agentdojo import convert_run
from driftdetect.adapters.agentdojo_content import (
    content_lines, convert_tree, injected_strings,
)
from tests.test_adapter_agentdojo import run_doc


class TestContentLines(unittest.TestCase):
    def test_alignment_with_l0_records(self):
        # The docstring's guarantee: same synthetic run through both
        # modules, index-by-index agreement on (run_id, step_index, tool).
        doc = run_doc(calls=(("tool_x", {"a": 1}, None), ("tool_y", {}, None)))
        rid = "model-a/travel/user_task_1/none/none"
        records, _ = convert_run(doc, rid, 0)
        lines = content_lines(doc, rid)
        self.assertEqual(len(lines), len(records))
        for rec, line in zip(records, lines):
            self.assertEqual(line["run_id"], rec.run_id)
            self.assertEqual(line["step_index"], rec.step_index)
            self.assertEqual(line["tool"], rec.tool)

    def test_l1_is_canonical_json_of_args(self):
        doc = run_doc(calls=(("tool_x", {"b": 2, "a": 1}, None),))
        (line,) = content_lines(doc, "rid")
        self.assertEqual(line["l1_text"], '{"a": 1, "b": 2}')

    def test_l2_matched_by_tool_call_id(self):
        # run_doc emits one tool-result message per call with content
        # "result"; a call whose id has no result message yields "".
        doc = run_doc(calls=(("tool_x", {}, None),))
        doc["messages"].append({"role": "assistant", "content": "done",
                                "tool_calls": [{"function": "tool_z",
                                                "args": {}, "id": "call_99",
                                                "placeholder_args": None}]})
        lines = content_lines(doc, "rid")
        self.assertEqual([ln["l2_text"] for ln in lines], ["result", ""])

    def test_block_list_tool_result_yields_joined_text(self):
        # The Llama/SecAlign transcript shape: content is a list of
        # {"type": "text", "content": ...} blocks.
        doc = run_doc(calls=(("tool_x", {}, None),))
        for msg in doc["messages"]:
            if msg.get("role") == "tool":
                msg["content"] = [{"type": "text", "content": "part one"},
                                  {"type": "text", "content": "part two"}]
        (line,) = content_lines(doc, "rid")
        self.assertEqual(line["l2_text"], "part one\npart two")

    def test_non_string_tool_result_is_canonical_json(self):
        doc = run_doc(calls=(("tool_x", {}, None),))
        for msg in doc["messages"]:
            if msg.get("role") == "tool":
                msg["content"] = {"rows": [1, 2]}
        (line,) = content_lines(doc, "rid")
        self.assertEqual(line["l2_text"], '{"rows": [1, 2]}')

    def test_positional_pairing_when_ids_are_missing(self):
        # The gemini/command-r/Llama/SecAlign shape: tool_call_id is
        # ""/None on every message; results must pair with the first
        # unanswered call in transcript order.
        doc = run_doc(calls=(("tool_x", {}, None), ("tool_y", {}, None)))
        for i, msg in enumerate(m for m in doc["messages"]
                                if m.get("role") == "tool"):
            msg["tool_call_id"] = None
            msg["content"] = f"result {i}"
        for msg in doc["messages"]:
            for call in (msg.get("tool_calls") or []):
                call["id"] = ""
        lines = content_lines(doc, "rid")
        self.assertEqual([ln["l2_text"] for ln in lines],
                         ["result 0", "result 1"])

    def test_l3_repeats_per_call_in_multicall_message(self):
        doc = run_doc(calls=())
        doc["messages"].append({
            "role": "assistant", "content": "thinking aloud",
            "tool_calls": [
                {"function": "tool_x", "args": {}, "id": "c0",
                 "placeholder_args": None},
                {"function": "tool_y", "args": {}, "id": "c1",
                 "placeholder_args": None},
            ],
        })
        lines = content_lines(doc, "rid")
        self.assertEqual([ln["l3_text"] for ln in lines],
                         ["thinking aloud", "thinking aloud"])
        self.assertEqual([ln["step_index"] for ln in lines], [0, 1])


class TestInjectedStrings(unittest.TestCase):
    def test_attacked_run_yields_sorted_unique_strings(self):
        doc = run_doc(attack="ignore_previous", injection="injection_task_1")
        doc["injections"] = {"slot_b": "do B", "slot_a": "do A",
                             "slot_c": "do A"}
        self.assertEqual(injected_strings(doc), ["do A", "do B"])

    def test_benign_run_yields_nothing(self):
        doc = run_doc()
        doc["injections"] = {"slot_a": "leftover"}
        self.assertEqual(injected_strings(doc), [])


class TestConvertTree(unittest.TestCase):
    def test_sidecar_injections_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = os.path.join(tmp, "runs")
            rdir = os.path.join(runs, "model-a", "travel", "user_task_1")
            os.makedirs(os.path.join(rdir, "none"))
            os.makedirs(os.path.join(rdir, "ignore_previous"))
            benign = run_doc()
            attacked = run_doc(attack="ignore_previous",
                               injection="injection_task_1")
            attacked["injections"] = {"slot": "Ignore your previous"}
            with open(os.path.join(rdir, "none", "none.json"), "w") as fh:
                json.dump(benign, fh)
            with open(os.path.join(rdir, "ignore_previous",
                                   "injection_task_1.json"), "w") as fh:
                json.dump(attacked, fh)

            out = os.path.join(tmp, "out")
            manifest = convert_tree(runs, out)

            entry = manifest["pipelines"]["model-a"]
            self.assertEqual(entry["n_runs"], 2)
            self.assertEqual(entry["n_attacked"], 1)
            self.assertEqual(manifest["n_lines_total"], 4)
            with open(os.path.join(out, "model-a.injections.json")) as fh:
                injections = json.load(fh)
            self.assertEqual(injections, {
                "model-a/travel/user_task_1/ignore_previous/injection_task_1":
                    ["Ignore your previous"],
            })
            for key in ("sha256_sidecar", "sha256_injections"):
                self.assertEqual(len(entry[key]), 64)


if __name__ == "__main__":
    unittest.main()
