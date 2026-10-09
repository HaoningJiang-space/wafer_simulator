# Public periphery API extraction: f91824d behavior retained

Machine compilation, transaction lowering, execution and supplied-event audit
can now be called independently of private study/server setup. This is a code
organization milestone, with no new timing model, machine contract or application
performance result. The [API guide](../../PUBLIC_PERIPHERY_API.md) contains the
standalone Python and CLI entries.

## Boundaries

| Public surface | Responsibility |
|---|---|
| `adapters.periphery_case.compile_case` | Explicit machine/work/placement/policy and bank/controller interface choice, using the original compilers |
| `PeripheryCase.to_record`, `case_from_record` | Serialize or restore supplied inputs and plans; preserve declaration order; check physical target consistency |
| `execution.timing.execute` | Unchanged resource admission, dependency, completion and storage lifetime behavior |
| `analysis.periphery_input.audit_input`, `wafer-sim audit-periphery` | Audit given input/events without generating an application, invoking BookSim or reading a server configuration |
| `experiments.server`, `experiments.revalidate_periphery` | Private host/root authorization and formal clean-source/same-source receipt workflow |

The saved-study reader no longer imports experiment `prepare` or a global REPO,
and accepts an explicit repository for provenance checks. It restores saved
plans rather than calling application lowering. Mechanism summary/timeline/plot
functions are separated from frozen study orchestration. Four moved helper
function bodies match their f91824d AST hashes exactly. `remote.py` preserves
historical private imports; current public APIs have no dependency on it.

Readback still uses the physical machine compiler to verify serialized target
and timing consistency. A supplied plan is not presumed correct: periphery
policy audit independently rejects early publication and altered work/dependencies.
No collective policy is imported into ordinary periphery output semantics.

## Verification on hn072

Behavior baseline: `f91824d171917e0e58824b97a1d2a2bff2e4cf51`.
Final tested code: `020f86e720a9363e78f99257fb7766921b0051b6`.

| Check | Result |
|---|---|
| Formal regression suite | **254 passed** |
| Portable suite in a fresh environment | **141 passed**, with only NumPy and NetworkX installed |
| Pre-refactor semantic cases | **10** periphery input/result/audit comparisons plus **1** collective result/audit comparison, including incomplete-run rejection |
| Registered input compatibility | All **15** unique component/application inputs match archived identities; no applications executed |
| Existing Native component readback | **3** bank/shared whole/pipeline read traces; audits, critical chains, transaction completion and summary fields unchanged |
| Frozen implementation / evidence | Execution, architecture, workload, periphery/wafer compilers, policy audit, configs, patches, upstream files and accepted evidence unchanged |

The portable suite overlaps the formal suite; the counts are not additive.
The full 254 comprise the old 239, seven previously separate attribution tests,
six new API regressions and two private server-policy regressions.

The eleven cases were captured **before refactoring**, at clean f91824d, with
independent capture-tool hashes. They cover whole/pipeline, bank/controller NICs,
read/write, remainder/window reuse, concurrent banks, sequential operands,
external supply, a consumer, capacity blocking, lexical plan-key order and
rank-local collective. Complete event/state digests and per-section checks cover
service order, phases/transfer completion, operations, output-ready times,
storage state, resource accounting and peaks. A complete small input/event/audit
fixture is shipped for direct JSON equality/readback.

Fresh-interpreter tests block experiment/server/native imports and process
creation while running the audit CLI with a fictitious hostname and unavailable
private root. The separate fresh environment contains `networkx==3.7` and
`numpy==2.5.3`, runs outside the source directory, and needs neither native
binaries nor private captures. These checks establish independence in the tested
Python/Linux environment; they are not a multi-platform certification.

The existing full suite still exercises its native fixtures. There were **zero
new application executions**, no A/B matrix rerun and no additional BookSim build.
Only three already saved native components were read through the new API. The
six frozen application input identities were checked separately by the private
preparation wrapper; the public event audit does not invoke that preparation.

## Validation history and limits

The first full pass caught a test comparing Python tuple fields directly with
JSON arrays. The test now compares normalized JSON structurally, retaining the
original expectation bytes. A compatibility check then caught a restoration
order error: topological graph order can differ from the original lowering's
operation declaration order. Restoration now uses declaration order, with a
specific regression. Failed/intermediate runs remain on the server; final
receipts refer only to the corrected same-source runs.

Server evidence under `/Projects/haoning/wafer_simulator/runs/`:

- `public-api-baseline-002`: pre-refactor cases and full events; 32 artifact hashes checked.
- `public-api-tests-003`: formal passing suite and native fixture output.
- `public-api-portable-env-001`: minimal environment and package installation log.
- `public-api-check-002`: portable log, input compatibility and native component readback receipt.
- `public-api-helper-identities-001`: unchanged helper-body hashes.

[CHECKED.json](CHECKED.json) records source, binary, input/event, environment and
log hashes; [SEMANTICS.json](SEMANTICS.json) is the same-source formal receipt.
[HELPER_IDENTITIES.json](HELPER_IDENTITIES.json) records helper AST equivalence.
`RUN_COMPLETE.json` is the server verifier's byte-exact receipt, including the
server-only portable log. Large captures and full event collections stay there.

No bank latency, service rate, routing/arbitration, window notification or DMA/RX
budget changes. Both declared contracts and ideal_commit_visibility remain;
D1 is unchanged and its application matrix stays deferred. Behavioral evidence
is scoped to the fixed cases, unchanged registered inputs and original execution
implementation; it does not establish hardware accuracy or new model fidelity.
