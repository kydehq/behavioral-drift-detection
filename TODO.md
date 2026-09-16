# TODO before publication

- [x] Co-author review of the full draft (language rules, claims check). Signed off by Joerg, 2026-09-09 (covers the v0.3 rework: re-voiced text, in-paper taxonomy derivation, Disclosure).
- [ ] Decide the venue: arXiv preprint (speed, analyst reach) vs. workshop submission (peer review).
- [x] Complete the author list for the arXiv:2604.04604 citation (legal drift taxonomy). Nannini, Smith, Maggini, Panai, Feliciano, Tiulkanov, Maran, Gealy, Bisconti — verified against arXiv v1 (Apr 6, 2026); re-check the version right before submission, the authors flag it as a working paper.
- [x] Verify every citation against the source once more before submission (figures were extracted from paper texts in September 2026). NOW LOAD-BEARING: the Disclosure section asserts this verification happened — it must be completed before any submission. (Verified 2026-09-08: all citations, figures, author lists, and venues cross-checked against primary sources; references updated).
- [x] Decide whether Table 2 rows get per-row references in the final layout. (Done: explicit per-row citations added across all 7 rows of Table 2).
- [ ] Keep the empirical gap honest: all "detection rate reported?" cells say "none" by design. Fill only with our own measured numbers (follow-up work), never with estimates.
- [ ] Convert to the venue's format (LaTeX) once the venue is decided.



Hey everyone! Jürgen & Joerg here 👋
Quick intro: we're building Kyde (inline drift detection and guardrails for autonomous agents). We wanted to share a survey paper and open-source reference implementation we just put out:

🔗 Repo: https://github.com/kydehq/behavioral-drift-detection

The problem: Most agent drift evaluations rely on an LLM-as-a-judge. But an LLM judge is itself an unmeasured, drifting system that suffers from context decay, vendor swaps, and test-
awareness.

Our thesis: Runtime drift detection must be deterministic, reproducible, and sovereign—computable by a third party from JSONL call records alone (same log, same score, zero external API
calls).

The repo implements:
• A two-regime detector in pure standard-library Python (no NumPy, no external model calls): windowed JS-divergence for gradual creep + CUSUM change-point statistics for abrupt shifts / prompt injections.
• An accompanying survey paper structuring 7 distinct drift phenomena into a detectability matrix.

If you're building long-running agents or care about local, sovereign agent reliability, take a look at the repo! We'd love feedback, PRs, or to chat with anyone interested in running drift detection on their own agent workflows.
