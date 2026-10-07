# Complete declared Transformer block

This input extends the validated A/B/AllReduce/C unit to one complete forward
block. It does not require further Chakra recovery. It is a separately named
analytical workload, not a fragment of the accepted capture, a Llama training
step, or calibrated hardware performance.

## Logical definition

`workloads/transformer.py` defines a bias-free pre-LayerNorm block with dense
unmasked multi-head self-attention, exact-erf GELU and two residual additions.
There is no dropout, KV cache, positional-encoding operation or backward pass.
The input is the block's already supplied activation, not token embeddings.

The registered configuration is batch 1, sequence 16, hidden width 64, four
heads, FFN width 128, and two tensor-parallel workers. All data is float32.
Q/K/V columns and whole attention heads are sharded; output-projection rows
are sharded. FFN up-projection columns and down-projection rows are sharded.
Both row-parallel projections produce full-width partial results, each followed
by a SUM AllReduce. Normalization and residual operations are replicated.

The full sequence is:

1. LayerNorm, Q/K/V projections, QK transpose multiplication.
2. Scaling, stable softmax, attention-value multiplication.
3. Output projection, SUM AllReduce, first residual addition.
4. LayerNorm, FFN up projection, exact GELU, FFN down projection.
5. SUM AllReduce and second residual addition, producing one replica per worker.

`tensors` records every shape, dtype and role. `operators` records mathematical
operator identities. Logical worker ownership is not a reticle ID:
`adapters/transformer.py` separately maps workers to endpoints and data homes.
Initial activations and LayerNorm parameters are declared replicas of equal
values; dense projection weights are independent shards of the corresponding
full matrix. Weights and normalization parameters remain resident; all other
intermediates release after their final consumers, except the final outputs.

For batch B, sequence S, width H and FFN width F, total matrix work is
`4*B*S*H^2 + 2*B*S^2*H + 2*B*S*H*F` MACs, independent of shard count. The
registered unit has **557,056 MACs**, thirty operations and two collectives.
This count does not convert source duration or assume two FLOPs per service
unit: one MAC is the explicit unit presented to the target.

## Scalar work and memory policy

LayerNorm uses centered variance, epsilon 1e-5, reciprocal square root, gamma
and beta. For N=B*S*H elements and R=B*S rows, it declares `4*N-R` additions
(including subtractions), `3*N+2*R` multiplications and R reciprocal square
roots. Softmax declares scaling, row maxima, subtract-max, exponentials, sums
and per-element divisions. Exact GELU `0.5*x*(1+erf(x/sqrt(2)))` declares three
multiplications, one addition and one erf per element. These work categories
have explicit separate rates, but share the worker's compute server.

Each operator reads its full logical inputs once and materializes its outputs;
attention scores and probabilities are separate resident objects. LayerNorm
and softmax each reserve two scalar arrays per row for temporary statistics.
Register-resident arithmetic and matrix accumulation are abstracted into compute
service; additional tiled rereads, cache behavior, matrix-engine utilization and
internal kernel traffic are not modeled. These are ideal operator-service
assumptions, not a claim to reproduce a GPU or a fabricated wafer kernel.

Both collectives reuse the existing conservative lowering: gather at worker 0,
sum, then materialize all destination outputs. The collective completes only
after every output home has been written. This is not a ring algorithm or
rank-local asynchronous collective completion. With workers on different memory
regions, the two collectives move **16,384 logical bytes** through the network;
link-service bytes can be larger because each physical hop serves those bytes.

The timed model now binds this explicit collective through the existing action
DAG. Independent source reads/gathers can overlap; the root result is written
once, then read for each broadcast. Root accesses share their memory port. All
participant inputs and output/staging reservations are required at entry, and
global completion still waits for every destination write. The earlier generic
multi-output lowering overcharged root materialization and is superseded; see
[collective timing](COLLECTIVE_TIMING.md).

## Target and validation

`configs/transformer_block.json` declares a two-region analytical machine with
256 KiB per region and two router hops between endpoints. Compute, memory,
endpoint and link rates are model parameters. The existing integer-cycle FCFS
calendar, whole-message network, atomic storage admission and independent
readback are reused unchanged. `adapters/declared_target.py` also serves the
original analytical unit; no second timing engine was added.

The first cases keep this entire forward block, routing, capacity, mapping and
collective policy fixed, then separately double compute, memory or network
rates. These are resource-response checks, not a placement ranking experiment.

Tests independently assemble dense full matrices and compare the entire
partitioned forward DAG numerically, including multi-batch and single-token
inputs. A float64 oracle isolates logical equivalence from device rounding;
the timing model's object sizes remain float32. Independent formulas check
all MAC and scalar counts. Other tests check transfer byte conservation, final
residency, collective completion, missing service rates, insufficient initial
capacity and unchanged original 113-cycle event records.

On eex005, run semantic tests at a clean committed revision, then:

```
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python \
  scripts/run_timed_example_remote.py ABSOLUTE_FRESH_OUTPUT TEST_RECEIPT \
  --workload transformer
```

The runner writes the complete DAG, shape/operator ledger, hardware, placement,
event records, resource queues, lifecycle, independent audit and hashes. The
full capture and accepted M0/M1 data remain separate evidence.

The subsequent [WoW placement pair](TRANSFORMER_WOW_PROTOCOL.md) reuses this
entire logical block and common compute/memory parameters. It replaces the
hand-declared network and endpoint map with each author's actual resource graph
and the same row-major mapping rule. Live BookSim receives only currently ready
transfers. The [accepted pair](results/transformer-wow-001/REVIEW.md) reports
the historical 13,062/13,430 cycles. Its [corrected action-based successor](results/collective-execution-001/REVIEW.md)
reports 12,550/12,918 cycles, followed by a separately registered eight-head
TP4/TP8 and two-mapping study.
