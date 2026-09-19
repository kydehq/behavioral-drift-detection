"""Unit tests for the TRACE content sidecar and the frozen-detector transfer."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.trace import convert_export as l0_convert
from driftdetect.adapters.trace import convert_trajectory
from driftdetect.adapters.trace_content import (
    content_lines, convert_export as content_convert, l1_text,
)
from driftdetect.eval_trace_transfer import evaluate, load_texts
from tests.test_adapter_trace import traj_doc
from tests.test_l1b_terminalwrench import CLEAN_TEXT, RECON_TEXT
from tests.test_l3_terminalwrench import HACK_TEXT


class TestL1Text(unittest.TestCase):
    def test_string_params_sorted_by_key(self):
        call = {"name": "Bash", "parameters": {
            "description": "run tests", "command": "npm test",
            "timeout": 5000, "run_in_background": False}}
        self.assertEqual(l1_text(call), "npm test\nrun tests")

    def test_edit_includes_written_content(self):
        call = {"name": "Edit", "parameters": {
            "file_path": "/srv/a.js", "old_string": "x", "new_string": "y"}}
        self.assertEqual(l1_text(call), "/srv/a.js\ny\nx")


class TestSidecarAlignment(unittest.TestCase):
    def test_lines_align_with_l0_records(self):
        doc = traj_doc()
        records, _ = convert_trajectory(doc)
        lines = content_lines(doc)
        self.assertEqual([l["step_index"] for l in lines],
                         [r.step_index for r in records])
        self.assertEqual([l["tool"] for l in lines],
                         [r.tool for r in records])
        self.assertEqual({l["l3_text"] for l in lines}, {"thinking"})
        self.assertIn("cd /srv && npm test", lines[1]["l1_text"])

    def test_export_conversion_matches_l0_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = os.path.join(tmp, "trajectories.jsonl")
            with open(export, "w") as fh:
                for i in range(3):
                    fh.write(json.dumps(traj_doc(f"trajectory_{i:04d}")) + "\n")
            l0 = l0_convert(export, os.path.join(tmp, "l0"))
            content = content_convert(export, os.path.join(tmp, "content"))
            self.assertEqual(l0["n_records_total"], content["n_lines_total"])
            self.assertEqual(
                len(content["models"]["trace"]["sha256_sidecar"]), 64)


class TestTransferEvaluate(unittest.TestCase):
    def _corpus(self, tmp):
        # Two trajectories: a clean one and one whose commands trip the
        # frozen L1b recon rule and whose messages trip the L3 patterns.
        docs = [
            traj_doc("trajectory_0001", label="0",
                     calls=(("Bash", {"command": CLEAN_TEXT}),)),
            traj_doc("trajectory_0002", label="1.1.2",
                     calls=(("Bash", {"command": RECON_TEXT}),)),
        ]
        for m in docs[1]["conversation"]:
            if m["role"] == "assistant":
                m["content"] = HACK_TEXT
        export = os.path.join(tmp, "trajectories.jsonl")
        with open(export, "w") as fh:
            for doc in docs:
                fh.write(json.dumps(doc) + "\n")
        l0_convert(export, tmp)
        content_convert(export, tmp)

    def test_load_texts_concatenates_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._corpus(tmp)
            l1_texts, l3_texts = load_texts(tmp)
            self.assertIn("find / -name 'verify*'",
                          l1_texts["trajectory_0002"])
            # per-message dedupe: the repeated content appears once
            self.assertEqual(l3_texts["trajectory_0002"].count("bypass"), 1)

    def test_frozen_detectors_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._corpus(tmp)
            res = evaluate(tmp, tmp)
            self.assertEqual((res["n_clean"], res["n_hacked"]), (1, 1))
            for row in res["rows"]:
                self.assertEqual(row["detection"], 1.0, row)
                self.assertEqual(row["fpr"], 0.0, row)
            self.assertEqual(
                res["coverage"]["L1b rules"]["verifier_recon"]["hacked"], 1)


if __name__ == "__main__":
    unittest.main()
