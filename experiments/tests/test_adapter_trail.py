"""Unit tests for the TRAIL adapter, on a synthetic mini trace tree."""

import json
import os
import tempfile
import unittest

from driftdetect.adapters.trail import (
    convert_trace, convert_tree, duration_ms, flatten_spans, load_annotation,
)
from driftdetect.records import read_jsonl


def span(span_id, name, ts, status="Ok", duration="PT1S",
         children=(), attrs=None):
    return {"span_id": span_id, "span_name": name, "timestamp": ts,
            "status_code": status, "duration": duration,
            "span_attributes": attrs or {}, "child_spans": list(children)}


def trace_doc(trace_id="t1"):
    return {"trace_id": trace_id, "spans": [
        span("s0", "main", "2025-04-01T10:00:00+00:00", "Ok", "PT2M", [
            span("s1", "Step 1", "2025-04-01T10:00:01+00:00", "Unset",
                 "PT30S", [
                     span("s2", "LiteLLMModel.__call__",
                          "2025-04-01T10:00:02+00:00", "Ok", "PT1M2.5S",
                          attrs={"llm.model_name": "o3-mini"}),
                 ]),
            span("s3", "Step 2", "2025-04-01T10:00:40+00:00", "Error",
                 "PT5S", [
                     span("s4", "VisitTool", "2025-04-01T10:00:41+00:00",
                          "Error", "PT0.25S"),
                 ]),
        ]),
    ]}


def annotation_doc():
    return {
        "errors": [
            {"category": "Tool-related", "location": "s4",
             "evidence": "long text", "description": "d", "impact": "HIGH"},
            {"category": "Goal Deviation", "location": "does-not-exist",
             "evidence": "e", "description": "d", "impact": "LOW"},
        ],
        "scores": [{"reliability_score": 3, "overall": 2.5}],
    }


class TestConvertTrace(unittest.TestCase):
    def test_spans_become_ordered_records(self):
        recs, _ = convert_trace(trace_doc(), annotation_doc(), "gaia")
        self.assertEqual([r.meta["span_id"] for r in recs],
                         ["s0", "s1", "s2", "s3", "s4"])
        self.assertEqual([r.step_index for r in recs], [0, 1, 2, 3, 4])
        self.assertEqual([r.status for r in recs],
                         ["ok", "ok", "ok", "error", "error"])
        self.assertEqual({r.run_id for r in recs}, {"t1"})
        self.assertEqual({r.goal_id for r in recs}, {"t1"})
        self.assertEqual({r.agent_id for r in recs}, {"gaia"})
        self.assertEqual(recs[2].model, "o3-mini")
        self.assertEqual(recs[0].model, "")
        self.assertEqual(recs[2].duration_ms, 62500.0)
        self.assertTrue(all(a.ts <= b.ts for a, b in zip(recs, recs[1:])))

    def test_equal_timestamps_keep_depth_first_order(self):
        doc = {"trace_id": "t", "spans": [
            span("a", "main", "2025-04-01T10:00:00+00:00", children=[
                span("b", "Step 1", "2025-04-01T10:00:00+00:00"),
                span("c", "Step 2", "2025-04-01T10:00:00+00:00"),
            ]),
        ]}
        recs, _ = convert_trace(doc, None, "gaia")
        self.assertEqual([r.meta["span_id"] for r in recs], ["a", "b", "c"])

    def test_label_resolves_annotation_locations(self):
        _, label = convert_trace(trace_doc(), annotation_doc(), "gaia")
        self.assertEqual(label["n_errors_annotated"], 2)
        self.assertEqual(label["n_locations_resolved"], 1)
        self.assertEqual(label["n_annotated_on_error_status"], 1)
        self.assertEqual(label["n_error_status"], 2)
        self.assertEqual(label["scores"], {"reliability_score": 3,
                                           "overall": 2.5})
        # evidence/description are not copied into the sidecar
        self.assertEqual(set(label["errors"][0]),
                         {"category", "location", "impact"})

    def test_non_trace_document_is_rejected(self):
        with self.assertRaises(ValueError):
            flatten_spans({"foo": 1})
        with self.assertRaises(ValueError):
            convert_trace({"spans": [span("a", "x", None)]}, None, "gaia")


