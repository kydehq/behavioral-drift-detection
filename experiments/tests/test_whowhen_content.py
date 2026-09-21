"""Unit tests for the E4 Who&When content experiment (follow-up)."""

import json
import os
import tempfile
import unittest

from driftdetect import eval_l3_terminalwrench
from driftdetect.adapters.whowhen import convert_run
from driftdetect.adapters.whowhen_content import content_lines, convert_tree
from driftdetect.eval_whowhen_content import (
    ERROR_SIGNATURE, is_dev, is_worker, predict,
)
from tests.test_adapter_whowhen import ag_doc

ERROR_TEXT = ("exitcode: 1 (execution failed)\nTraceback (most recent call "
              "last):\n  File 'x.py', line 3")
APOLOGY_TEXT = "I apologize for the confusion — the previous filter didn't work."
CLEAN_TEXT = "Here is the list of series Ted Danson has starred in."


class TestAdapterAlignment(unittest.TestCase):
    def test_alignment_with_l0_records(self):
        doc = ag_doc()
        records, _ = convert_run(doc, "algorithm-generated", "ag/1")
        lines = content_lines(doc, "ag/1")
        self.assertEqual(len(lines), len(records))
        for rec, line in zip(records, lines):
            self.assertEqual(line["run_id"], rec.run_id)
            self.assertEqual(line["step_index"], rec.step_index)
            self.assertEqual(line["tool"], rec.tool)

    def test_entry_without_seam_label_is_skipped_with_hole(self):
        doc = ag_doc()
        doc["history"].insert(1, {"content": "orphan text"})
        lines = content_lines(doc, "rid")
        self.assertNotIn(1, [ln["step_index"] for ln in lines])
        self.assertEqual(lines[1]["step_index"], 2)

    def test_convert_tree_writes_sidecar_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            vdir = os.path.join(tmp, "Algorithm-Generated")
            os.makedirs(vdir)
            with open(os.path.join(vdir, "1.json"), "w") as fh:
                json.dump(ag_doc(), fh)
            out = os.path.join(tmp, "out")
            manifest = convert_tree(tmp, out)
            entry = manifest["variants"]["algorithm-generated"]
            self.assertEqual(entry["n_runs"], 1)
            self.assertEqual(len(entry["sha256_sidecar"]), 64)


class TestPredictors(unittest.TestCase):
    def _seq(self, texts, labels=None):
        labels = labels or ["Agent_A"] * len(texts)
        return [(i, labels[i], texts[i]) for i in range(len(texts))]

    def test_error_signature(self):
        self.assertTrue(ERROR_SIGNATURE.search(ERROR_TEXT))
        self.assertFalse(ERROR_SIGNATURE.search(CLEAN_TEXT))

    def test_before_first_error_names_the_causer(self):
        seq = self._seq([CLEAN_TEXT, CLEAN_TEXT, ERROR_TEXT, CLEAN_TEXT])
        preds = predict(seq)
        self.assertEqual(preds["first_error"], 2)
        self.assertEqual(preds["before_first_error"], 1)

    def test_no_match_falls_back_to_first(self):
        seq = self._seq([CLEAN_TEXT, CLEAN_TEXT])
        preds = predict(seq)
        self.assertEqual(preds["first_error"], 0)
        self.assertEqual(preds["before_first_apology"], 0)

    def test_before_first_apology(self):
        seq = self._seq([CLEAN_TEXT, APOLOGY_TEXT])
        self.assertEqual(predict(seq)["before_first_apology"], 0)

    def test_worker_predictors_skip_orchestrator_frames(self):
        seq = [(0, "human", "task"),
               (1, "Orchestrator (-> WebSurfer)", "Next speaker WebSurfer"),
               (2, "WebSurfer", CLEAN_TEXT),
               (3, "Orchestrator (thought)", "Updated Ledger: ..."),
               (4, "FileSurfer", CLEAN_TEXT)]
        preds = predict(seq)
        self.assertEqual(preds["first_worker"], 2)
        self.assertEqual(preds["second_worker"], 4)

    def test_is_worker(self):
        self.assertTrue(is_worker("WebSurfer"))
        self.assertFalse(is_worker("Orchestrator (-> WebSurfer)"))
        self.assertFalse(is_worker("human"))

    def test_positional_baselines(self):
        seq = self._seq([CLEAN_TEXT] * 5)
        preds = predict(seq)
        self.assertEqual((preds["first"], preds["third"], preds["middle"],
                          preds["last"]), (0, 2, 2, 4))

    def test_split_function_is_the_shared_one(self):
        self.assertIs(is_dev, eval_l3_terminalwrench.is_dev)


if __name__ == "__main__":
    unittest.main()
