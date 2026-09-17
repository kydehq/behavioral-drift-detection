# Reward-hack detection on Terminal Wrench records

10 trials per model, seed base 7, calibration
margin 1.2, divergence window 50. Real records;
the stream experiment uses a composed timeline over the full task
mixture (module docstring — no goal conditioning, the corpus is too
thin per task). Hacked = rewarded_serious_exploit, clean = baseline.

## Per-run surprisal (primary)

Corpus JSD = plain JSD between the clean and hacked aggregate tool
distributions (effect size at corpus scale, not a detection).

| model | clean runs | hacked runs | corpus JSD | detection | FPR |
|---|---|---|---|---|---|
| claude-opus-4.6 | 614 | 730 | 0.118 | 0.0% | 0.0% |
| gemini-3.1-pro | 984 | 1469 | 0.090 | 0.0% | 0.0% |
| gpt-5.4 | 754 | 967 | 0.123 | 0.0% | 0.1% |

## Stream onset, two-regime

| model | cells | det. div | det. cusum | FP div | FP cusum | delay div | delay cusum |
|---|---|---|---|---|---|---|---|
| claude-opus-4.6 | 10 | 0% | 30% | 0% | 30% | — | 857 |
| gemini-3.1-pro | 10 | 0% | 10% | 0% | 40% | — | 2851 |
| gpt-5.4 | 10 | 0% | 0% | 0% | 60% | — | — |
