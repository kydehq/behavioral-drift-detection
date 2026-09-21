# E4b: hallucination detection and localization on AgentHallu

Paper-use-only corpus (adapter docstring). Detection: one frozen
cross-channel rule (tool-response error, unacknowledged in the
final message), developed on the ~20% dev split; 'eval' is the
held-out measurement. Localization: E4's frozen Who&When
predictors transferred verbatim (whole corpus held-out) plus the
re-instantiated first_worker_local; targets are the corpus's
1-based source steps on annotated hallucinated runs.

## Detection (unacknowledged_error)

| framework | split | hallucinated | clean | detection | FPR |
|---|---|---|---|---|---|
| bfcl | eval | 81 | 50 | 54.3% | 40.0% |
| bfcl | dev | 22 | 11 | 72.7% | 36.4% |
| camel | eval | 43 | 28 | 30.2% | 32.1% |
| camel | dev | 14 | 8 | 64.3% | 37.5% |
| magentic-one | eval | 46 | 32 | 6.5% | 0.0% |
| magentic-one | dev | 8 | 8 | 0.0% | 12.5% |
| octotools | eval | 27 | 15 | 25.9% | 13.3% |
| octotools | dev | 3 | 2 | 33.3% | 0.0% |
| opendeepsearch | eval | 44 | 31 | 15.9% | 3.2% |
| opendeepsearch | dev | 14 | 11 | 7.1% | 0.0% |
| openmanus | eval | 62 | 18 | 12.9% | 16.7% |
| openmanus | dev | 22 | 2 | 22.7% | 0.0% |
| smolagents | eval | 51 | 29 | 21.6% | 31.0% |
| smolagents | dev | 6 | 5 | 16.7% | 40.0% |
| **all** | eval | 354 | 203 | 26.3% | 21.7% |
| **all** | dev | 89 | 47 | 37.1% | 21.3% |

## Localization transfer (annotated hallucinated runs)

| framework | runs | E[random] | first | third | middle | last | first_error | before_first_error | before_first_apology | first_worker | second_worker | first_worker_local |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bfcl | 103 | 12% | 9% | 17% | 15% | 3% | 9% | 9% | 9% | 9% | 6% | 9% |
| camel | 57 | 15% | 9% | 58% | 23% | 12% | 9% | 9% | 9% | 9% | 0% | 9% |
| magentic-one | 54 | 14% | 31% | 35% | 17% | 6% | 31% | 31% | 30% | 31% | 2% | 35% |
| octotools | 30 | 24% | 3% | 20% | 53% | 3% | 3% | 3% | 3% | 3% | 47% | 3% |
| opendeepsearch | 58 | 23% | 28% | 19% | 36% | 2% | 28% | 28% | 28% | 28% | 29% | 28% |
| openmanus | 84 | 22% | 46% | 20% | 25% | 1% | 46% | 46% | 48% | 46% | 11% | 46% |
| smolagents | 57 | 21% | 44% | 12% | 18% | 11% | 44% | 44% | 44% | 44% | 16% | 44% |
