"""Unit tests for the L1 content sidecar and tokenizer (follow-up E1)."""

import json
import math
import os
import random
import tempfile
import unittest

from driftdetect.adapters.terminalwrench import convert_tree as l0_convert
from driftdetect.adapters.terminalwrench_content import (
    content_lines, convert_tree as content_convert,
)
from driftdetect.baseline import freeze_baseline
from driftdetect.detectors import DivergenceChannel
from driftdetect.eval_agentdojo import perrun_trial, stream_trial
from driftdetect.eval_l1_terminalwrench import (
    FastDivergenceChannel, canonical_tokens, fast_perrun_trial,
    fast_stream_trial, token_runs,
)
from driftdetect.records import CallRecord, read_jsonl, group_by_run
from tests.test_adapter_terminalwrench import meta_doc, traj_doc


def _rec(rid: str, k: int, tool: str) -> CallRecord:
    return CallRecord(ts=float(k), run_id=rid, agent_id="a", model="m",
                      model_version="1", goal_id="g", step_index=k,
                      tool=tool, params_hash="0" * 12, status="ok",
                      duration_ms=0.0)


class TestCanonicalTokens(unittest.TestCase):
    def test_full_command_tokens(self):
        self.assertEqual(
            canonical_tokens("cat /etc/passwd | grep root\n", "cat"),
            ["cat", "/etc/passwd", "|", "grep", "root"])

    def test_num_hex_long_classes(self):
        toks = canonical_tokens(
            "kill 4242 deadbeefdeadbeef " + "x" * 65, "kill")
        self.assertEqual(toks, ["kill", "<num>", "<hex>", "<long>"])

    def test_unbalanced_quote_falls_back_to_whitespace(self):
        toks = canonical_tokens("echo \"broken\n", "echo")
        self.assertEqual(toks, ["echo", '"broken'])

    def test_empty_text_keeps_tool_name(self):
        self.assertEqual(canonical_tokens("", "mark_task_complete"),
                         ["mark_task_complete"])


class TestSidecarAlignment(unittest.TestCase):
    def test_lines_align_with_l0_records(self):
        traj = traj_doc()
        lines = content_lines(traj, "1012/hack_trajectories/v5")
        self.assertEqual([l["step_index"] for l in lines], [0, 1, 2])
        self.assertEqual([l["tool"] for l in lines],
                         ["mkdir", "cat", "mark_task_complete"])
        self.assertEqual(lines[0]["l1_text"], "mkdir -p /tmp/x\n")
        self.assertEqual(lines[2]["l1_text"], "")
        self.assertEqual({l["l3_text"] for l in lines}, {"thinking"})

    def test_tree_conversion_matches_l0_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks")
            d = os.path.join(tasks, "1012", "m", "hack_trajectories", "v5")
            os.makedirs(os.path.join(d, "trial", "agent"))
            with open(os.path.join(d, "metadata.json"), "w") as fh:
                json.dump(meta_doc(), fh)
            with open(os.path.join(d, "trial", "agent", "trajectory.json"), "w") as fh:
                json.dump(traj_doc(), fh)

            l0 = l0_convert(tasks, os.path.join(tmp, "l0"))
            content = content_convert(tasks, os.path.join(tmp, "content"))
            self.assertEqual(l0["n_records_total"], content["n_lines_total"])
            self.assertEqual(len(content["models"]["m"]["sha256_sidecar"]), 64)

    def test_token_runs_expand_and_reindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            tasks = os.path.join(tmp, "tasks")
            d = os.path.join(tasks, "1012", "m", "hack_trajectories", "v5")
            os.makedirs(os.path.join(d, "trial", "agent"))
            with open(os.path.join(d, "metadata.json"), "w") as fh:
                json.dump(meta_doc(), fh)
            with open(os.path.join(d, "trial", "agent", "trajectory.json"), "w") as fh:
                json.dump(traj_doc(), fh)
            l0_convert(tasks, os.path.join(tmp, "l0"))
            content_convert(tasks, os.path.join(tmp, "content"))

            runs = group_by_run(read_jsonl(os.path.join(tmp, "l0", "m.jsonl")))
            sidecar = {}
            with open(os.path.join(tmp, "content", "m.content.jsonl")) as fh:
                for raw in fh:
                    line = json.loads(raw)
                    sidecar[(line["run_id"], line["step_index"])] = line
            expanded = token_runs(runs, sidecar)
            recs = expanded["1012/hack_trajectories/v5"]
            # mkdir -p /tmp/x + cat /tmp/x/f + mark_task_complete = 3+2+1
            self.assertEqual([r.tool for r in recs],
                             ["mkdir", "-p", "/tmp/x", "cat", "/tmp/x/f",
                              "mark_task_complete"])
            self.assertEqual([r.step_index for r in recs], list(range(6)))

    def test_sidecar_is_deterministic(self):
        traj = traj_doc()
        self.assertEqual(content_lines(traj, "r"), content_lines(traj, "r"))


