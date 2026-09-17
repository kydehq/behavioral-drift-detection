# Drift detection experiments

Companion code to `../paper/behavioral-drift-detection-survey.md`. Implements the
detector set the survey argues for — deterministic statistics, reproducible from
boundary call records alone — plus a synthetic test-set builder and an
evaluation harness.

**Stdlib-only. No numpy, no model calls, no wall clock in any verdict.** This
makes the paper's reproducibility argument literal: a third party with the same
JSONL log and the same baseline fingerprint computes the same score.

## Layout

```
driftdetect/
  records.py     CallRecord schema + JSONL I/O (provisional until a
                 production ledger schema is finalized)
  baseline.py    FrozenBaseline: admission-time snapshot with a SHA-256
                 fingerprint, so every verdict names its exact reference
                 (anti reference-contamination, Fernandez 2026)
  detectors.py   The algorithm set:
                 - DivergenceChannel: windowed JSD + EMA vs frozen baseline
                   (creep regime, Section 5)
                 - CusumChannel: CUSUM on per-event surprisal (jump regime /
                   in-session injection, Sections 2.3 + 5)
                 - detect_context_decay: error/abort rate by run-length bin
                 - detect_version_drift: segmentation on model/version fields
                 - detect_omission: expected calls that stop appearing
                   (Arike et al.: omission beats commission)
                 - check_goal_persistence: 4 countable failure classes
                   (duplicate submission, premature abort, false success,
                   missing progress)
                 - classify_persistence: durable vs transient shift (type 6)
  testset.py     Seeded generator: baseline period + 8 scenarios with known
                 drift onsets (none / abrupt / gradual / transient /
                 context_decay / version / omission / failure_classes)
  evaluate.py    Harness: detection rate, FPR, median delay per drift type
  adapters/      Real corpora -> CallRecord ledgers, each with a labels
                 sidecar and a sha256 manifest (mapping decisions in the
                 module docstrings; nothing the source lacks is invented):
                 - agentdojo.py       AgentDojo runs (injection labels)
                 - swebench.py        SWE-bench submission trajectories
                 - terminalwrench.py  Terminal Wrench (reward-hack labels)
                 - trail.py           TRAIL OpenTelemetry traces (per-span
                                      status + human error annotations)
                 - trace.py           TRACE coding trajectories (reward-hack
                                      subcategory labels; reads the JSONL
                                      export of the gated Parquet)
                 - whowhen.py         Who&When multi-agent failure logs
                                      (delegation-seam records + human
                                      failure attribution)
  eval_agentdojo.py       injection experiments (per-run + stream onset)
  eval_swebench.py        version-drift + null-stream experiments
  eval_terminalwrench.py  reward-hacking experiments (same pair of
                          experiments as eval_agentdojo, no goal
                          conditioning — docstring explains)
  eval_trail.py           error-rate / context-decay validation (corpus
                          description + calibration check, not detection
                          rates — 148 traces; docstring explains)
  eval_trace.py           reward-hacking cross-corpus check on TRACE
                          (single deployment — the corpus names neither
                          model nor scaffold)
  eval_whowhen.py         seam observability on Who&When (all runs are
                          failures — no detection rates possible;
                          docstring explains)
tests/           Unit tests (python -m unittest)
```

## Run

```bash
cd experiments
python3 -m unittest discover -s tests -t .          # unit tests
python3 -m driftdetect.evaluate --trials 5          # synthetic validation table
python3 -m driftdetect.evaluate --out results/synthetic-validation.md
```

## Honesty rule

Numbers produced by `evaluate.py` are **synthetic validation**: they show the
detectors fire on what they claim to detect, with measurable delay and
false-positive behavior. They are **not** detection performance on real
operational records and must never be entered into Table 2 of the survey
(see `../TODO.md`). Table 2 fills only with numbers measured on real 
multi-week operational records.

## Next steps

1. Replace `records.py` with a finalized production ledger schema.
2. Add an adapter that reads real ledger exports into `CallRecord` streams.
3. Freeze a baseline on an admission-time window of real records; run the
   two-regime detector over subsequent weeks; report per-drift-type numbers.
4. Per-agent task models (paper §7 outlook): mine recurring tasks from the
   record (trace clustering / process discovery), learn per-task reference
   models out of band (call sequences, branching probabilities, duration
   envelopes), freeze + fingerprint them like baselines, and score single
   runs against them — run-scale instead of window-scale detection.
