"""Unit tests: each detector fires on its scenario and stays quiet on null data.

Run with:  python -m unittest discover -s experiments/tests -t experiments
"""

import unittest

from driftdetect.baseline import freeze_baseline
from driftdetect.detectors import (
    GoalSpec,
    check_goal_persistence,
    classify_persistence,
    detect_context_decay,
    detect_omission,
    detect_version_drift,
    js_divergence,
    run_two_regime,
)
from driftdetect.testset import Generator, TERMINAL_TOOLS

N_RUNS = 120
SPECS = {
    goal: GoalSpec(goal_id=goal, terminal_tool=t, min_steps=3, max_steps=200)
    for goal, t in TERMINAL_TOOLS.items()
}


def make(drift_type: str, seed: int = 7):
    gen = Generator(seed=seed)
    baseline = freeze_baseline(gen.baseline_period(N_RUNS))
    scenario = gen.scenario(drift_type, N_RUNS)
    return baseline, scenario


class TestDivergencePrimitives(unittest.TestCase):
    def test_jsd_bounds_and_symmetry(self):
        p = {"a": 0.5, "b": 0.5}
        q = {"c": 1.0}
        self.assertAlmostEqual(js_divergence(p, p), 0.0, places=6)
        self.assertAlmostEqual(js_divergence(p, q), 1.0, places=3)  # disjoint support
        self.assertAlmostEqual(js_divergence(p, q), js_divergence(q, p), places=9)


class TestTwoRegime(unittest.TestCase):
    def test_cusum_fires_fast_on_abrupt_shift(self):
        baseline, sc = make("abrupt")
        alarms = {a.channel: a for a in run_two_regime(sc.records, baseline)}
        self.assertIn("cusum", alarms)
        delay = alarms["cusum"].event_index - sc.onset_index
        self.assertLess(delay, 50, "change-point channel should catch a jump quickly")

    def test_divergence_fires_on_gradual_shift(self):
        baseline, sc = make("gradual")
        alarms = {a.channel: a for a in run_two_regime(sc.records, baseline)}
        self.assertIn("divergence", alarms)
        self.assertGreater(alarms["divergence"].event_index, sc.onset_index)

    def test_quiet_on_null(self):
        baseline, sc = make("none")
        self.assertEqual(run_two_regime(sc.records, baseline), [])


class TestPersistence(unittest.TestCase):
    def test_durable_shift_is_persistent(self):
        baseline, sc = make("abrupt")
        v = classify_persistence(sc.records, baseline)
        self.assertTrue(v.shifted and v.persistent)

    def test_transient_shift_recovers(self):
        baseline, sc = make("transient")
        v = classify_persistence(sc.records, baseline)
        self.assertTrue(v.shifted)
        self.assertFalse(v.persistent)


class TestBatchDetectors(unittest.TestCase):
    def test_context_decay_flags_long_bins(self):
        baseline, sc = make("context_decay")
        findings = detect_context_decay(sc.records[sc.onset_index:], baseline)
        self.assertTrue(findings)
        worst = max(findings, key=lambda f: f.z)
        self.assertGreater(worst.observed_rate, worst.baseline_rate)

    def test_version_shift_found_at_boundary(self):
        _, sc = make("version")
        shifts = detect_version_drift(sc.records)
        hit = [s for s in shifts if s.to_version[1] == "2.0"]
        self.assertTrue(hit)
        self.assertGreaterEqual(hit[0].jsd, 0.05)

    def test_omission_detects_dropped_expected_tools(self):
        baseline, sc = make("omission")
        findings = detect_omission(sc.records[sc.onset_index:], baseline)
        dropped = {f.tool for f in findings}
        self.assertTrue({"classify", "compare"} & dropped)

    def test_no_batch_findings_on_null(self):
        baseline, sc = make("none")
        post = sc.records[len(sc.records) // 2:]
        self.assertEqual(detect_context_decay(post, baseline), [])
        self.assertEqual(detect_version_drift(sc.records), [])
        self.assertEqual(detect_omission(post, baseline), [])


class TestFailureClasses(unittest.TestCase):
    def test_all_four_classes_detected_and_null_is_clean(self):
        _, sc = make("failure_classes")
        kinds = {v.kind for v in check_goal_persistence(sc.records, SPECS)}
        self.assertEqual(kinds, {
            "duplicate_submission", "premature_abort",
            "false_success", "missing_progress",
        })

        _, null_sc = make("none")
        self.assertEqual(check_goal_persistence(null_sc.records, SPECS), [])


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_records_same_verdict(self):
        b1, s1 = make("abrupt", seed=42)
        b2, s2 = make("abrupt", seed=42)
        self.assertEqual(b1.fingerprint(), b2.fingerprint())
        a1 = run_two_regime(s1.records, b1)
        a2 = run_two_regime(s2.records, b2)
        self.assertEqual([(a.channel, a.event_index) for a in a1],
                         [(a.channel, a.event_index) for a in a2])


if __name__ == "__main__":
    unittest.main()
