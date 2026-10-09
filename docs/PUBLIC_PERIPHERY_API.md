# Portable periphery compilation, execution and readback

Behavior baseline: `f91824d171917e0e58824b97a1d2a2bff2e4cf51`. This extraction
does not change bank/controller rates, router behavior, transaction dependencies,
window visibility, descriptor/RX assumptions, admission, publication or retirement.
Existing model adapters and execution/storage implementations remain unchanged.
Ordinary periphery operations use the APIs below. Collectives continue through
their existing adapter with rank-local semantics and shared portable regressions.

## Public functions

| Function | Input / responsibility |
|---|---|
| `adapters.periphery_case.compile_case` | Explicit WaferMachine, Workload, Placement, TransactionPolicy, and `bank` or `controller` interface organization; calls existing compilers/lowering |
| `PeripheryCase.to_record` | JSON-ready inventory/target/timing, workload, placement, policy, plans and transaction ledger; optional study capacity upper bound |
| `adapters.periphery_case.case_from_record` | Restore a supplied plan and logical graph; validate physical target/timing consistency; never call an application generator or transaction lowering |
| `execution.timing.execute` | Existing execution API, using the caller's case binding, timing and optional backend |
| `analysis.periphery_input.audit_input` | Independently audit supplied input/events; reject early publication, changed policy work, incomplete execution and inconsistent target/services |

Importing/calling these functions does not consult a server, Git, repository
configuration, an upstream checkout or a native executable. The caller provides
the input. Readback checks physical inventory against the existing machine
compiler; it does **not** regenerate the workload or transaction phases.
Plans remain untrusted input for the independent periphery audit. Restoring
a record alone does not certify its execution or plan semantics.

Explicit objects can be compiled and run as follows:

```python
from wafer_sim.adapters.periphery_case import compile_case
from wafer_sim.adapters.memory_periphery import TransactionPolicy
from wafer_sim.execution.timing import execute
from wafer_sim.analysis.periphery_input import audit_input

# machine, workload and placement are supplied by the caller.
case = compile_case(machine, workload, placement,
                    TransactionPolicy('pipeline', chunk_bytes=4096, window_chunks=4),
                    interface_organization='controller')
record = case.to_record()
result = execute(case.binding, case.compiled.timing)
checked = audit_input(record, result)
```

Without a network argument, `execute` uses the existing analytical whole-message
network. It is a semantic/coarse backend, not Native S, D0 or D1 and not a new
performance reference. Passing a backend remains the existing execute contract;
this API extraction does not validate new backend/policy combinations.
Whole-object staging and ideal_commit_visibility retain their existing limits.

## Portable tests and a supplied-event example

From a checkout, the public suite requires Python 3.11+, NumPy and NetworkX.
It has no native builds, private captures, credentials or server environment
variables. Use an installed package or set `PYTHONPATH=src`:

```bash
python -m pip install numpy networkx
PYTHONPATH=src python scripts/test_public.py
PYTHONPATH=src python -m wafer_sim.cli audit-periphery \
  --input tests/fixtures/public-periphery/controller_pipeline_read-INPUT.json \
  --execution tests/fixtures/public-periphery/controller_pipeline_read-EXECUTION.json \
  --output /tmp/periphery-audit.json
```

The JSON files are small pre-refactor fixtures, not server path references.
Ten periphery cases and one collective compare complete results and individual
event/state sections with pinned f91824d captures. They cover service order,
phase/transfer completion, output availability, capacity/lifetime state, resource
accounting, whole/pipeline, external traffic, consumers and incomplete runs.
A plan-order case preserves declaration order even when JSON keys sort lexically
or the graph's topological order differs.
Another test blocks experiment/server/native imports and process creation in a
fresh interpreter while invoking the public audit CLI on a fictitious hostname.

The full private suite remains `scripts/test_wow_target_remote.py`, with native
fixtures, clean-source checks and a formal same-source receipt. Server locations
and authorization live in `experiments.server`; `remote.py` only preserves old
private imports. Local work in this maintained workspace remains source/Git only,
per AGENTS.md. The portable commands above describe the public interface; this
project's actual verification runs on hn072.

## Saved-study orchestration

`analysis.memory_periphery_study.run(..., repo=...)` reads saved JSON plans and
events and applies source/artifact/measurement checks. It no longer imports
experiment preparation or enforces a hostname. `audit_input` is the smaller
entry with no Git/archive/receipt requirements. Mechanism summary/figure helpers
are likewise separate from their frozen study's private orchestration.

Formal hn072 revalidation uses:

```bash
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.revalidate_periphery \
  --source /Projects/haoning/wafer_simulator/runs/periphery-applications-001 \
  --output /Projects/haoning/wafer_simulator/runs/periphery-revalidation-NEW \
  --tests /Projects/haoning/wafer_simulator/runs/periphery-tests-NEW/SEMANTICS.json
```

The original mechanism campaign now has an orchestration module at
`experiments.periphery_attribution`; its strict frozen-source gate is retained.
Historical reproductions still use their pinned source. The API extraction is
a separate source milestone with behavioral equivalence evidence, not a reason
to relax old campaign gates or rerun already accepted application matrices.
