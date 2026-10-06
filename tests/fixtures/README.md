# Arbitration reference

`allocator-grants.sha256` identifies the 1,500 rounds emitted by
`tests/native_allocator_replay.cpp` on eex005: 500 rounds each of input-first,
output-first and iSLIP allocation, including ties, priority and removals.

The expected grants were obtained from the pre-node-reuse implementation and
matched byte for byte after node reuse. Original evidence remains at
`/home/wangziheng/wafer_simulator/runs/node-reuse-contract-002/` as
`runtime-opt-grants.txt` and `node-reuse-grants.txt`. See `docs/NODE_REUSE.md`.

The single maintained implementation is checked against this frozen reference.
Changing the expected hash requires an explained change to the input fixture or
arbitration contract; never regenerate it just to make a failure pass.
