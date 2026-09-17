"""Unit tests for the Who&When adapter, on synthetic mini runs."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.whowhen import convert_run, convert_tree
from driftdetect.eval_whowhen import speaker
from driftdetect.records import read_jsonl


def ag_doc(question_id="qid-1", mistake_agent="Excel_Expert",
           mistake_step="1"):
    return {
        "is_correct": False,
        "question": "q",
        "question_ID": question_id,
        "level": 2,
        "ground_truth": "42",
        "history": [
            {"content": "plan", "role": "assistant", "name": "Excel_Expert"},
            {"content": "run it", "role": "user", "name": "Computer_terminal"},
            {"content": "done", "role": "assistant", "name": "Excel_Expert"},
        ],
        "mistake_agent": mistake_agent,
        "mistake_step": mistake_step,
        "mistake_reason": "edge case",
        "system_prompt": {"Excel_Expert": "..."},
    }


def hc_doc(question_id="qid-2"):
    return {
        "question": "q",
        "groundtruth": "g",
        "is_corrected": "False",
        "question_ID": question_id,
        "history": [
            {"content": "req", "role": "human"},
            {"content": "plan", "role": "Orchestrator (thought)"},
            {"content": "go", "role": "Orchestrator (-> WebSurfer)"},
            {"content": "page", "role": "WebSurfer"},
        ],
        "mistake_agent": "WebSurfer",
        "mistake_step": "3",
        "mistake_reason": "wrong click",
    }


class TestConvertRun(unittest.TestCase):
    def test_ag_seam_label_is_the_name(self):
        recs, label = convert_run(ag_doc(), "algorithm-generated",
                                  "algorithm-generated/1")
        self.assertEqual([r.tool for r in recs],
                         ["Excel_Expert", "Computer_terminal", "Excel_Expert"])
        self.assertEqual([r.step_index for r in recs], [0, 1, 2])
        self.assertEqual({r.agent_id for r in recs}, {"algorithm-generated"})
        self.assertEqual({r.goal_id for r in recs}, {"qid-1"})
        self.assertEqual({r.status for r in recs}, {"ok"})
        self.assertEqual(label["mistake_agent"], "Excel_Expert")
        self.assertEqual(label["mistake_step"], "1")
        self.assertIs(label["is_correct"], False)
        self.assertEqual(label["n_calls"], 3)

    def test_hc_seam_label_is_the_role(self):
        recs, label = convert_run(hc_doc(), "hand-crafted", "hand-crafted/1")
        self.assertEqual([r.tool for r in recs],
                         ["human", "Orchestrator (thought)",
                          "Orchestrator (-> WebSurfer)", "WebSurfer"])
        self.assertEqual(label["is_corrected"], "False")
        self.assertIsNone(label["is_correct"])

    def test_speaker_canonicalization(self):
        self.assertEqual(speaker("Orchestrator (-> WebSurfer)"),
                         "Orchestrator")
        self.assertEqual(speaker("Orchestrator (thought)"), "Orchestrator")
        self.assertEqual(speaker("WebSurfer"), "WebSurfer")
        self.assertEqual(speaker("Excel_Expert"), "Excel_Expert")

    def test_non_run_document_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_run({"foo": 1}, "k", "k/1")
        doc = ag_doc()
        del doc["question_ID"]
        with self.assertRaises(ValueError):
            convert_run(doc, "k", "k/1")

    def test_params_hash_is_deterministic(self):
        recs1, _ = convert_run(ag_doc(), "k", "k/1")
        recs2, _ = convert_run(ag_doc(), "k", "k/1")
        self.assertEqual(recs1[0].params_hash, recs2[0].params_hash)
        self.assertEqual(len(recs1[0].params_hash), 12)


class TestConvertTree(unittest.TestCase):
    def _write(self, root, variant_dir, fname, doc):
        d = os.path.join(root, variant_dir)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, fname), "w") as fh:
            json.dump(doc, fh)

    def test_tree_conversion_writes_ledger_labels_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Who&When")
            self._write(root, "Algorithm-Generated", "1.json", ag_doc())
            self._write(root, "Hand-Crafted", "1.json", hc_doc())

            out = os.path.join(tmp, "out")
            manifest = convert_tree(root, out)

            self.assertEqual(manifest["n_runs_total"], 2)
            self.assertEqual(manifest["n_records_total"], 7)
            self.assertEqual(set(manifest["variants"]),
                             {"algorithm-generated", "hand-crafted"})
            recs = list(read_jsonl(
                os.path.join(out, "algorithm-generated.jsonl")))
            self.assertEqual({r.run_id for r in recs},
                             {"algorithm-generated/1"})
            with open(os.path.join(out, "hand-crafted.labels.json")) as fh:
                labels = json.load(fh)
            self.assertEqual(labels["hand-crafted/1"]["mistake_agent"],
                             "WebSurfer")
            entry = manifest["variants"]["algorithm-generated"]
            self.assertEqual(len(entry["sha256_ledger"]), 64)

    def test_numeric_filename_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Who&When")
            for n in ("10", "2", "1"):
                self._write(root, "Algorithm-Generated", f"{n}.json",
                            ag_doc(question_id=f"qid-{n}"))
            out = os.path.join(tmp, "out")
            convert_tree(root, out)
            recs = list(read_jsonl(
                os.path.join(out, "algorithm-generated.jsonl")))
            seen = list(dict.fromkeys(r.run_id for r in recs))
            self.assertEqual(seen, ["algorithm-generated/1",
                                    "algorithm-generated/2",
                                    "algorithm-generated/10"])

    def test_malformed_run_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Who&When")
            self._write(root, "Algorithm-Generated", "1.json", ag_doc())
            d = os.path.join(root, "Algorithm-Generated")
            with open(os.path.join(d, "2.json"), "w") as fh:
                fh.write("not json")

            manifest = convert_tree(root, os.path.join(tmp, "out"))
            self.assertEqual(manifest["n_runs_total"], 1)
            self.assertEqual(manifest["n_skipped"], 1)

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "Who&When")
            self._write(root, "Hand-Crafted", "1.json", hc_doc())
            m1 = convert_tree(root, os.path.join(tmp, "out1"))
            m2 = convert_tree(root, os.path.join(tmp, "out2"))
            self.assertEqual(m1["variants"]["hand-crafted"]["sha256_ledger"],
                             m2["variants"]["hand-crafted"]["sha256_ledger"])


if __name__ == "__main__":
    unittest.main()
