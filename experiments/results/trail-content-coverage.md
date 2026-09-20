# E3: content access vs TRAIL's annotated error mass

Frozen signature families (6), developed on the
~20% dev split only; 'eval' is the held-out measurement. own =
signatures on the annotated span's stored outputs; window adds
3 downstream spans; L1 delta = new execution-error content
in the next prompt (module docstring). on-status is the L0
baseline restricted to the same locations. Negative rates are the
same predicates on non-annotated spans — the noise floor. 148
runs: coverage accounting, not detection rates.

## Per-location coverage of the annotated error mass

| dataset | split | locations | on-status (L0) | own outputs | window 3 | L1 delta | neg own | neg window 3 | neg L1 delta |
|---|---|---|---|---|---|---|---|---|---|
| gaia | eval | 453 | 6.4% | 6.0% | 12.8% | 31.6% | 5.9% | 17.0% | 13.4% |
| gaia | dev | 132 | 3.8% | 4.5% | 12.1% | 24.2% | 5.2% | 14.3% | 7.8% |
| swe_bench | eval | 201 | 5.5% | 16.9% | 36.3% | 11.9% | 13.3% | 34.8% | 10.0% |
| swe_bench | dev | 53 | 5.7% | 17.0% | 20.8% | 3.8% | 9.4% | 23.5% | 9.0% |

## Per-category coverage (eval split)

| dataset | category | locations | own | window 3 | L1 delta |
|---|---|---|---|---|---|
| gaia | formatting error | 99 | 6% | 14% | 66% |
| gaia | instruction non-compliance | 50 | 0% | 4% | 4% |
| gaia | goal deviation | 46 | 4% | 7% | 17% |
| gaia | tool-related | 37 | 3% | 11% | 49% |
| gaia | resource abuse | 34 | 3% | 15% | 38% |
| gaia | task orchestration | 33 | 3% | 3% | 9% |
| gaia | tool selection error | 32 | 0% | 6% | 9% |
| gaia | language-only | 30 | 7% | 7% | 10% |
| gaia | poor information retrieval | 22 | 5% | 14% | 23% |
| gaia | context handling failure | 15 | 0% | 13% | 47% |
| gaia | incorrect problem identification | 14 | 21% | 43% | 29% |
| gaia | tool output misinterpretation | 12 | 8% | 17% | 33% |
| gaia | environment setup error | 9 | 22% | 56% | 56% |
| gaia | resource not found | 7 | 86% | 86% | 0% |
| gaia | authentication error | 4 | 25% | 25% | 25% |
| gaia | tool definition issue | 2 | 0% | 0% | 50% |
| gaia | timeout issue | 2 | 0% | 0% | 0% |
| gaia | resource exhaustion | 2 | 0% | 0% | 0% |
| gaia | service error | 1 | 0% | 0% | 100% |
| gaia | tool selection | 1 | 0% | 0% | 0% |
| gaia | task orchestration error | 1 | 0% | 0% | 0% |
| swe_bench | instruction non-compliance | 64 | 28% | 56% | 5% |
| swe_bench | formatting error | 57 | 9% | 28% | 18% |
| swe_bench | context handling failure | 18 | 0% | 6% | 0% |
| swe_bench | resource abuse | 14 | 14% | 36% | 21% |
| swe_bench | poor information retrieval | 13 | 8% | 38% | 0% |
| swe_bench | language-only | 11 | 36% | 36% | 0% |
| swe_bench | incorrect problem identification | 8 | 38% | 38% | 12% |
| swe_bench | tool-related | 6 | 0% | 17% | 83% |
| swe_bench | task orchestration | 3 | 0% | 0% | 67% |
| swe_bench | incorrect memory usage | 2 | 50% | 100% | 0% |
| swe_bench | resource exhaustion | 1 | 0% | 0% | 0% |
| swe_bench | tool output misinterpretation | 1 | 0% | 0% | 0% |
| swe_bench | task orchestration error | 1 | 0% | 0% | 0% |
| swe_bench | goal deviation | 1 | 0% | 0% | 0% |
| swe_bench | instruction non complience | 1 | 0% | 0% | 0% |

## True-context-length profile — gaia (whole corpus, LLM calls)

| prompt tokens | calls | annotated per call |
|---|---|---|
| 0–2,000 | 398 | 0.123 |
| 2,000–4,000 | 249 | 0.329 |
| 4,000–8,000 | 372 | 0.274 |
| 8,000–16,000 | 389 | 0.229 |
| 16,000–32,000 | 99 | 0.101 |

| steps in run | calls | annotated per call | median prompt tokens |
|---|---|---|---|
| 0–9 | 351 | 0.265 | 1,281 |
| 10–19 | 367 | 0.243 | 3,310 |
| 20–29 | 178 | 0.197 | 6,405 |
| 30–39 | 161 | 0.329 | 9,050 |
| 40–49 | 84 | 0.226 | 10,564 |
| 50–59 | 95 | 0.137 | 12,085 |
| 60–69 | 70 | 0.100 | 14,591 |
| 70–79 | 43 | 0.023 | 7,278 |
| 80–89 | 32 | 0.250 | 7,439 |
| 100–109 | 20 | 0.100 | 9,805 |

## True-context-length profile — swe_bench (whole corpus, LLM calls)

| prompt tokens | calls | annotated per call |
|---|---|---|
| 2,000–4,000 | 18 | 0.056 |
| 4,000–8,000 | 121 | 0.430 |
| 8,000–16,000 | 108 | 0.407 |
| 16,000–32,000 | 108 | 0.361 |
| 32,000–64,000 | 96 | 0.281 |
| 64,000–128,000 | 10 | 0.300 |

| steps in run | calls | annotated per call | median prompt tokens |
|---|---|---|---|
| 0–9 | 95 | 0.400 | 4,766 |
| 10–19 | 145 | 0.441 | 9,234 |
| 20–29 | 108 | 0.324 | 17,695 |
| 30–39 | 64 | 0.359 | 26,061 |
| 40–49 | 39 | 0.154 | 35,254 |
