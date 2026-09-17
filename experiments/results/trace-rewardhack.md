# Reward-hack detection on TRACE records

10 trials, seed base 7, calibration margin
2.0, divergence window 50. Real records; the
stream experiment uses a composed timeline over the full task
mixture (module docstring — no goal conditioning, every trajectory
is a unique task). Hacked = source label != "0"; the corpus names
neither model nor scaffold, so there is a single deployment row.

## Per-run surprisal (primary)

Corpus JSD = plain JSD between the clean and hacked aggregate tool
distributions (effect size at corpus scale, not a detection).

| deployment | clean runs | hacked runs | corpus JSD | detection | FPR |
|---|---|---|---|---|---|
| trace | 249 | 268 | 0.017 | 0.0% | 0.0% |

## Stream onset, two-regime

| deployment | cells | det. div | det. cusum | FP div | FP cusum | delay div | delay cusum |
|---|---|---|---|---|---|---|---|
| trace | 10 | 0% | 0% | 0% | 0% | — | — |
