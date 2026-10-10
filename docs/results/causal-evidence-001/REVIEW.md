# R2.2: execution independent of evidence mode

Accepted execution source: `954f7b81bf6d78bcedc962a23f7b3bed073e84d2`.
All tests and new component predictions ran on hn072 (`ee4e072`). Original
G1, AST G2.1, machine policies and accepted raw records are preserved.

The final [test receipt](TESTS.json) records 71 passing targeted regressions.
This suite overlaps earlier R1/R2.1/G1/G2.1 tests; counts are not additive.
Seven frozen components pass [independent readback](VERIFIED.json), covering
10,787 flits and 30,604 boundaries including final reverse-credit drain.
Full, Compact and Counters have identical default causal states and semantic
progress at every boundary. There are two mode-pair comparisons per boundary.
All 1,224,440 seven-field scalar comparisons match. Full prediction files are
byte-identical to accepted R1; persisted Compact records independently expand
to the complete original events. Counters summaries/counts match quantities
derived from the original full events, without claiming a full flit audit.

The transition reports primitive events after semantic updates. Event dictionary
construction belongs to the evidence consumer, and completion never reads its
histories. The Counters regression rejects any call to the event-row encoder.
An independent schema decoder rejects missing/unknown streams, malformed rows,
duplicate service identities and inconsistent message clocks. It does not import
the producer or execute the candidate. Formal readback rechecks all 47 artifacts
and saved per-boundary ledgers rather than replacing saved outputs.

R2.2 deliberately retains eager source deques and packet/path metadata in every
mode. This is evidence separation, not elimination of all per-flit memory or a
performance claim. Source representation and macro migration remain separate.
No Native or application execution was started.

Raw campaign: `/Projects/haoning/wafer_simulator/runs/causal-evidence-001`;
tests: `causal-evidence-tests-001`; readback: `causal-evidence-readback-001`.
[Published copies](PUBLISHED_COPIES.json) are byte-verified against these server
paths. The campaign manifest is
`d54777804687969659b349db01cfbf8ce528e9af3baa0b73fd0ebad6237e05ff`.
