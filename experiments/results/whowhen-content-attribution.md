# E4: failure attribution on Who&When, L3 seam content

One frozen prediction per run and predictor (module docstring);
predictors were developed on the ~20% dev split only, 'eval' is
the held-out measurement. step@1 = predicted record index equals
the annotated mistake_step; agent@1 = the predicted record's
speaker equals mistake_agent. All 184 runs are failures:
attribution accounting, never detection rates. E[random] is the
analytic step@1 of a uniform pick.

## algorithm-generated — eval split (110 runs, E[random] step@1 = 12.0%)

| predictor | class | step@1 | abs. dist <= 2 | agent@1 |
|---|---|---|---|---|
| first | baseline | 14.5% | 50.0% | 46.4% |
| third | baseline | 9.1% | 69.1% | 24.5% |
| middle | baseline | 12.7% | 60.0% | 30.0% |
| last | baseline | 0.9% | 18.2% | 37.3% |
| first_error | content | 11.8% | 68.2% | 24.5% |
| before_first_error | content | 30.9% | 65.5% | 55.5% |
| before_first_apology | content | 14.5% | 49.1% | 45.5% |
| first_worker | structure | 14.5% | 50.0% | 46.4% |
| second_worker | structure | 26.4% | 60.0% | 42.7% |

## algorithm-generated — dev split (16 runs, E[random] step@1 = 12.1%)

| predictor | class | step@1 | abs. dist <= 2 | agent@1 |
|---|---|---|---|---|
| first | baseline | 25.0% | 62.5% | 68.8% |
| third | baseline | 6.2% | 81.2% | 12.5% |
| middle | baseline | 6.2% | 37.5% | 31.2% |
| last | baseline | 0.0% | 18.8% | 25.0% |
| first_error | content | 25.0% | 68.8% | 37.5% |
| before_first_error | content | 43.8% | 75.0% | 62.5% |
| before_first_apology | content | 25.0% | 62.5% | 62.5% |
| first_worker | structure | 25.0% | 62.5% | 68.8% |
| second_worker | structure | 31.2% | 75.0% | 43.8% |

## hand-crafted — eval split (44 runs, E[random] step@1 = 4.8%)

| predictor | class | step@1 | abs. dist <= 2 | agent@1 |
|---|---|---|---|---|
| first | baseline | 0.0% | 2.3% | 0.0% |
| third | baseline | 0.0% | 22.7% | 34.1% |
| middle | baseline | 2.3% | 20.5% | 45.5% |
| last | baseline | 13.6% | 20.5% | 59.1% |
| first_error | content | 13.6% | 18.2% | 34.1% |
| before_first_error | content | 0.0% | 18.2% | 13.6% |
| before_first_apology | content | 0.0% | 2.3% | 11.4% |
| first_worker | structure | 18.2% | 29.5% | 59.1% |
| second_worker | structure | 15.9% | 27.3% | 59.1% |

## hand-crafted — dev split (14 runs, E[random] step@1 = 2.2%)

| predictor | class | step@1 | abs. dist <= 2 | agent@1 |
|---|---|---|---|---|
| first | baseline | 0.0% | 0.0% | 0.0% |
| third | baseline | 0.0% | 14.3% | 21.4% |
| middle | baseline | 7.1% | 14.3% | 21.4% |
| last | baseline | 7.1% | 7.1% | 64.3% |
| first_error | content | 7.1% | 7.1% | 35.7% |
| before_first_error | content | 0.0% | 7.1% | 0.0% |
| before_first_apology | content | 0.0% | 0.0% | 0.0% |
| first_worker | structure | 21.4% | 21.4% | 57.1% |
| second_worker | structure | 28.6% | 35.7% | 50.0% |
