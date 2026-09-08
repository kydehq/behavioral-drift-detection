# Synthetic validation of the drift detectors

Trials per drift type: 5 (seeds 7, +1000 each) — 200 runs per period, stdlib-only, fully deterministic.

> **These numbers validate the detectors on synthetic data with known
> drift onsets. They are NOT detection performance on real operational
> records and must never be entered into Table 2 of the survey.**

| Drift scenario | Responsible detector | Detected (rate) | Median delay (events) | Example detail |
|---|---|---|---|---|
| none | all (false-positive check) | FPR 0% | n/a | clean |
| abrupt | CUSUM change-point channel | 100% | 0 | channels fired: ['cusum', 'divergence'] |
| gradual | windowed JSD + EMA channel | 100% | 324 | channels fired: ['cusum', 'divergence'] |
| transient | persistence classifier (shift seen, not durable) | 100% | 20 | shifted=True persistent=False |
| context_decay | error rate by run-length bin | 100% | n/a | 3 bins flagged, worst bin 1 (0.01 -> 0.29, z=19.4) |
| version | version segmentation + JSD | 100% | 0 | JSD across version boundary: 0.613 |
| omission | expected-tool presence per goal | 100% | n/a | dropped: reconcile-invoice/compare (0% of runs), triage-ticket/classify (0% of runs) |
| failure_classes | per-run predicates (4 countable classes) | 100% | n/a | violations by kind: {'duplicate_submission': 5, 'false_success': 10, 'missing_progress': 5, 'premature_abort': 5} |
