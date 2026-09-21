"""Unit tests for the SWE-chat real-timeline evaluation (E5)."""

import unittest

from driftdetect.eval_swechat import (
    concat,
    experiment_fingerprint,
    experiment_null,
    experiment_version,
    longest_single_version_block,
    n_records,
    split_at_fractions,
    version_blocks,
)
from driftdetect.records import CallRecord


def session(run_id, user, tools, version="1.0", t0=0.0, model="m"):
    return [
        CallRecord(
            ts=t0 + i, run_id=run_id, agent_id=user, model=model,
            model_version=version, goal_id="repo", step_index=i, tool=tool,
            params_hash="p", status="ok", duration_ms=0.0,
        )
        for i, tool in enumerate(tools)
    ]


def steady_sessions(user, n_sessions, session_len=40, version="1.0",
                    tools=("Read", "Edit", "git", "Grep"), t0=0.0):
    out = []
    for s in range(n_sessions):
        seq = [tools[(s + i) % len(tools)] for i in range(session_len)]
        out.append(session(f"{user}-s{s:03d}", user, seq, version=version,
                           t0=t0 + s * 1000.0))
    return out


class TestTimelineHelpers(unittest.TestCase):
    def test_version_blocks_are_contiguous(self):
        tl = (steady_sessions("u", 2, version="1.0")
              + steady_sessions("u", 3, version="1.1", t0=10_000)
              + steady_sessions("u", 1, version="1.0", t0=20_000))
        blocks = version_blocks(tl)
        self.assertEqual([(v, len(b)) for v, b in blocks],
                         [("1.0", 2), ("1.1", 3), ("1.0", 1)])

    def test_longest_block_respects_minimum(self):
        tl = (steady_sessions("u", 2, version="1.0")
              + steady_sessions("u", 5, version="1.1", t0=10_000))
        block = longest_single_version_block(tl, min_records_=100)
        self.assertEqual(block[0][0].model_version, "1.1")
        self.assertIsNone(longest_single_version_block(tl, min_records_=10_000))

    def test_unknown_version_blocks_are_not_null_material(self):
        tl = (steady_sessions("u", 3, version="1.0")
              + steady_sessions("u", 8, version="", t0=10_000))
        block = longest_single_version_block(tl, min_records_=100)
        self.assertEqual(block[0][0].model_version, "1.0")

    def test_split_at_fractions_keeps_sessions_whole(self):
        tl = steady_sessions("u", 8)
        parts = split_at_fractions(tl, (0.5, 0.75))
        self.assertEqual(sum(len(p) for p in parts), 8)
        self.assertEqual(n_records(tl),
                         sum(n_records(p) for p in parts))
        self.assertTrue(all(parts))
        # not enough boundaries for two cuts
        self.assertIsNone(split_at_fractions(steady_sessions("u", 2), (0.5, 0.75)))


class TestNullExperiment(unittest.TestCase):
    def test_stationary_user_produces_cell_without_alarm(self):
        timelines = {"u1": steady_sessions("u1", 12)}
        rows = experiment_null(timelines, window=20, margin=2.0, trials=3,
                               seed=7, min_records_=200, horizon_cap=500)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # a perfectly cyclic vocabulary should alarm in neither arm
        self.assertFalse(row["real_fp"]["divergence"])
        self.assertFalse(row["real_fp"]["cusum"])
        self.assertEqual(row["composed_fp"]["divergence"], 0.0)
        self.assertEqual(row["composed_cells"], 3)

    def test_too_small_users_are_skipped(self):
        timelines = {"u1": steady_sessions("u1", 2)}
        rows = experiment_null(timelines, window=20, margin=2.0, trials=2,
                               seed=7, min_records_=200, horizon_cap=500)
        self.assertEqual(rows, [])


class TestVersionExperiment(unittest.TestCase):
    def test_real_boundary_with_vocabulary_change_is_detected(self):
        old = steady_sessions("u1", 10, version="1.0")
        new = steady_sessions("u1", 6, version="2.0", t0=100_000,
                              tools=("Fetch", "Deploy", "Fetch", "Deploy"))
        timelines = {"u1": old + new}
        real, control = experiment_version(
            timelines, window=20, margin=2.0,
            min_admission=200, min_new=100, horizon_cap=500)
        self.assertEqual(len(real), 1)
        self.assertEqual((real[0]["old"], real[0]["new"]), ("1.0", "2.0"))
        self.assertGreater(real[0]["jsd"], 0.5)
        self.assertTrue(real[0]["detected"]["divergence"]
                        or real[0]["detected"]["cusum"])
        # the old block is also a control block (fake boundary, no change)
        self.assertEqual(len(control), 1)
        self.assertFalse(control[0]["detected"]["divergence"])

    def test_unknown_version_yields_no_boundary_and_no_control(self):
        old = steady_sessions("u1", 10, version="")
        new = steady_sessions("u1", 6, version="2.0", t0=100_000,
                              tools=("Fetch", "Deploy", "Fetch", "Deploy"))
        timelines = {"u1": old + new}
        real, control = experiment_version(
            timelines, window=20, margin=2.0,
            min_admission=200, min_new=100, horizon_cap=500)
        self.assertEqual(real, [])       # "" -> 2.0 is not a verified change
        self.assertEqual(control, [])    # the "" block cannot be a control

    def test_identical_behavior_across_boundary_is_not_detected(self):
        old = steady_sessions("u1", 10, version="1.0")
        new = steady_sessions("u1", 6, version="2.0", t0=100_000)
        timelines = {"u1": old + new}
        real, _ = experiment_version(
            timelines, window=20, margin=2.0,
            min_admission=200, min_new=100, horizon_cap=500)
        self.assertEqual(len(real), 1)
        self.assertLess(real[0]["jsd"], 0.01)
        self.assertFalse(real[0]["detected"]["divergence"])
        self.assertFalse(real[0]["detected"]["cusum"])


class TestFingerprint(unittest.TestCase):
    def test_within_smaller_than_between_for_distinct_users(self):
        timelines = {
            "u1": steady_sessions("u1", 10, tools=("Read", "Edit", "git", "Grep")),
            "u2": steady_sessions("u2", 10, tools=("Fetch", "Deploy", "kubectl", "helm")),
        }
        fp = experiment_fingerprint(timelines, block_size=100)
        self.assertEqual(fp["within_adjacent"]["n"], 2)
        self.assertEqual(fp["between_users"]["n"], 1)
        self.assertLess(fp["within_adjacent"]["median"],
                        fp["between_users"]["median"])
        self.assertIn(1, fp["aging"])
        # lag between block medians: sessions are 1000 s apart
        self.assertGreater(fp["aging"][1]["median_lag_days"], 0.0)

    def test_concat_preserves_order(self):
        tl = steady_sessions("u", 3, session_len=5)
        recs = concat(tl)
        self.assertEqual(len(recs), 15)
        self.assertEqual(recs[0].run_id, "u-s000")
        self.assertEqual(recs[-1].run_id, "u-s002")


if __name__ == "__main__":
    unittest.main()