class TestDurationParsing(unittest.TestCase):
    def test_iso8601_durations(self):
        self.assertEqual(duration_ms("PT1M48.755S"), 108755.0)
        self.assertEqual(duration_ms("PT0.25S"), 250.0)
        self.assertEqual(duration_ms("P1DT1H"), 90_000_000.0)
        self.assertEqual(duration_ms("nope"), 0.0)
        self.assertEqual(duration_ms(None), 0.0)


class TestLoadAnnotation(unittest.TestCase):
    def test_trailing_comma_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.json")
            with open(p, "w") as fh:
                fh.write('{"errors": [{"category": "X", "location": "s1",'
                         ' "impact": "LOW"},\n]}')
            ann = load_annotation(p)
            self.assertEqual(len(ann["errors"]), 1)


class TestConvertTree(unittest.TestCase):
    def _write(self, base, dataset_dir, key, trace, ann):
        ddir = os.path.join(base, "data", dataset_dir)
        adir = os.path.join(base, f"processed_annotations_{key}")
        os.makedirs(ddir, exist_ok=True)
        os.makedirs(adir, exist_ok=True)
        tid = trace["trace_id"]
        with open(os.path.join(ddir, f"{tid}.json"), "w") as fh:
            json.dump(trace, fh)
        if ann is not None:
            with open(os.path.join(adir, f"{tid}.json"), "w") as fh:
                json.dump(ann, fh)

    def test_tree_conversion_writes_ledger_labels_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = os.path.join(tmp, "benchmarking")
            self._write(bench, "GAIA", "gaia", trace_doc("t1"),
                        annotation_doc())
            self._write(bench, "SWE Bench", "swe_bench", trace_doc("t2"),
                        None)

            out = os.path.join(tmp, "out")
            manifest = convert_tree(bench, out)

            self.assertEqual(manifest["n_runs_total"], 2)
            self.assertEqual(manifest["n_records_total"], 10)
            self.assertEqual(set(manifest["datasets"]),
                             {"gaia", "swe_bench"})
            recs = list(read_jsonl(os.path.join(out, "gaia.jsonl")))
            self.assertEqual(len(recs), 5)
            self.assertEqual({r.run_id for r in recs}, {"t1"})
            with open(os.path.join(out, "gaia.labels.json")) as fh:
                labels = json.load(fh)
            self.assertEqual(labels["t1"]["n_locations_resolved"], 1)
            entry = manifest["datasets"]["gaia"]
            self.assertEqual(len(entry["sha256_ledger"]), 64)

    def test_malformed_trace_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = os.path.join(tmp, "benchmarking")
            self._write(bench, "GAIA", "gaia", trace_doc("t1"),
                        annotation_doc())
            ddir = os.path.join(bench, "data", "GAIA")
            with open(os.path.join(ddir, "broken.json"), "w") as fh:
                fh.write("not json")

            manifest = convert_tree(bench, os.path.join(tmp, "out"))
            self.assertEqual(manifest["n_runs_total"], 1)
            self.assertEqual(manifest["n_skipped"], 1)

    def test_conversion_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = os.path.join(tmp, "benchmarking")
            self._write(bench, "GAIA", "gaia", trace_doc("t1"),
                        annotation_doc())
            m1 = convert_tree(bench, os.path.join(tmp, "out1"))
            m2 = convert_tree(bench, os.path.join(tmp, "out2"))
            self.assertEqual(m1["datasets"]["gaia"]["sha256_ledger"],
                             m2["datasets"]["gaia"]["sha256_ledger"])


if __name__ == "__main__":
    unittest.main()
