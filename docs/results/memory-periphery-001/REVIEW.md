# Memory-periphery policy sensitivity: 6x6 A/B

The declared bounded pipeline changes the restricted A/B preference. This is
machine-policy sensitivity, not a prediction-error comparison or hardware validation.

| Condition | A cycles | B cycles | A−B | Preferred | Old A choice regret |
|---|---:|---:|---:|---|---:|
| v1_whole | 30645 | 31303 | -658 | A | 0 |
| shared_whole | 30645 | 31303 | -658 | A | 0 |
| shared_pipeline | 25345 | 23561 | 1784 | B | 1784 |

A=`clustered_local`; B=`remote_balanced`. Positive A−B favors B.
All six cells reproduce exactly across three fresh-process repetitions.
Old v1 A/B execution hashes reproduce the accepted S records. The v1 export
config and topology are byte-identical to the archived exporter.

At whole-object policy the interface change leaves both application times
unchanged in this experiment. At the fixed shared-interface organization,
the pipeline changes the supply schedule and application preference. The
old reversal therefore depends on transaction policy in this declared case.
It remains evidence for v1, but is not established as policy-independent.

The pipeline preserves payload/control bytes, work, full-object reservations,
operand order and retirement/publication. It uses 4 KiB fragments and four
slots per transaction; all observed windows are within that bound. Bank
latency follows each serializer request and can overlap other requests.
The policy also applies to external-controller traffic; SRAM C2C stays whole.
This is not solely a change in DRAM response scheduling.

Nine native component executions precede applications; all 27 saved
executions were independently reaudited and all 15 registered command
streams replayed. Detailed traffic/resource/event evidence stays on hn072.

| Component | v1 whole | shared whole | shared pipeline |
|---|---:|---:|---:|
| read | 7228 | 7228 | 3388 |
| write | 7228 | 7228 | 3388 |
| two_banks | 9297 | 9297 | 5457 |

| Condition/layout | Fresh worker median (s) | Native messages | Native flits | Python RSS max (MiB) | Native RSS max (MiB) |
|---|---:|---:|---:|---:|---:|
| v1_whole/clustered_local | 7.490 | 254 | 92525 | 379.9 | 217.4 |
| v1_whole/remote_balanced | 10.751 | 254 | 92525 | 492.2 | 329.7 |
| shared_whole/clustered_local | 7.133 | 254 | 92525 | 379.4 | 216.5 |
| shared_whole/remote_balanced | 10.100 | 254 | 92525 | 492.1 | 328.7 |
| shared_pipeline/clustered_local | 7.933 | 1445 | 92525 | 402.6 | 208.9 |
| shared_pipeline/remote_balanced | 10.891 | 1445 | 92525 | 504.2 | 284.6 |

Campaign wall: 202.394 s; component workers: 7.607 s; application workers: 162.910 s; native replay: 30.252 s. No calibration table was fitted.

Per-stage timing, CPU, RSS ranges, output size, source/binary/input/result
identities, traffic envelopes and verification receipts are in RESULTS.json,
SUMMARY.json and CHECKED.json. Host load and affinity were recorded; other
research jobs shared the host, so wall times are descriptive measurements.

Limits: one fixed fragment/window choice and one known 6x6 workload/layout
pair. No bank-specific-interface pipeline arm, no factorial interaction
estimate, no Local rerun/global optimum claim, no new holdout or hardware
calibration. D1 remains an unvalidated v1 application candidate. D0/D1 need
the same policy/organization before any new prediction-accuracy assessment.

Experiment source: `1c7a84aff461ef6eb60255686d70d097a9677ef4`. Server evidence: `/Projects/haoning/wafer_simulator/runs/periphery-applications-001`.
