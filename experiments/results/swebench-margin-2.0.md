# Two-regime detector on SWE-bench submission ledgers

10 trials, seed base 7, divergence window 50,
calibration margin 2.0, submissions with >= 100 runs.
Real records, composed (shuffled) stream order — run order inside a
submission batch has no temporal meaning. See module docstring.

## Null stability within submissions (no drift expected; alarms = FP)

| submission | runs | cells | FP div | FP cusum | median horizon |
|---|---|---|---|---|---|
| 20240402_sweagent_claude3opus | 443 | 10 | 0% | 20% | 2105 |
| 20240402_sweagent_gpt4 | 496 | 10 | 0% | 20% | 2570 |
| 20240620_sweagent_claude3.5sonnet | 500 | 10 | 0% | 30% | 4186 |
| 20240728_sweagent_gpt4o | 465 | 10 | 0% | 0% | 4578 |
| 20241023_emergent | 498 | 10 | 0% | 0% | 375 |
| 20241029_OpenHands-CodeAct-2.1-sonnet-20241022 | 500 | 10 | 10% | 0% | 3139 |
| 20241125_enginelabs | 499 | 10 | 0% | 10% | 2248 |
| 20241223_emergent | 500 | 10 | 0% | 0% | 375 |
| 20250203_openhands_4x_scaled | 389 | 10 | 20% | 0% | 1914 |
| 20250415_openhands | 500 | 10 | 10% | 0% | 4714 |
| 20250511_sweagent_lm_32b | 500 | 10 | 0% | 50% | 5147 |
| 20250515_Refact_Agent | 500 | 10 | 20% | 30% | 4100 |
| 20250519_trae | 499 | 10 | 0% | 0% | 4720 |
| 20250524_openhands_claude_4_sonnet | 500 | 10 | 10% | 0% | 8910 |
| 20250603_Refact_Agent_claude-4-sonnet | 500 | 10 | 30% | 40% | 6195 |
| 20250612_trae | 499 | 10 | 0% | 0% | 5513 |
| 20250710_bloop | 500 | 10 | 30% | 0% | 7372 |
| 20250716_openhands_kimi_k2 | 500 | 10 | 0% | 30% | 7030 |
| 20250804_codesweep_sweagent_kimi_k2_instruct | 500 | 10 | 30% | 20% | 3773 |
| 20250807_openhands_gpt5 | 500 | 10 | 10% | 10% | 3776 |

## Version drift across submissions (same framework family; real version change)

| family | baseline submission | streamed submission | cells | dist. JSD | det. div | det. cusum | delay div | delay cusum |
|---|---|---|---|---|---|---|---|---|
| emergent | 20241023_emergent | 20241223_emergent | 10 | 0.000 | 0% | 0% | — | — |
| openhands | 20241029_OpenHands-CodeAct-2.1-sonnet-20241022 | 20250203_openhands_4x_scaled | 10 | 0.000 | 60% | 0% | 2276 | — |
| openhands | 20250203_openhands_4x_scaled | 20250415_openhands | 10 | 0.013 | 30% | 100% | 299 | 20 |
| openhands | 20250415_openhands | 20250524_openhands_claude_4_sonnet | 10 | 0.006 | 10% | 0% | 1054 | — |
| openhands | 20250524_openhands_claude_4_sonnet | 20250716_openhands_kimi_k2 | 10 | 0.002 | 20% | 50% | 4875 | 6210 |
| openhands | 20250716_openhands_kimi_k2 | 20250807_openhands_gpt5 | 10 | 0.105 | 90% | 0% | 188 | — |
| sweagent | 20240402_sweagent_claude3opus | 20240402_sweagent_gpt4 | 10 | 0.085 | 10% | 50% | 2045 | 581 |
| sweagent | 20240402_sweagent_gpt4 | 20240620_sweagent_claude3.5sonnet | 10 | 0.116 | 40% | 100% | 697 | 137 |
| sweagent | 20240620_sweagent_claude3.5sonnet | 20240728_sweagent_gpt4o | 10 | 0.091 | 0% | 90% | — | 543 |
| sweagent | 20240728_sweagent_gpt4o | 20250511_sweagent_lm_32b | 10 | 0.813 | 0% | 100% | — | 84 |
| sweagent | 20250511_sweagent_lm_32b | 20250804_codesweep_sweagent_kimi_k2_instruct | 10 | 0.075 | 0% | 100% | — | 861 |
| trae | 20250519_trae | 20250612_trae | 10 | 0.021 | 0% | 80% | — | 1973 |
