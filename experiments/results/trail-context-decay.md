# Error-rate / context-decay validation on TRAIL records

Split-half calibration: 10 trials, seed base 7,
z-threshold 3.0, min 30 calls per bin. Real
records; corpus description + calibration check, not detection
rates (module docstring). One record per OpenTelemetry span.

## Overview and signal coverage

share on-status = annotated errors whose span also carries
status_code Error — the fraction of human-judged error mass the
runtime status signal sees at all.

| dataset | runs | records | status errors | annotated errors (resolved) | on-status | share on-status | models |
|---|---|---|---|---|---|---|---|
| gaia | 117 | 3579 | 367 (10.3%) | 585 (585) | 34 | 5.8% | o3-mini |
| swe_bench | 31 | 1047 | 70 (6.7%) | 256 (254) | 14 | 5.5% | anthropic/claude-3-7-sonnet-latest |

## Length profile — gaia

| steps in run | calls | status-error rate | annotated errors | annotated per call |
|---|---|---|---|---|
| 0–9 | 1170 | 2.1% | 189 | 0.162 |
| 10–19 | 663 | 7.1% | 152 | 0.229 |
| 20–29 | 409 | 16.4% | 62 | 0.152 |
| 30–39 | 321 | 25.5% | 80 | 0.249 |
| 40–49 | 237 | 21.9% | 32 | 0.135 |
| 50–59 | 184 | 15.2% | 27 | 0.147 |
| 60–69 | 143 | 11.2% | 13 | 0.091 |
| 70–79 | 101 | 2.0% | 2 | 0.020 |
| 80–89 | 69 | 18.8% | 11 | 0.159 |
| 90–99 | 47 | 10.6% | 4 | 0.085 |
| 100–109 | 40 | 5.0% | 3 | 0.075 |
| 110–119 | 40 | 5.0% | 1 | 0.025 |
| 120–129 | 40 | 17.5% | 4 | 0.100 |
| 130–139 | 37 | 27.0% | 2 | 0.054 |
| 140–149 | 30 | 16.7% | 3 | 0.100 |

## Length profile — swe_bench

| steps in run | calls | status-error rate | annotated errors | annotated per call |
|---|---|---|---|---|
| 0–9 | 310 | 7.7% | 60 | 0.194 |
| 10–19 | 294 | 6.8% | 89 | 0.303 |
| 20–29 | 216 | 2.8% | 52 | 0.241 |
| 30–39 | 129 | 7.8% | 31 | 0.240 |
| 40–49 | 78 | 11.5% | 11 | 0.141 |

## Split-half calibration (stationary — every flag is false)

| dataset | trials | trials with flags | flagged bins total |
|---|---|---|---|
| gaia | 10 | 1 | 1 |
| swe_bench | 10 | 0 | 0 |
