# Evidence index and milestone status

Historical protocols describe their own scope; they are not parallel current
roadmaps. All accepted reports/hashes remain. Current entry and objective are
in [README](../README.md) and [RESEARCH_DIRECTION](RESEARCH_DIRECTION.md).

| Area | Status | Accepted evidence / scope |
|---|---|---|
| Spatial storage abstraction U0/U1/S | Complete; machine and execution kernel frozen | [9 cells, 54 executions, layout-selection error and cost](results/memory-abstraction-001/REVIEW.md); aggregate communication misses the 3,193-cycle near/remote gap |
| Independent compute/memory wafer machine | First integration accepted; numerical resources uncalibrated | [Physical legality, transactions and three complete same-work cases](results/wafer-machine-001/REVIEW.md); original execution kernel and LoI evidence retained |
| Independent groups sharing one WoW | Complete; models remain frozen | [12-cell solo/joint coverage](results/group-sharing-001/REVIEW.md); actual path sharing, no final slowdown, +48-cycle joint gap error |
| Boundary design-gain prediction | Complete; enhancement closed | [24-cell result and model selection](results/boundary-design-001/model_selection.md); kernel frozen |
| Boundary model selection | Complete | [Objective-specific errors and reduction reconvergence](results/boundary-model-selection-001/REVIEW.md) |
| Memory-service policy isolation | Complete | [36 runs, two target policies](results/memory-service-isolation-001/REVIEW.md) |
| Memory/network boundary | Complete | [Streaming contract, occupancy and message evidence](results/memory-boundary-001/REVIEW.md) |
| Exact runtime optimization | Closed | [Preserved events; admission-check reduction](results/memory-execution-cost-001/REVIEW.md) |
| Network approximation | Closed, optional models retained | [Matched transfer study](results/transfer-granularity-001/REVIEW.md), [packet pipeline](results/packet-pipeline-001/REVIEW.md) |
| Tree and placement studies | Frozen validation cases | [Tree spatial](results/tree-spatial-001/REVIEW.md), [rank-local/balance](results/rank-local-balance-001/REVIEW.md) |
| Collective timed execution | Complete | [Action DAG and corrected result materialization](results/collective-execution-001/REVIEW.md) |
| Initial Transformer/WoW pair | Superseded lowering, evidence retained | [Original pair with correction](results/transformer-wow-001/REVIEW.md) |
| Target timing and logical block | Complete foundation | [Timed execution](results/timed-execution-001/REVIEW.md), [Transformer](results/transformer-execution-001/REVIEW.md) |
| Full GOAL fixed-local replay and M0/M1 | Complete conditional evidence | [006](results/llama16-006/REVIEW.md), [model boundary](results/model-boundary-001/REVIEW.md); missing original WoW capture is not reconstructed |
| Full-capture static-cost Mstatic | Deferred separate question | [Historical protocol](MODEL_BOUNDARY_PROTOCOL.md); not a gate to current work |
| Chakra recovery | Frozen, incomplete semantic input | [Source check](results/chakra-normalization-001/REVIEW.md), [latest recovery](results/collective-recovery-001/REVIEW.md) |
| Source delivery / server cleanup | Complete, evidence retained | [Pinned files](EXTERNAL_SOURCES.md), [cleanup receipt](results/remote-cleanup-001/REVIEW.md) |

Do not call historical conditional replay calibrated native wafer timing; do not
turn old pending instructions into new experiments without a current objective.
