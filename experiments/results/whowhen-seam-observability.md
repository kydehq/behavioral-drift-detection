# Seam observability on Who&When records

All runs in this corpus are failures; no detection-rate
experiment is possible (module docstring). Measured instead:
whether the failure attribution a human produced can be stated
in terms the boundary record contains.

## Attribution observability

| variant | runs | records | seam labels | speakers | mistake agent visible | mistake step valid | both |
|---|---|---|---|---|---|---|---|
| algorithm-generated | 126 | 1099 | 191 | 191 | 126/126 | 126/126 | 126/126 |
| hand-crafted | 58 | 2993 | 11 | 6 | 58/58 | 58/58 | 58/58 |

## Where the annotated mistake sits, and who makes it

Position = mistake_step relative to run length. Routing weight =
median share of a run's messages spoken by the mistake agent.

| variant | early third | middle third | late third | median routing weight of mistake agent |
|---|---|---|---|---|
| algorithm-generated | 72 | 33 | 21 | 30.0% |
| hand-crafted | 29 | 10 | 19 | 22.2% |
