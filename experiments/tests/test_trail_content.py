"""Unit tests for the E3 TRAIL content experiment (follow-up)."""

import unittest

from driftdetect import eval_l3_terminalwrench
from driftdetect.eval_trail_content import (
    exec_delta_covered, exec_prompt_counts, is_dev, matched_signatures,
    norm_category, output_text, token_bin, token_bin_label,
)

EXEC_TEXT = ("Execution logs:\nError when executing tool page_down with "
             "arguments {'': ''}: TypeError: unexpected keyword argument")
CLEAN_TEXT = ("Address: google: LibreText Introductory Chemistry materials\n"
              "Pie Menus or Linear Menus, Which Is Better? Sep 2015.")


def llm_line(l1="", **kw):
    line = {"kind": "LLM", "l1_text": l1, "l2_text": "", "l3_text": "",
            "tokens_prompt": None, "tokens_completion": None}
    line.update(kw)
    return line


def tool_line(l2=""):
    return {"kind": "TOOL", "l1_text": "", "l2_text": l2, "l3_text": "",
            "tokens_prompt": None, "tokens_completion": None}


class TestSignatures(unittest.TestCase):
    def test_execution_error_text_matches(self):
        self.assertIn("exec_error", matched_signatures(EXEC_TEXT))
        self.assertIn("py_exception", matched_signatures(EXEC_TEXT))

    def test_clean_search_output_does_not_match(self):
        self.assertEqual(matched_signatures(CLEAN_TEXT), [])

    def test_output_text_never_reads_the_prompt(self):
        # l1 is the replay channel; measurement 1 must not see it.
        line = llm_line(l1=EXEC_TEXT, l2_text="fine", l3_text="also fine")
        self.assertEqual(matched_signatures(output_text(line)), [])

    def test_split_function_is_the_shared_one(self):
        self.assertIs(is_dev, eval_l3_terminalwrench.is_dev)


class TestNormCategory(unittest.TestCase):
    def test_corpus_spelling_variants_fold(self):
        self.assertEqual(norm_category("Formatting Errors"),
                         norm_category("Formatting Error"))
        self.assertEqual(norm_category("Context Handling Failures"),
                         norm_category("Context Handling Failure"))
        self.assertEqual(norm_category(" Incorrect Problem Identification"),
                         norm_category("Incorrect Problem Identification"))


class TestExecDelta(unittest.TestCase):
    def test_new_error_in_next_prompt_is_credited(self):
        lines = [llm_line(l1="clean history"),
                 tool_line(),                      # the annotated location
                 llm_line(l1="history\n" + EXEC_TEXT)]
        self.assertTrue(exec_delta_covered(1, exec_prompt_counts(lines)))

    def test_stale_replayed_error_is_not_credited(self):
        # The same single error string sits in the prompt before AND
        # after the location: nothing new arrived, no credit.
        lines = [llm_line(l1=EXEC_TEXT),
                 tool_line(),
                 llm_line(l1=EXEC_TEXT)]
        self.assertFalse(exec_delta_covered(1, exec_prompt_counts(lines)))

    def test_no_following_llm_call_means_no_credit(self):
        lines = [llm_line(l1="clean"), tool_line()]
        self.assertFalse(exec_delta_covered(1, exec_prompt_counts(lines)))

    def test_additional_occurrence_counts_as_new(self):
        lines = [llm_line(l1=EXEC_TEXT),
                 tool_line(),
                 llm_line(l1=EXEC_TEXT + "\n" + EXEC_TEXT)]
        self.assertTrue(exec_delta_covered(1, exec_prompt_counts(lines)))


class TestTokenBins(unittest.TestCase):
    def test_bin_edges_double(self):
        self.assertEqual(token_bin(1999), -1)
        self.assertEqual(token_bin(2000), 0)
        self.assertEqual(token_bin(3999), 0)
        self.assertEqual(token_bin(4000), 1)
        self.assertEqual(token_bin(16000), 3)

    def test_labels(self):
        self.assertEqual(token_bin_label(-1), "0–2,000")
        self.assertEqual(token_bin_label(0), "2,000–4,000")
        self.assertEqual(token_bin_label(3), "16,000–32,000")


if __name__ == "__main__":
    unittest.main()