class TestFastDivergenceChannel(unittest.TestCase):
    """FastDivergenceChannel vs. DivergenceChannel: same scores (to floating-
    point tolerance — the summation order differs, and the original itself is
    not bit-stable across processes because js_divergence iterates a set),
    same alarm trajectory, on streams exercising every term class: window
    tokens seen at baseline, window tokens unseen at baseline (q_t = 0), and
    baseline tokens absent from the window (the precomputed rest term)."""

    VOCAB = [f"t{i:03d}" for i in range(300)]

    def _baseline(self, rng):
        weights = [1.0 / (i + 1) for i in range(len(self.VOCAB))]
        records = [
            _rec(f"b{k // 40}", k, rng.choices(self.VOCAB, weights)[0])
            for k in range(4000)
        ]
        return freeze_baseline(records), weights

    def _assert_equivalent(self, baseline, stream, threshold, expect_alarm):
        # threshold is set per stream (a 25-token window over a 300-token
        # vocabulary sits well above the 0.15 default even in control —
        # which is why the experiments calibrate it).
        slow = DivergenceChannel(baseline, window=25, threshold=threshold)
        fast = FastDivergenceChannel(baseline, window=25, threshold=threshold)
        alarmed = False
        for i, rec in enumerate(stream):
            s_slow, s_fast = slow.update(rec), fast.update(rec)
            if s_slow is None:
                self.assertIsNone(s_fast)
            else:
                self.assertTrue(
                    math.isclose(s_slow, s_fast, rel_tol=1e-9, abs_tol=1e-12),
                    f"event {i}: {s_slow} != {s_fast}")
            self.assertEqual(slow.alarmed, fast.alarmed, f"event {i}")
            alarmed = alarmed or fast.alarmed
        self.assertEqual(alarmed, expect_alarm)

    def test_in_control_stream(self):
        rng = random.Random(11)
        baseline, weights = self._baseline(rng)
        stream = [_rec("s", k, rng.choices(self.VOCAB, weights)[0])
                  for k in range(1500)]
        self._assert_equivalent(baseline, stream, threshold=0.97,
                                expect_alarm=False)

    def test_drifting_stream_with_unseen_tokens(self):
        rng = random.Random(12)
        baseline, weights = self._baseline(rng)
        drifted = [f"u{i}" for i in range(30)] + self.VOCAB[250:]
        stream = [_rec("s", k, rng.choices(self.VOCAB, weights)[0])
                  for k in range(500)]
        stream += [_rec("s", 500 + k, rng.choice(drifted))
                   for k in range(1500)]
        self._assert_equivalent(baseline, stream, threshold=0.5,
                                expect_alarm=True)


def _stream_corpus(seed, n_injected=16):
    rng = random.Random(seed)
    vocab = [f"t{i:03d}" for i in range(120)]
    weights = [1.0 / (i + 1) for i in range(len(vocab))]
    shifted = [f"u{i}" for i in range(20)] + vocab[100:]
    runs, benign, injected = {}, [], []
    for i in range(48):
        rid = f"ben{i:02d}"
        benign.append(rid)
        runs[rid] = [_rec(rid, k, rng.choices(vocab, weights)[0])
                     for k in range(rng.randint(25, 35))]
    for i in range(n_injected):
        rid = f"inj{i:02d}"
        injected.append(rid)
        runs[rid] = [_rec(rid, k, rng.choice(shifted))
                     for k in range(rng.randint(25, 35))]
    return benign, injected, runs


