# Behavioral Drift Detection

Research on detecting behavioral drift in LLM-driven autonomous systems from
operational records — a survey paper and stdlib-only reference implementations
of the detectors it argues for.

## The paper

**Behavioral Drift in Autonomous LLM-driven Systems: A Survey of Detection
Approaches and the Case for Deterministic Detection** (v0.3, Eckel & Radehaus, KYDE)
— read it as
[Markdown](paper/behavioral-drift-detection-survey.md) or
[PDF](paper/behavioral-drift-detection-survey.pdf).
The PDF is rebuilt from the Markdown source with
[`paper/build-pdf.sh`](paper/build-pdf.sh) (pandoc + headless Chrome).

LLM-driven agents do not keep a fixed policy: given the same task weeks later,
they often take different actions. The literature calls this *behavioral
drift*, but the label is too coarse. The paper:

- **separates seven drift phenomena** (goal drift, context decay, reward
  hacking, deception, multi-agent drift, persistent drift, version drift) and
  maps them onto the EU AI Act's coarser legal taxonomy (Art. 3(23)
  "substantial modification", Art. 12 record-keeping, Art. 72 post-market
  monitoring), with prompt injection placed explicitly as a *cause* that
  produces three of the seven;
- **surveys eight recent detection approaches**, from composite stability
  metrics and a formal non-identifiability theorem to runtime governance
  frameworks and lightweight black-box detectors, and shows their reported
  numbers are not comparable: units differ, no work splits performance by
  drift type, and every evaluation rests on synthetic or LLM-labeled ground
  truth;
- **contributes a detectability matrix** (Table 2) crossing the seven
  phenomena with evidence, reported performance, and what boundary call
  records alone can establish — to our knowledge the first such breakdown;
- **argues the determinism requirement**: every surveyed hot-path detector is
  deterministic statistics, with LLMs confined to evaluation and diagnosis —
  and this separation must be a design rule, because an LLM judge is itself a
  drifting system (the judge regress), a disputed verdict must be recomputable
  from the record alone, and frozen, integrity-protected baselines are the
  answer to reference contamination.

The outlook covers filling the matrix with numbers measured on real multi-week
operational records, and per-agent task models — recurring tasks mined from
the record (process discovery), frozen and fingerprinted like baselines, for
run-scale instead of window-scale detection.

## The code

[`experiments/`](experiments/) — reference implementations of the paper's
Section 5 detector set, **Python standard library only**, so that every
verdict is reproducible by a third party from the record alone: same log,
same score.

- Two-regime distributional detector against a frozen, fingerprinted baseline:
  windowed Jensen–Shannon divergence + EMA for gradual drift, CUSUM on
  per-event surprisal for abrupt (injection-like) shifts.
- Per-type detectors from Table 2: context decay (error rate by run-length
  bin), version drift (record-field segmentation), omission (expected calls
  that stop appearing), and the four countable goal-persistence failure
  classes (duplicate submission, premature abort, false success, missing
  progress), plus a persistent-vs-transient classifier.
- A seeded synthetic test-set generator with known drift onsets, and an
  evaluation harness reporting detection rate, false-positive rate, and
  detection delay per drift type
  ([results](experiments/results/synthetic-validation.md) — synthetic
  validation only, by design never entered into the paper's Table 2).

```bash
cd experiments
python3 -m unittest discover -s tests -t .   # unit tests
python3 -m driftdetect.evaluate --trials 5   # validation table
```

## Status

v0.3, co-author reviewed. Venue selection and LaTeX conversion pending. The
empirical follow-up — measuring the detectors on real multi-week operational
records — is the immediate next step.

## License

[CC BY 4.0](LICENSE).
