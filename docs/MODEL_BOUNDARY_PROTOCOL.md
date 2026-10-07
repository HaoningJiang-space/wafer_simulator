# Source-local cost versus target-resource service

Research question: for the same complete AI work, how much does a better WoW
network improve application completion, and which costs and shared resources
must be modeled to judge that correctly?

This document consolidates the existing M0/M1 contract and records the next
methodological questions. It does not register or launch another experiment.
On 2026-10-07 the current delivery is the
[source classification](LOCAL_STAGE_PROVENANCE.md),
[target-resource mapping](TARGET_RESOURCE_MAPPING.md) and this protocol.
The one previously authorized M1 pair has already completed; it is retained
as evidence, not restarted to follow a new document sequence.

## One model boundary, with explicit retained assumptions

M0 is accepted run `llama16-full-006-csr-frontier`. M1 is accepted retry
`llama16-model-boundary-M1-002`; attempt 001 failed at input loading and remains
excluded. Both models use the identical frozen 006 binary and, within each
placement, identical geometry, network configuration and endpoint mapping.

M1 replaces only the 1,337,280 source-verified intra-host transfer pairs with
messages between their target reticles. It removes both fixed endpoint costs,
retains every original requires line and replaces completion by all-flit
arrival plus the receive join. CPU-lane issue policy is unchanged; the replaced
operations now have the network-resource occupancy described in the mapping
document. M0/M1 is therefore a transfer representation and resource-ownership
comparison. It does not isolate contention from target cost or lane occupancy.

| Held fixed | Requirement |
| --- | --- |
| Logical work | Same complete Llama capture, collective algorithm, byte arguments and original dependency relations |
| Remaining local work | Every non-transfer operation, interval and reduction/copy duration remains unchanged |
| Target assignment | Same row-major `(host,NIC)` assignment rule; unchanged within each placement across models |
| Operation policy | Same lane arbitration, zero CPU send-issue cost and all-flit completion semantics |
| Network | Same author geometry and parameters per placement; 1 GHz, 2000-byte flits, routing, buffers and seed 1 |
| Native execution | Exact same binary SHA-256, not merely the same source revision |

This conversion preserves 5,324,230 operation identities. Explicit messages
increase from 445,740 to 1,783,020 and flits from 151,889,580 to 607,558,380.
All 8,556,960 original requires relations remain. New matched-arrival relations
overlap existing send-to-receive requires edges, so the unique native graph
remains 9,002,700 predecessor predicates. Both source relation kinds are
retained in arrays and audited; one completion satisfies their conjunction.
These exact counts describe this conversion, not a general requirement that
every valid intermediate representation preserve node count.

## Acceptance, without repeating completed work

The following checks have already passed and are recorded by hashes:

1. Complete source correspondence; unique peer and positive-size pairing for
   every modified transfer. Major fixed stages retain their identified source
   category; composite interval contents remain explicitly uncalibrated.
2. Full M0 lowered traces and contracts match the accepted originals for both
   placements. M0 uses the original published costs, not fresh random model draws.
3. Complete M1 operation/dependency readback proves unchanged non-transfer
   operations, retained original messages/relations and no double charge.
4. Semantic regression checks cover pairing, dependency representation and
   cost removal; full-run audits check every completion and arrival, CPU
   non-overlap, message phases and total work. A timeout cannot pass.
5. Both M1 arms and dependency profiles are complete. The separate original
   002-versus-006 check now also reports identical complete input/event hashes
   for both placements. This validates implementation optimization on M0;
   it neither requires M0/M1 event equality nor validates M1's physical accuracy.

See [source/conversion receipt](results/local-stage-provenance/PROVENANCE_COMPLETE.json),
[transformation audit](results/local-stage-provenance/TRANSFORMATION_AUDIT.json),
[M0 recheck](results/local-stage-provenance/M0_IDENTITY_RECHECK.json),
[M1 acceptance](results/model-boundary-001/M1/acceptance.json) and
[002/006 equivalence](results/model-boundary-001/implementation_equivalence.json).
The generic M1 attribution snapshot still says reference equivalence `pending`:
it did not consume the separate final M0 verification. Its bytes are preserved;
the two records answer different checks and must not be silently conflated.

## Read the comparison at application and message level

For each model report `T_baseline`, `T_rotated`, their difference, percentage
reduction relative to that model's Baseline, and `T_baseline/T_rotated`.
Then compare the two differences, without requiring a ranking reversal.
Recover the actual chain in each arm; distinguish unchanged local service
durations from changed chain membership or lane blocking.

Original inter-host messages are a common population of 445,740 messages and
must be matched by original operation identity across models. The added
1,337,280 messages form a separate population. Across-model all-message means
mix these populations and cannot identify the cause of an application change.
Readiness-to-start, start-to-first-injection and first-injection-to-completion
are distinct intervals; the last includes serialization and competition.

The [accepted four-cell result](results/model-boundary-001/REVIEW.md) is an
observation under this contract. Changed prediction alone does not establish
improved accuracy. Source support establishes what was moved; target hardware
evidence would be needed to establish absolute timing accuracy.

## The next simple comparator is a question, not a launched experiment

If further work is warranted, compare M1 with a target static-cost model that
uses the same recovered bytes, target paths and interface/router costs but
does not let the added transfers consume shared network resources. Retain M1's
operation dependencies, lane issue and receive-completion semantics. Original
explicit traffic must have a stated, unchanged treatment in both modes.

Before implementation, specify the congestion-free path/tie-selection rule,
serialization, endpoint and router costs, and what endpoint sharing is removed.
Do not fit static costs to the observed M1 completion times. The comparator
must have analytically or independently checked service semantics and no
double counting. A delay inserted as a CPU-holding calc is not a clean test.

Assess both absolute application-time error and the placement-gap error, plus
critical-chain and common-message changes. A relative error in the small
placement gap can be large while the absolute application error is small;
report both. Define the accuracy needed for the intended design decision
before judging whether static costs are sufficient. No numerical success
threshold, new configuration or static-model run is registered here.

If static costs suffice, retain the simpler method. If they fail, demonstrate
which shared-resource effects explain the failure before adding machinery.
ATLAHS already supports GPU grouping/reorganization; recovering its hidden
transfers is baseline construction, not by itself a novel simulator method.

Only after this mechanism is established should separate controlled axes
examine local-cost sensitivity, mapping, another complete workload and then
physical budgets. Original-configuration and equal-budget comparisons are
distinct. Thermal, PDN, new schedulers and simulator acceleration remain
outside the current work.
