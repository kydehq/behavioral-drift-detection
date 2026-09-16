"""Unit tests for the SWE-bench adapter, on a synthetic mini submission tree."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.swebench import (
    _goal_id,
    _submission_epoch,
    convert_tree,
    detect_format,
)
from driftdetect.records import read_jsonl

SWEAGENT_DOC = {
    "environment": "swe_env",
    "trajectory": [
        {"action": "create reproduce.py\n", "observation": "[File created]"},
        {"action": "edit 1:1\nprint('x')\nend_of_edit", "observation": "[edited]"},
        {"action": "", "observation": "ignored"},
        {"action": "submit", "observation": "done"},
    ],
}

OPENAI_DOC = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "fix the bug"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "execute_bash", "arguments": "{\"command\": \"ls\"}"}},
    ]},
    {"role": "tool", "content": "files", "tool_call_id": "c1", "name": "execute_bash"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c2", "type": "function",
         "function": {"name": "finish", "arguments": "{}"}},
    ]},
]


def make_tree(tmp):
    root = os.path.join(tmp, "verified")
    d1 = os.path.join(root, "20240402_sweagent_x", "trajs")
    d2 = os.path.join(root, "20250415_openhands_y", "trajs")
    d3 = os.path.join(root, "20231010_rag_z", "logs")  # no trajs at all
    d4 = os.path.join(root, "20250804_epam_list", "trajs")   # .traj, top-level list
    d5 = os.path.join(root, "20250720_lingxi_text", "trajs")  # .traj, not JSON
    for d in (d1, d2, d3, d4, d5):
        os.makedirs(d)
    with open(os.path.join(d1, "astropy__astropy-12907.traj"), "w") as fh:
        json.dump(SWEAGENT_DOC, fh)
    with open(os.path.join(d2, "django__django-11099.json"), "w") as fh:
        json.dump(OPENAI_DOC, fh)
    with open(os.path.join(d4, "astropy__astropy-12907.traj"), "w") as fh:
        json.dump([{"uuid-1": {"author_name": "Thoughts", "message": "x"}}], fh)
    with open(os.path.join(d5, "astropy__astropy-12907.traj"), "w") as fh:
        fh.write("<issue_description>\nplain text, not JSON\n")
    return root


class TestHelpers(unittest.TestCase):
    def test_goal_id_is_repo(self):
        self.assertEqual(_goal_id("astropy__astropy-12907"), "astropy__astropy")
        self.assertEqual(_goal_id("norepo"), "norepo")

    def test_epoch_from_submission_date(self):
        self.assertEqual(_submission_epoch("20240402_sweagent_x"), 1712016000.0)
        # no date prefix -> fixed fallback, still deterministic
        self.assertEqual(_submission_epoch("nodate"), _submission_epoch("nodate"))


class TestConvertTree(unittest.TestCase):
    def test_formats_detected_and_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            self.assertEqual(
                detect_format(os.path.join(root, "20240402_sweagent_x", "trajs")),
                "sweagent")
            self.assertEqual(
                detect_format(os.path.join(root, "20250415_openhands_y", "trajs")),
                "openai_messages")

            out = os.path.join(tmp, "out")
            manifest = convert_tree(root, out)

            self.assertIn("20231010_rag_z", manifest["skipped"])
            # bespoke .traj reuses (list-shaped JSON, plain text) must not
            # crash the conversion — they end up skipped with a reason
            self.assertIn("20250804_epam_list", manifest["skipped"])
            self.assertIn("20250720_lingxi_text", manifest["skipped"])
            self.assertIn("no parsable runs", manifest["skipped"]["20250804_epam_list"])
            self.assertEqual(manifest["n_runs_total"], 2)

            recs = list(read_jsonl(os.path.join(out, "20240402_sweagent_x.jsonl")))
            # empty action dropped: create, edit, submit
            self.assertEqual([r.tool for r in recs], ["create", "edit", "submit"])
            self.assertEqual(recs[0].run_id, "astropy__astropy-12907")
            self.assertEqual(recs[0].goal_id, "astropy__astropy")
            self.assertEqual({r.status for r in recs}, {"ok"})

            recs2 = list(read_jsonl(os.path.join(out, "20250415_openhands_y.jsonl")))
            self.assertEqual([r.tool for r in recs2], ["execute_bash", "finish"])

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(tmp)
            m1 = convert_tree(root, os.path.join(tmp, "o1"))
            m2 = convert_tree(root, os.path.join(tmp, "o2"))
            self.assertEqual(
                m1["submissions"]["20240402_sweagent_x"]["sha256_ledger"],
                m2["submissions"]["20240402_sweagent_x"]["sha256_ledger"],
            )


if __name__ == "__main__":
    unittest.main()
