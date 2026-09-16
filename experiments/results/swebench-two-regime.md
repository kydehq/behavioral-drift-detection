# Two-regime detector on SWE-bench submission ledgers

5 trials, seed base 7, divergence window 50,
calibration margin 1.2, submissions with >= 100 runs.
Real records, composed (shuffled) stream order — run order inside a
submission batch has no temporal meaning. See module docstring.

## Null stability within submissions (no drift expected; alarms = FP)

| submission | runs | cells | FP div | FP cusum | median horizon |
|---|---|---|---|---|---|
| 20240402_sweagent_claude3opus | 443 | 5 | 40% | 80% | 2089 |
| 20240402_sweagent_gpt4 | 496 | 5 | 20% | 40% | 2601 |
| 20240620_sweagent_claude3.5sonnet | 500 | 5 | 40% | 60% | 4120 |
| 20240728_sweagent_gpt4o | 465 | 5 | 0% | 40% | 4614 |
| 20241023_emergent | 498 | 5 | 0% | 0% | 375 |
| 20241029_OpenHands-CodeAct-2.1-sonnet-20241022 | 500 | 5 | 40% | 0% | 3225 |
| 20241125_enginelabs | 499 | 5 | 0% | 20% | 2255 |
| 20241223_emergent | 500 | 5 | 0% | 0% | 375 |
| 20250203_openhands_4x_scaled | 389 | 5 | 20% | 0% | 1889 |
| 20250415_openhands | 500 | 5 | 20% | 60% | 4693 |
| 20250511_sweagent_lm_32b | 500 | 5 | 0% | 80% | 5091 |
| 20250515_Refact_Agent | 500 | 5 | 40% | 40% | 3989 |
| 20250519_trae | 499 | 5 | 20% | 40% | 4717 |
| 20250524_openhands_claude_4_sonnet | 500 | 5 | 20% | 20% | 8721 |
| 20250603_Refact_Agent_claude-4-sonnet | 500 | 5 | 40% | 40% | 6126 |
| 20250612_trae | 499 | 5 | 80% | 20% | 5531 |
| 20250710_bloop | 500 | 5 | 20% | 0% | 7342 |
| 20250716_openhands_kimi_k2 | 500 | 5 | 40% | 40% | 7018 |
| 20250804_codesweep_sweagent_kimi_k2_instruct | 500 | 5 | 20% | 40% | 3613 |
| 20250807_openhands_gpt5 | 500 | 5 | 40% | 40% | 3767 |

## Version drift across submissions (same framework family; real version change)

| family | baseline submission | streamed submission | cells | dist. JSD | det. div | det. cusum | delay div | delay cusum |
|---|---|---|---|---|---|---|---|---|
| emergent | 20241023_emergent | 20241223_emergent | 5 | 0.000 | 0% | 0% | — | — |
| openhands | 20241029_OpenHands-CodeAct-2.1-sonnet-20241022 | 20250203_openhands_4x_scaled | 5 | 0.000 | 80% | 0% | 1175 | — |
| openhands | 20250203_openhands_4x_scaled | 20250415_openhands | 5 | 0.013 | 40% | 100% | 731 | 45 |
| openhands | 20250415_openhands | 20250524_openhands_claude_4_sonnet | 5 | 0.006 | 60% | 80% | 1856 | 2230 |
| openhands | 20250524_openhands_claude_4_sonnet | 20250716_openhands_kimi_k2 | 5 | 0.002 | 40% | 80% | 503 | 2234 |
| openhands | 20250716_openhands_kimi_k2 | 20250807_openhands_gpt5 | 5 | 0.105 | 100% | 0% | 53 | — |
| sweagent | 20240402_sweagent_claude3opus | 20240402_sweagent_gpt4 | 5 | 0.085 | 80% | 100% | 280 | 349 |
| sweagent | 20240402_sweagent_gpt4 | 20240620_sweagent_claude3.5sonnet | 5 | 0.116 | 100% | 100% | 157 | 123 |
| sweagent | 20240620_sweagent_claude3.5sonnet | 20240728_sweagent_gpt4o | 5 | 0.091 | 80% | 100% | 888 | 407 |
| sweagent | 20240728_sweagent_gpt4o | 20250511_sweagent_lm_32b | 5 | 0.813 | 100% | 100% | 116 | 55 |
| sweagent | 20250511_sweagent_lm_32b | 20250804_codesweep_sweagent_kimi_k2_instruct | 5 | 0.075 | 20% | 100% | 513 | 446 |
| trae | 20250519_trae | 20250612_trae | 5 | 0.021 | 80% | 100% | 339 | 946 |
