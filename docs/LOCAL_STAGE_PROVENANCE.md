# Fixed local stages: source audit and the M0/M1 boundary

Checked on eex005 on 2026-10-06. The 006 implementation and result are frozen;
random mapping and further simulator optimization remain deferred.

Complete M0 lowering identity and M1 input audits passed. The first full M1
attempt (`llama16-model-boundary-M1-001`) failed during native input loading:
006 rejects repeated predecessor IDs. Both failure records are retained and
provide no application result. The adapter now explicitly represents shared
requires/arrival predicates once, retaining both source relation kinds in the
graph and independent audit. The same study retries in `llama16-model-boundary-M1-002`
after rechecking both complete M0 serializations and the full predecessor graph.
The native binary remains unchanged. Accepted results and critical-chain
readback will be written to `runs/model-boundary-analysis-001`.

The second controller started at **14:48:20 UTC**, PID `2727834`, with log
`logs/model-boundary-M1-002.log`. Both complete M0 traces have again matched
their original hashes after the predicate repair. The full transformation
readback confirms identical native predecessor structure (9,002,700 edges),
unchanged non-transfer operations and no double charging. This is input
acceptance, not a completed M1 application result.

## What the source audit established

The two dominant operations are measured intervals between NCCL event groups,
not transfer-model calls or calibrated pure-compute stages. Their original
GOAL identities were recovered through a **complete source correspondence**,
not a match based only on duration or CPU lane.

| Original operation | GOAL host / label | Original interval | Same-process/device non-NCCL kernel coverage | Time outside recorded kernels |
| --- | --- | ---: | ---: | ---: |
| 4895210 | 3 / 902031 | 556.029402 ms | 354.010909 ms | 202.018493 ms |
| 2066694 | 1 / 735605 | 382.900771 ms | 376.836770 ms | 6.064001 ms |

Both intervals contain 1,241 non-NCCL kernels, including elementwise, copy
and reduction kernels. No NCCL kernel overlaps either interval on the identified
process/device. This does **not** make uncovered time communication waiting,
or kernel coverage calibrated pure computation. No interval was shortened.
The kernel audit records absolute boundaries, process/device IDs and SQLite
hashes in [INTERVAL_ACTIVITY.json](results/local-stage-provenance/INTERVAL_ACTIVITY.json).

The selected critical chains now have the following source classification.
All durations below are preserved original services at the existing 1-GHz
replay convention; they are not target hardware measurements.

| Fixed local category | Baseline, cycles | Rotated, cycles |
| --- | ---: | ---: |
| Measured event-group intervals | 1,201,830,747 | 1,201,384,604 |
| Reduction model | 254,504,564 | 254,503,434 |
| Copy model | 172,258,848 | 173,052,501 |
| Combined reduction/copy model | 44,504,747 | 42,114,062 |
| Intra-host GPU transfer model | 64,910,070 | 64,610,729 |
| Zero-duration synchronization placeholders | 0 | 0 |
| Total fixed local service | 1,738,008,976 | 1,735,665,330 |

Every selected local stage has a source category. This is complete rule
classification, not complete physical interpretation of measured intervals.
In particular, the original claim of approximately 99.95% local service cannot
be restated as approximately 99.95% pure computation. Nor is the transfer
service on one selected chain a bound on its counterfactual performance effect.

The complete server-only table is
`runs/local-stage-provenance-001/local_stage_provenance.csv` (about 21 MB).
[Major stages](results/local-stage-provenance/major_local_stages.csv) and
[the full category totals and artifact hashes](results/local-stage-provenance/LOCAL_STAGES.json)
are published here.

An independent delivery check read all **99,428** selected-chain source rows
against original operation identities and durations, and closed both category
totals. Its [receipt](results/local-stage-provenance/PROVENANCE_COMPLETE.json)
records the script, environment and all artifact hashes. The final source and
attribution regression checks passed **21 tests** on eex005 in
`runs/local-provenance-unit-005` (12 attribution and 9 source/conversion checks).
These are semantic software checks, not reduced-work performance experiments.

## How correspondence was proved

