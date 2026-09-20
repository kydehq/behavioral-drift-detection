# E2: injection detection on AgentDojo, L2 content features

Frozen content features (6 regexes over inbound
tool-result texts), flag at >= 1 distinct match(es)
per run; deterministic, no trials. Features were developed on the
~20% dev split only (same sha256(run_id) % 5 protocol as the
Terminal Wrench experiments); 'eval' is the held-out measurement.
Detection over all attacked runs; 'success' restricts to the
L0-comparable successful-injection runs; 'reached' restricts to
attacked runs whose ground-truth injected string appears in some
tool result (evaluation denominator only, module docstring).

## Per-run verdicts (eval split)

| pipeline | benign | attacked | det. attacked | det. success | det. reached | FPR |
|---|---|---|---|---|---|---|
| Meta-SecAlign-70B | 109 | 2310 | 89.3% | 100.0% (36) | 92.3% (2069) | 6.4% |
| Meta-SecAlign-70B-repeat_user_prompt | 107 | 2272 | 88.9% | 100.0% (43) | 91.6% (2050) | 7.5% |
| claude-3-5-sonnet-20240620 | 84 | 484 | 91.5% | 100.0% (170) | 100.0% (310) | 3.6% |
| claude-3-5-sonnet-20241022 | 92 | 480 | 91.5% | 100.0% (5) | 100.0% (316) | 2.2% |
| claude-3-7-sonnet-20250219 | 109 | 765 | 98.0% | 100.0% (40) | 100.0% (606) | 7.3% |
| claude-3-haiku-20240307 | 86 | 409 | 84.4% | 93.9% (33) | 100.0% (231) | 7.0% |
| claude-3-opus-20240229 | 92 | 321 | 94.1% | 98.0% (51) | 100.0% (182) | 4.3% |
| claude-3-sonnet-20240229 | 78 | 419 | 92.4% | 100.0% (135) | 100.0% (256) | 3.8% |
| claude-3-sonnet-20240229-repeat_user_prompt | 27 | 0 | — | — (0) | — (0) | 3.7% |
| command-r | 93 | 498 | 74.5% | 93.8% (16) | 100.0% (280) | 2.2% |
| command-r-plus | 99 | 501 | 81.2% | 100.0% (5) | 100.0% (283) | 4.0% |
| gemini-1.5-flash-001 | 92 | 449 | 84.0% | 100.0% (64) | 100.0% (276) | 2.2% |
| gemini-1.5-flash-002 | 68 | 373 | 87.9% | 100.0% (20) | 100.0% (229) | 2.9% |
| gemini-1.5-pro-001 | 79 | 426 | 85.2% | 95.7% (139) | 100.0% (244) | 5.1% |
| gemini-1.5-pro-002 | 89 | 490 | 88.2% | 100.0% (91) | 100.0% (323) | 6.7% |
| gemini-2.0-flash-001 | 70 | 475 | 88.8% | 100.0% (112) | 100.0% (357) | 4.3% |
| gemini-2.0-flash-exp | 75 | 364 | 88.7% | 100.0% (92) | 100.0% (238) | 2.7% |
| gpt-3.5-turbo-0125 | 107 | 493 | 77.3% | 98.1% (53) | 100.0% (284) | 5.6% |
| gpt-4-0125-preview | 94 | 504 | 91.5% | 100.0% (282) | 100.0% (345) | 2.1% |
| gpt-4-turbo-2024-04-09 | 92 | 491 | 88.6% | 99.3% (148) | 100.0% (313) | 3.3% |
| gpt-4o-2024-05-13 | 101 | 5436 | 88.2% | 97.9% (1590) | 95.7% (3991) | 3.0% |
| gpt-4o-2024-05-13-repeat_user_prompt | 99 | 499 | 94.6% | 100.0% (150) | 100.0% (348) | 4.0% |
| gpt-4o-2024-05-13-spotlighting_with_delimiting | 105 | 510 | 92.5% | 100.0% (207) | 100.0% (337) | 1.9% |
| gpt-4o-2024-05-13-tool_filter | 93 | 491 | 87.6% | 100.0% (33) | 100.0% (295) | 5.4% |
| gpt-4o-2024-05-13-transformers_pi_detector | 93 | 484 | 26.2% | 100.0% (42) | 100.0% (118) | 3.2% |
| gpt-4o-mini-2024-07-18 | 97 | 496 | 90.5% | 98.6% (146) | 100.0% (318) | 8.2% |
| meta-llama_Llama-3-70b-chat-hf | 88 | 483 | 67.5% | 100.0% (130) | 100.0% (280) | 3.4% |
| meta-llama_Llama-3.3-70B-Instruct | 93 | 1833 | 84.6% | 97.9% (290) | 90.5% (1574) | 5.4% |
| meta-llama_Llama-3.3-70B-Instruct-repeat_user_prompt | 91 | 1678 | 83.0% | 98.2% (111) | 91.9% (1414) | 5.5% |

## Dev vs eval (overfitting check, aggregated)

| split | benign | attacked | det. attacked | det. success | FPR |
|---|---|---|---|---|---|
| eval | 2602 | 24434 | 86.2% | 98.7% | 4.5% |
| dev | 639 | 5932 | 85.9% | 98.9% | 3.8% |

## Per-attack-type detection (eval split, all pipelines)

| attack type | flagged / attacked | detection |
|---|---|---|
| captcha_dos | 69/77 | 89.6% |
| direct | 2305/3233 | 71.3% |
| dos | 69/76 | 90.8% |
| felony_dos | 74/80 | 92.5% |
| ignore_previous | 2999/3237 | 92.6% |
| important_instructions | 12188/14043 | 86.8% |
| important_instructions_no_model_name | 456/500 | 91.2% |
| important_instructions_no_names | 451/496 | 90.9% |
| important_instructions_no_user_name | 460/508 | 90.6% |
| important_instructions_wrong_model_name | 466/509 | 91.6% |
| important_instructions_wrong_user_name | 466/516 | 90.3% |
| injecagent | 460/505 | 91.1% |
| offensive_email_dos | 69/76 | 90.8% |
| swearwords_dos | 68/76 | 89.5% |
| tool_knowledge | 463/502 | 92.2% |

## Benign feature hits (eval split, FP sources)

| feature | benign runs hit |
|---|---|
| info_tag | 0 |
| addressed_msg | 0 |
| before_solve | 0 |
| ignore_previous | 0 |
| do_first | 76 |
| todo_directive | 40 |