class TestFastStreamTrial(unittest.TestCase):
    """fast_stream_trial vs. eval_agentdojo.stream_trial: identical verdicts
    (false_alarm / detected / delay) on a corpus small enough for the O(vocab)
    original."""

    def test_matches_original_trial(self):
        benign, injected, runs = _stream_corpus(21)
        for seed in range(5):
            slow = stream_trial(benign, injected, runs, random.Random(seed),
                                10, 1.2)
            fast = fast_stream_trial(benign, injected, runs,
                                     random.Random(seed), 10, 1.2)
            self.assertEqual(slow, fast, f"seed {seed}")

    def test_thin_corpus_returns_none(self):
        benign, injected, runs = _stream_corpus(22)
        thin = benign[:4]
        self.assertIsNone(fast_stream_trial(thin, injected, runs,
                                            random.Random(0), 50, 1.2))

    def test_with_thresholds_only_adds_keys(self):
        benign, injected, runs = _stream_corpus(23)
        plain = fast_stream_trial(benign, injected, runs, random.Random(1),
                                  10, 1.2)
        rich = fast_stream_trial(benign, injected, runs, random.Random(1),
                                 10, 1.2, with_thresholds=True)
        self.assertGreater(rich.pop("div_threshold"), 0.0)
        self.assertGreater(rich.pop("cusum_threshold"), 0.0)
        self.assertEqual(plain, rich)


class TestWindowSweep(unittest.TestCase):
    def test_sweep_rows_per_window(self):
        from unittest import mock

        from driftdetect import eval_l1_window_sweep as sweep

        benign, injected, runs = _stream_corpus(31, n_injected=32)
        labels = {rid: {"classification": "clean_baseline_label",
                        "n_calls": len(recs)}
                  for rid, recs in runs.items()}
        for rid in injected:
            labels[rid]["classification"] = "hacked_label"

        with mock.patch.object(sweep, "load_pipeline",
                               return_value=(runs, labels)), \
             mock.patch.object(sweep, "load_sidecar", return_value={}), \
             mock.patch.object(sweep, "token_runs",
                               side_effect=lambda r, s: r), \
             mock.patch.object(sweep, "CLEAN_CLASS", "clean_baseline_label"), \
             mock.patch.object(sweep, "HACKED_CLASS", "hacked_label"):
            rows = sweep.sweep_model("ld", "cd", "m", windows=(10, 20),
                                     trials=3, seed=7, margin=1.2)
        self.assertEqual([r["window"] for r in rows], [10, 20])
        for r in rows:
            self.assertEqual(r["cells"], 3)
            self.assertLessEqual(r["n_capped"], r["cells"])
            self.assertGreaterEqual(r["div_threshold_median"], 0.0)
            for key in ("false_alarm", "detected"):
                self.assertTrue(0.0 <= r[key] <= 1.0)


class TestFastPerrunTrial(unittest.TestCase):
    def _runs(self, seed):
        import random
        rng = random.Random(seed)
        tools = ["ls", "cat", "grep", "python3", "rm", "curl"]
        runs = {}
        for i in range(24):
            rid = f"run{i}"
            runs[rid] = [
                CallRecord(ts=float(k), run_id=rid, agent_id="a", model="",
                           model_version="", goal_id="g", step_index=k,
                           tool=rng.choice(tools), params_hash="0" * 12,
                           status="ok", duration_ms=0.0)
                for k in range(rng.randint(3, 9))
            ]
        return runs

    def test_bit_identical_to_original(self):
        import random
        runs = self._runs(3)
        benign = sorted(runs)[:16]
        hacked = sorted(runs)[16:]
        for seed in range(5):
            slow = perrun_trial(benign, hacked, runs,
                                random.Random(seed), 2.0)
            fast = fast_perrun_trial(benign, hacked, runs,
                                     random.Random(seed), 2.0)
            self.assertEqual(slow, fast)


if __name__ == "__main__":
    unittest.main()
