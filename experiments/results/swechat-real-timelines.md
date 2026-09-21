# Real-timeline experiments on SWE-chat (E5)

Ledger agent `claude-code`, 171 users total; divergence window 50, margins 2.0, 1.2, 10 composed trials (seed base 7), min block 400 records, version boundaries at >= 300 old / >= 150 new records, streams capped at 2000 events.

Real wall-clock session order; the composed arm re-shuffles the same
sessions under the companion protocol. See module docstring.

## Null stability, real vs composed order (margin 2.0)

One cell per user: longest contiguous same-CLI-version session
block, 50/25/25 chronological split; alarms on the null quarter
are false positives. Composed = session order shuffled.

| arm | users | FP div | FP cusum | median horizon |
|---|---|---|---|---|
| real (chronological) | 65 | 6% | 34% | 314 |
| composed (shuffled x10) | 65 | 5% | 30% | 314 |

## Null stability, real vs composed order (margin 1.2)

One cell per user: longest contiguous same-CLI-version session
block, 50/25/25 chronological split; alarms on the null quarter
are false positives. Composed = session order shuffled.

| arm | users | FP div | FP cusum | median horizon |
|---|---|---|---|---|
| real (chronological) | 65 | 34% | 48% | 314 |
| composed (shuffled x10) | 65 | 32% | 45% | 314 |

## Real CLI version drift (margin 2.0)

Boundaries read off the records: baseline on ~2/3 of the old
version block, calibration on the rest, the new version block
streamed. Control = identical protocol at a fake boundary at
~60% of single-version blocks.

| arm | boundaries | det div | det cusum | median JSD | median delay div | median delay cusum |
|---|---|---|---|---|---|---|
| real version change | 19 | 26% | 47% | 0.132 | 658 | 147 |
| control (no change) | 65 | 17% | 55% | 0.127 | 174 | 151 |

Per-boundary rows (real changes), sorted by JSD:

| user | old -> new | n old / new | gap days | JSD | div | cusum |
|---|---|---|---|---|---|---|
| FSM1 | 0.4.2 -> 0.5.1 | 594 / 419 | 46.3 | 0.343 | . | . |
| jdsingh1 | 0.4.8 -> 0.4.9 | 458 / 861 | 1.9 | 0.335 | . | x |
| abiswas@ | 0.4.2 -> 0.5.1 | 3182 / 1516 | 33.9 | 0.200 | . | x |
| Nagi-ovo | 0.4.5 -> 0.4.8 | 848 / 2398 | 5.9 | 0.155 | x | x |
| tarasyar | 0.4.9 -> 0.5.1 | 1574 / 327 | -0.1 | 0.153 | . | . |
| nosman | 0.5.0 -> 0.5.1 | 1390 / 413 | 8.7 | 0.152 | . | . |
| ronnnnn | 0.5.1 -> 0.5.3 | 372 / 188 | 15.2 | 0.150 | x | x |
| abiswas@ | 0.5.1 -> 0.5.3 | 1516 / 907 | 15.0 | 0.140 | . | . |
| raman325 | 0.4.2 -> 0.4.7 | 876 / 930 | 20.2 | 0.139 | . | . |
| khaong | v0.4.7-215-g473bd8795 -> v0.4.8-47-g08af2461b | 696 / 311 | -0.0 | 0.132 | . | . |
| schmalle | 0.4.2 -> 0.5.0 | 423 / 1360 | 0.2 | 0.127 | x | x |
| robouden | 0.4.2 -> 0.4.8 | 1845 / 735 | 1.9 | 0.125 | . | x |
| ronnnnn | 0.4.3 -> 0.4.7 | 345 / 312 | 4.9 | 0.122 | x | x |
| FSM1 | 0.5.1 -> 0.5.0 | 419 / 310 | 0.7 | 0.113 | . | x |
| nosman | 0.4.8 -> 0.5.0 | 660 / 1390 | 0.6 | 0.107 | x | . |
| khaong | dev -> v0.4.4-34-gc899b591-dirty | 396 / 173 | 1.5 | 0.092 | . | . |
| KeKs0r | 0.4.4 -> 0.4.9 | 6403 / 1660 | 0.0 | 0.085 | . | x |
| hutusi | 0.4.8 -> 0.5.0 | 846 / 170 | 0.1 | 0.076 | . | . |
| gtrrz-vi | dev -> v0.4.7-59-g6588fad7-dirty | 1062 / 270 | 0.9 | 0.048 | . | . |