All four public Nsight reports were downloaded and exported on eex005. No raw
capture, SQLite export, complete GOAL, event array or large CSV was downloaded
to the local checkout.

The current ATLAHS pin cannot regenerate this published input: it changes
message counts and NPKit cost generation. The unmodified historical author
revision `e436c1de79619e7bcd9977e2a713f8e4a1f7e8f9`, with its existing
`merge_non_overlap` and `unique_nic` options, recovers the complete serialized
structure under the source-host order `[2, 0, 3, 1]`:

- 5,324,230 operations: 4,432,750 calc and 445,740 send/receive pairs;
- all 8,556,960 original dependency lines;
- identical operation labels, CPU/NIC assignments, messages, byte counts,
  peers, tags, line ordering and dependency structure.

Historical reduction/copy routines make cached random choices. Fresh draws
changed 1,731,968 calc durations. Every changed amount was observed at a
reduction/copy source call; **no interval or transfer duration differed**.
The original published costs are constant for each corresponding cached model
key. They were retained, not replaced with fresh draws or a newer median model.
The rebuilt file is therefore source evidence, not the M0 execution input.
The unchanged original file remains M0.

The source observer wraps author writes and model calls without editing author
files. It records the executed source line, GPU, event group, model arguments,
transfer peer and interval boundaries. An independent pass checks all source
records against the original graph and hashes every GOAL line with only calc
amounts normalized; non-NPKit amounts are then required to match exactly.
See [SOURCE_CORRESPONDENCE.json](results/local-stage-provenance/SOURCE_CORRESPONDENCE.json).

`source_stream` is the author's logical stream label after coalescing; it is
not a raw CUDA stream ID. The interval activity audit records CUDA stream IDs
separately. The parser GPU index and GOAL CPU-lane number likewise retain their
distinct meanings.

## Source-supported transfer recovery

The original cross-GPU dependencies uniquely pair **1,337,280 local sends and
1,337,280 local receives**. Every pair has complementary source/peer GPUs,
matching positive size and the same original host. There are no missing or
multiply matched endpoints. The recorded transfer-model byte arguments sum to
**909,686,250,240 bytes**. Both endpoint cost totals are 3,031,750,800 cycles
over the entire graph; these parallel totals must not be treated as application
duration. See [LOCAL_TRANSFERS.json](results/local-stage-provenance/LOCAL_TRANSFERS.json).

This identifies specific original-platform transfer costs hidden in calc.
It does not yet establish their effect on placement ranking.

## The single next comparison

M0 reuses the accepted 006 pair. M1 substitutes only these paired local
transfers with messages between their mapped compute-reticle endpoints.
Both old endpoint transfer durations are removed, so network service is not
charged on top of the original transfer cost. All other calc values and all
original dependency lines remain unchanged. The workload, collective algorithm,
mapping, seed, network and clock controls are fixed.

A recovered receive has both an original requires edge and a matched-arrival
relation from its send. Both await the same completed-send event, so their
conjunction is one native predecessor predicate. Both source relations remain
in the input arrays and independent timing audit, and the critical-chain reader
records both reasons. Profile checks distinguish source relation occurrences
from unique native predicates. The entire M1 predecessor graph must equal M0's
graph: the recovered arrivals were already original local requires edges.
Complete M0 lowering must
still reproduce both saved traces and contracts, and M1 must pass the complete
input and graph audits before execution. The native binary is frozen 006.

Preparation and execution live in separate scripts. `prepare_model_boundary_remote.py`
performs source checks, materializes M1, verifies M0 identity and audits M1.
It launches no simulation. M1 results must be accepted before comparing
`Delta_M0 = T_baseline,M0 - T_rotated,M0` with `Delta_M1`.

Even M1 preserves composite intervals and GPU-derived reduction/copy costs.
Its result will test this transfer boundary under fixed remaining local costs;
it will not be calibrated native WoW training time. Router/link costs still
differ between placements, and internal port/VC causes remain unobserved.

The 002–006 direct full-event comparison continues independently. Neither
source correspondence nor M0 lowering identity claims that it has finished.
