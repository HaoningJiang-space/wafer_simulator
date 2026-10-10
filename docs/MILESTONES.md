# Evidence index and milestone status

Historical protocols describe their own scope; they are not parallel current
roadmaps. All accepted reports/hashes remain. Current entry and objective are
in [README](../README.md) and [RESEARCH_DIRECTION](RESEARCH_DIRECTION.md).

| Area | Status | Accepted evidence / scope |
|---|---|---|
| G1 causal closure | Independent bounded component gate complete; G2 deferred | [Seven cases, 14 complete Native runs, 13 regressions and seven negative probes](results/causal-closure-001/REVIEW.md); 10,787 flits, 97,083 local service clocks, 112,695 allocation calls and full credit/message/drain sequences exact without Native internal inputs; zero applications or compression claims |
| Local service reconstruction | Conditional local gate complete; independent network gate not implemented | [Six Native component observations, 13 regressions and four negative probes](results/local-service-001/REVIEW.md); full reference events/protocols exact; multi-input VC contention, zero multi-input switch requests; 36,864 service-clock and 22,506 eligibility/pointer comparisons exact given observed arrivals/credit returns; zero new applications |
| Source order / local merge | Saved-data diagnosis and source-only probe complete; component gate not passed | [60 artifact checks, 16 component / 18 application records, four remote tests and four Python probes](results/source-order-001/REVIEW.md); common-source final times restored but source boundary +60 cycles; distinct-source merge unchanged; 69 critical S messages with zero generation wait, local merging on B critical paths; zero new native/application runs |
| Detailed S cost profile | Two-input diagnosis complete; no acceleration implemented | [Four controlled profiles and two negative audit probes](results/native-service-profile-001/REVIEW.md); complete events/protocols exact at 6×6/7×7 B, affinity matched; native Steps and recording/JSON/audit all cost time; five exploratory profiles preserved and excluded |
| Public periphery compilation / event audit | Complete under f91824d behavior | [254 formal / 141 portable tests](results/public-periphery-api-001/REVIEW.md); 11 pre-refactor event/state cases, 15 unchanged registered inputs and three old Native readbacks; private receipt/server policy separated; zero new application executions |
| Periphery acceptance and actual interface ports | Repaired; original evidence revalidated | [239 regressions and 27 saved executions](results/memory-periphery-audit-fix-001/REVIEW.md); tables/counts unchanged, zero new application simulations; independent plan publication, semantic summary checks and final NIC port counting |
| Periphery critical chain and DMA contract | Existing-trace analysis complete; hardware budgets unavailable | [18 traces and seven analysis regressions](results/memory-periphery-attribution-001/INTERPRETATION.md); earlier supply and changing chain exposure; [ideal commit visibility](MEMORY_WINDOW_CONTRACT.md) explicitly retained, no physical DMA/RX certification or principal-machine selection |
| Memory-periphery organization/policy | Complete under declared assumptions | [Six 6×6 A/B cells, 18 applications, nine components, 15 replays](results/memory-periphery-001/REVIEW.md); shared-interface whole matches v1, bounded pipeline changes A/B preference; 228 tests; no hardware calibration |
| Shared spatial service D1 | Complete fixed v1 experiment; partial accuracy result | [81 applications, 18 replays, 256 tests](results/shared-spatial-service-001/REVIEW.md); 152 component readbacks, frozen D0/S events exact; all pair directions restored, MAPE 1.201%, 8/9 application and 0/9 gap budgets pass; 8.03–13.81× recurring whole-worker speedup, prior calibration separate |
| Independent spatial service D0 | Complete under v1 policy | [1,700 component conditions and 81 U1/D0/S applications](results/independent-spatial-service-001/REVIEW.md); Local timing/global choice recovered, but A/B direction still wrong at 6×6/7×7; 100-cycle gap budget fails |
| Long-response mechanism discrimination | Complete; no U2 or kernel change | [20 isolated responses, 10 native replays](results/isolated-response-001/REVIEW.md); constant isolated injection span across 0–5 C2C hops, temporally shared critical outputs with workload background |
| Spatial scaling / locality–load tradeoff | Complete; models frozen | [27 cells, 81 executions, three array sizes](results/spatial-scaling-001/REVIEW.md); U1 misses the A–B decision at 6×6/7×7; zero staging-capacity waits |
| Runtime relocation to hn072 | Complete; old evidence cold-archived | [Verified archive and cleanup](results/server-migration-001/REVIEW.md); 50,072 entries verified, 26.5 GB observed free-space increase; current native binary unchanged |
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