## Real CLI version drift (margin 1.2)

Boundaries read off the records: baseline on ~2/3 of the old
version block, calibration on the rest, the new version block
streamed. Control = identical protocol at a fake boundary at
~60% of single-version blocks.

| arm | boundaries | det div | det cusum | median JSD | median delay div | median delay cusum |
|---|---|---|---|---|---|---|
| real version change | 19 | 47% | 68% | 0.132 | 64 | 130 |
| control (no change) | 65 | 52% | 68% | 0.127 | 140 | 143 |

Per-boundary rows (real changes), sorted by JSD:

| user | old -> new | n old / new | gap days | JSD | div | cusum |
|---|---|---|---|---|---|---|
| FSM1 | 0.4.2 -> 0.5.1 | 594 / 419 | 46.3 | 0.343 | . | x |
| jdsingh1 | 0.4.8 -> 0.4.9 | 458 / 861 | 1.9 | 0.335 | x | x |
| abiswas@ | 0.4.2 -> 0.5.1 | 3182 / 1516 | 33.9 | 0.200 | . | x |
| Nagi-ovo | 0.4.5 -> 0.4.8 | 848 / 2398 | 5.9 | 0.155 | x | x |
| tarasyar | 0.4.9 -> 0.5.1 | 1574 / 327 | -0.1 | 0.153 | . | . |
| nosman | 0.5.0 -> 0.5.1 | 1390 / 413 | 8.7 | 0.152 | . | x |
| ronnnnn | 0.5.1 -> 0.5.3 | 372 / 188 | 15.2 | 0.150 | x | x |
| abiswas@ | 0.5.1 -> 0.5.3 | 1516 / 907 | 15.0 | 0.140 | . | . |
| raman325 | 0.4.2 -> 0.4.7 | 876 / 930 | 20.2 | 0.139 | . | . |
| khaong | v0.4.7-215-g473bd8795 -> v0.4.8-47-g08af2461b | 696 / 311 | -0.0 | 0.132 | . | x |
| schmalle | 0.4.2 -> 0.5.0 | 423 / 1360 | 0.2 | 0.127 | x | x |
| robouden | 0.4.2 -> 0.4.8 | 1845 / 735 | 1.9 | 0.125 | x | x |
| ronnnnn | 0.4.3 -> 0.4.7 | 345 / 312 | 4.9 | 0.122 | x | x |
| FSM1 | 0.5.1 -> 0.5.0 | 419 / 310 | 0.7 | 0.113 | x | x |
| nosman | 0.4.8 -> 0.5.0 | 660 / 1390 | 0.6 | 0.107 | x | x |
| khaong | dev -> v0.4.4-34-gc899b591-dirty | 396 / 173 | 1.5 | 0.092 | . | . |
| KeKs0r | 0.4.4 -> 0.4.9 | 6403 / 1660 | 0.0 | 0.085 | . | x |
| hutusi | 0.4.8 -> 0.5.0 | 846 / 170 | 0.1 | 0.076 | x | . |
| gtrrz-vi | dev -> v0.4.7-59-g6588fad7-dirty | 1062 / 270 | 0.9 | 0.048 | . | . |

## Fingerprint accounting (JSD over 400-record blocks)

| comparison | n | median | q1 | q3 |
|---|---|---|---|---|
| within user, adjacent blocks | 58 | 0.149 | 0.101 | 0.211 |
| within user, first vs last block | 34 | 0.211 | 0.140 | 0.276 |
| between users, first blocks | 1653 | 0.358 | 0.296 | 0.424 |

Aging curve (JSD of block k vs block 0, median across users):

| k | users | median JSD | median lag days |
|---|---|---|---|
| 1 | 41 | 0.137 | 1.6 |
| 2 | 41 | 0.158 | 3.6 |
| 3 | 34 | 0.155 | 6.9 |
| 4 | 25 | 0.158 | 7.7 |
| 5 | 23 | 0.154 | 7.9 |
| 6 | 15 | 0.201 | 7.7 |
| 7 | 14 | 0.221 | 8.9 |
| 8 | 11 | 0.160 | 9.8 |
| 9 | 10 | 0.134 | 9.8 |
| 10 | 10 | 0.169 | 12.2 |
| 11 | 9 | 0.174 | 14.2 |
| 12 | 9 | 0.206 | 13.6 |
