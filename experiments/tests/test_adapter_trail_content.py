"""Unit tests for the TRAIL content-sidecar adapter (follow-up)."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.trail import convert_trace
from driftdetect.adapters.trail_content import content_lines, convert_tree
from tests.test_adapter_trail import trace_doc


class TestContentLines(unittest.TestCase):
    def test_alignment_with_l0_records(self):
        # The docstring's guarantee: same synthetic trace through both
        # modules, index-by-index agreement on (run_id, step_index, tool).
        trace = trace_doc()
        records, _ = convert_trace(trace, None, "gaia")
        lines = content_lines(trace, trace["trace_id"])
        self.assertEqual(len(lines), len(records))
        for rec, line in zip(records, lines):
            self.assertEqual(line["run_id"], rec.run_id)
            self.assertEqual(line["step_index"], rec.step_index)
            self.assertEqual(line["tool"], rec.tool)

    def test_channels_and_token_counts(self):
        trace = trace_doc()
        span = trace["spans"][0]
        span["span_attributes"] = {
            "openinference.span.kind": "LLM",
            "input.value": "the prompt",
            "output.value": '{"role": "assistant", "content": "the text"}',
            "llm.output_messages.0.message.content": "part one",
            "llm.output_messages.1.message.content": "part two",
            "llm.token_count.prompt": "1234",
            "llm.token_count.completion": "56",
        }
        line = content_lines(trace, trace["trace_id"])[0]
        self.assertEqual(line["kind"], "LLM")
        self.assertEqual(line["l1_text"], "the prompt")
        self.assertEqual(line["l2_text"],
                         '{"role": "assistant", "content": "the text"}')
        self.assertEqual(line["l3_text"], "part one\npart two")
        self.assertEqual(line["tokens_prompt"], 1234)
        self.assertEqual(line["tokens_completion"], 56)

    def test_missing_attributes_yield_empty_and_null(self):
        trace = trace_doc()
        trace["spans"][0]["span_attributes"] = {}
        line = content_lines(trace, trace["trace_id"])[0]
        self.assertEqual((line["kind"], line["l1_text"], line["l2_text"],
                          line["l3_text"]), ("", "", "", ""))
        self.assertIsNone(line["tokens_prompt"])
        self.assertIsNone(line["tokens_completion"])

    def test_unparsable_token_count_becomes_null(self):
        trace = trace_doc()
        trace["spans"][0]["span_attributes"] = {
            "llm.token_count.prompt": "n/a"}
        line = content_lines(trace, trace["trace_id"])[0]
        self.assertIsNone(line["tokens_prompt"])


class TestConvertTree(unittest.TestCase):
    def test_sidecar_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = os.path.join(tmp, "benchmarking")
            data = os.path.join(bench, "data", "GAIA")
            os.makedirs(data)
            trace = trace_doc()
            with open(os.path.join(data, f"{trace['trace_id']}.json"),
                      "w") as fh:
                json.dump(trace, fh)
            # a mismatched file name must be skipped, like the L0 adapter
            with open(os.path.join(data, "other-name.json"), "w") as fh:
                json.dump(trace, fh)

            out = os.path.join(tmp, "out")
            manifest = convert_tree(bench, out)

            self.assertEqual(manifest["n_skipped"], 1)
            entry = manifest["datasets"]["gaia"]
            self.assertEqual(entry["n_runs"], 1)
            self.assertEqual(len(entry["sha256_sidecar"]), 64)
            with open(os.path.join(out, "gaia.content.jsonl")) as fh:
                lines = [json.loads(x) for x in fh]
            self.assertEqual(len(lines), entry["n_lines"])
            self.assertEqual(lines[0]["run_id"], trace["trace_id"])


if __name__ == "__main__":
    unittest.main()
