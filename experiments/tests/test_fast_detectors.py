"""Unit tests for the O(1) incremental divergence channel."""

import math
import random
import unittest

from driftdetect.baseline import freeze_baseline
from driftdetect.detectors import DivergenceChannel
from driftdetect.fast_detectors import IncrementalDivergenceChannel
from driftdetect.records import CallRecord

VOCAB = [f"t{i:03d}" for i in range(300)]


def _rec(k, tool):
    return CallRecord(ts=float(k), run_id="s", agent_id="a", model="m",
                      model_version="1", goal_id="g", step_index=k,
                      tool=tool, params_hash="0" * 12, status="ok",
                      duration_ms=0.0)


def _baseline(rng):
    weights = [1.0 / (i + 1) for i in range(len(VOCAB))]
    records = [_rec(k, rng.choices(VOCAB, weights)[0]) for k in range(4000)]
    return freeze_baseline(records), weights


class TestIncrementalDivergenceChannel(unittest.TestCase):
    def _assert_equivalent(self, baseline, stream, threshold, expect_alarm,
                           resync):
        slow = DivergenceChannel(baseline, window=25, threshold=threshold)
        fast = IncrementalDivergenceChannel(baseline, window=25,
                                            threshold=threshold,
                                            resync=resync)
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

    def test_in_control_stream_across_resyncs(self):
        rng = random.Random(41)
        baseline, weights = _baseline(rng)
        stream = [_rec(k, rng.choices(VOCAB, weights)[0])
                  for k in range(1500)]
        # resync=7 crosses rebuild boundaries hundreds of times
        self._assert_equivalent(baseline, stream, threshold=0.97,
                                expect_alarm=False, resync=7)

    def test_drifting_stream_with_unseen_tokens(self):
        rng = random.Random(42)
        baseline, weights = _baseline(rng)
        drifted = [f"u{i}" for i in range(30)] + VOCAB[250:]
        stream = [_rec(k, rng.choices(VOCAB, weights)[0])
                  for k in range(500)]
        stream += [_rec(500 + k, rng.choice(drifted)) for k in range(1500)]
        self._assert_equivalent(baseline, stream, threshold=0.5,
                                expect_alarm=True, resync=7)

    def test_no_drift_without_resync(self):
        # With resync far beyond the stream length the sums never rebuild:
        # the accumulated float error alone must stay within tolerance.
        rng = random.Random(43)
        baseline, weights = _baseline(rng)
        stream = [_rec(k, rng.choices(VOCAB, weights)[0])
                  for k in range(1500)]
        self._assert_equivalent(baseline, stream, threshold=0.97,
                                expect_alarm=False, resync=10**9)


if __name__ == "__main__":
    unittest.main()
