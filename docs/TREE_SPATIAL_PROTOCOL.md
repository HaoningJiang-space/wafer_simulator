# Fixed-tree AllReduce and physical traffic projection

The logical AllReduce and complete eight-head TP8 forward block remain unchanged.
`binary_tree_sum` is an execution policy. For communicator position i>0 its
parent is floor((i-1)/2); TP8 rank 7 belongs to rank 3. The tree never reads
target geometry, timing or measured performance. Entry, resource arbitration,
rank-local final-output publication and retirement are unchanged.

Leaves read their input and send it to the parent. An internal node reads its
own input and each stored child result, performs k*N scalar adds for k children,
then writes one subtree sum. A non-root internal node reserves separate partial
storage, reads that value and sends it up. Root writes its final output once.
Broadcast follows the same edges downward; each child output is written before
publication and before that child forwards to its children. Partial values are
never final outputs. All internal stages stay pinned through operation retirement.
This whole-tensor abstraction models no tiling, register capacity or streaming.

At distinct endpoints both algorithms send 2(P-1)D logical bytes and do (P-1)N
adds per AllReduce. They do not have identical memory work: each non-root
internal tree node adds one D-byte partial write and read. At TP8 there are
three such nodes (1,2,3), adding 6D bytes per collective. Across the block,
expected traffic is 114688 payload bytes, 28 messages, 84 native 2000-byte
flits; two reductions perform 14336 adds. Tree allocates three extra partial
objects per collective while distributing child staging across parents.
SUM association changes; real arithmetic semantics agree, bitwise floating
point identity is not asserted. Numerical/action-DAG checks use independent
rank contributions and float64 tolerance, including non-power-of-two ranks.

## Registered matrix and acceptance

`configs/transformer_tree_study.json` declares only six new arms: Baseline/Rotated
at 32/256/1024 B/cycle, fixed row-major and existing compute/network parameters.
Reuse six direct-root arms from `collective-memory-balance-001` only after hash
verification, independent re-audit using current binding, and exact matching of
logical work, mapping, target, timing, binary identity and all other controls.
No additional simulation of direct-root is necessary if these checks pass.

Validation checks full tensor SUM using the generated dependency/action graph,
byte/add conservation, local publication, partial invisibility, retained staging,
finite capacity, and live-native/standalone all-flit agreement. Every arm also
retains coarse-network execution and independent timing/lifetime audit.

## Spatial metrics

Use observed paths of **every flit**, rather than a representative message route.
Assign payload in source flit-ID order; the last flit carries only the residual
bytes. Count its full flit size separately as wire traffic. Report:

- Per-active-endpoint input/output bytes; maximum combined load and max/mean
  over the eight active endpoints (not all twenty physical endpoints).
- Every directed physical link, including zeros, with payload/wire bytes and
  flit counts; maximum and distribution. Directional links are independent
  capacity resources. `byte-hops` sums all inter-router traversals.
- A declared geometric graph cut: exported router-center x<0 versus x>=0, all layers.
  The pinned WoW export positions are centers (confirmed by its visualizer),
  so no half-dimension is added. This is not detailed wire routing.
  Sum capacity of all exported directed links crossing the partition. Count
  actual traversals, including repeated crossings. Report directions separately
  and max(ceil(wire_bytes_direction / capacity_direction)) as a loose service
  lower bound; unique crossing-message bytes would not give that accounting.
- Critical transfers/actions, per-region memory/add activity and whole-block
  completion. Integrated load and the cut lower bound do not prove saturation.

Run only on eex005 from clean committed source with `PYTHONPATH=src`:

```sh
python scripts/test_wow_target_remote.py TESTS
python scripts/run_transformer_wow_remote.py TREE TESTS/SEMANTICS.json --tree
python scripts/analyze_tree_spatial_remote.py DIRECT TREE ANALYSIS
python scripts/plot_tree_spatial_remote.py ANALYSIS FIGURES
```

Outcome is open: tree may improve, hurt or leave the placement gap unchanged.
Explain changes through depth, partial-result service, spatial traffic and
critical work. Do not attribute the entire effect solely to congestion.

The [accepted result](results/tree-spatial-001/REVIEW.md) contains the twelve-cell
comparison, spatial metrics, critical branches and all concrete run identities.
