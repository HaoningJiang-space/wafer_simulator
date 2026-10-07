# Fixed-contract execution cost probe

Prepared before running the cost probe. This follows
[memory-service isolation](results/memory-service-isolation-001/REVIEW.md).
It measures implementation cost under one declared target contract; it does
not change the target memory policy to manufacture a simulation speedup.

## Fixed target and evidence boundary

Reuse the accepted s16/s64 `burst_256` descriptors without editing them:
Baseline, row-major, direct-root, TP8, shared memory 32 B/cycle, 256 KiB per
region, 2 TX / 8 RX slots with their 20,000 bytes carved out, and the same
BookSim binary/configuration/seed. Use the bounded boundary reference only.

| Property | Contract | Provenance |
| --- | --- | --- |
| Network paths, latencies, flit size | Accepted WoW export and native network | Pinned author code and prior accepted inputs |
| Memory rate, capacity | 32 B/cycle, 256 KiB per region | Declared analytical resources, not calibrated WoW SRAM |
| Request arbitration | Successive <=256 valid-byte bursts; next burst rejoins FCFS at previous completion | Declared diagnostic policy from the accepted study |
| Outstanding work | One burst per logical request; ordinary and DMA traffic share the port | Existing execution contract |
| Source admission | One DMA message per source through its final injection; reserve TX before reading | Declared endpoint policy |
| Packet eligibility | All valid packet bytes read before injection | Existing boundary implementation |
| Receive feedback | Hold RX and native credit until all valid packet bytes are written | Existing bounded implementation |
| Visibility/lifetime | Full-object commit before publication; existing rank-local outputs and retirement | Accepted storage contract |

The target adapter still states `compute_memory_calibrated=False`. Neither the
256-byte burst nor FIFO sizes are inferred hardware facts. Hardware calibration
is not a prerequisite to testing a simulation transformation under this explicit
contract, but these results cannot establish native WoW prediction accuracy.

## Measurement

For each complete shape run three unprofiled cold processes, then one diagnostic
process with cProfile enabled only inside `execute`. Keep full event/protocol
logging and CPU affinity identical. Existing meters separate graph construction,
initialization, execution, close/serialization, and independent audit. Profile
serialization has a separate phase. Use only unprofiled runs for timing claims;
profiling perturbs execution cost, and profiler wall time includes IPC waits.
Native child CPU is available as a lifetime total, not a per-function attribution.

Require all eight execution records and input identities to equal the accepted
counterparts exactly, with the same native binary. Source/environment and result
hashes are retained in the remote run directory. Profiling is not a new workload,
a truncated run, or another accuracy reference.

Read the profile's self and cumulative times separately. In particular distinguish
calendar operations, admission/lifetime checks, Python/native protocol handling,
blocking I/O and serialization. Do not sum overlapping cumulative times or call
all time spent in a network wrapper native network computation.

## Decision before modifying the execution loop

Only target the measured dominant cost. If calendar events dominate, investigate
combining internal services only over intervals with no competing admission,
callback or external feedback. If conservative cross-process synchronization
dominates, investigate a proved-safe synchronization reduction instead. An empty
application message table alone does not prove the native network is drained:
credits and router state can still be in flight. Preserve native cycle/RNG and
same-cycle ordering unless explicitly validated otherwise.

Any candidate must preserve this memory contract, bytes, service slots, all
output/retirement timestamps and bounded FIFO behavior. Keep detailed records
for comparison; no speedup claim from disabling logs. Compare exact complete
events and native replies, semantic deadline/tie/backpressure tests, then the
same two complete blocks and unprofiled costs. Do not change arbitration,
bandwidth, capacity, workloads, placements or default backend in this stage.

Stop if no justified low-cost transformation is found. A cost diagnosis is not
itself a new simulator model. No optimization or new result is claimed by this
registration.

## Candidate selected after profiling

The accepted diagnostic run `memory-execution-cost-001` found repeated
`StorageState.admission` / reservation checks dominating Python execution, not
the calendar's burst arithmetic. The first candidate therefore only suppresses
admission scans when their inputs have not changed. Initial admission remains
mandatory; publication and retirement mark it dirty. Retirement matters even
without output because it can free capacity or satisfy a control dependency.
Partial memory/packet progress cannot change any of these admission inputs.

Keep stable topological order, earliest dependency-ready timestamps, every
service event, and every native command/reply. No batching or network clock
shortcut is introduced. The same cost probe is repeated on the candidate,
with all complete records required to equal the old accepted runs. Regression
checks include retirement-only capacity release, independent completions during
long burst sequences, same-cycle/deadline behavior and rank-local publication.
This is an implementation optimization under the fixed model, not evidence of
a new approximation or calibrated hardware accuracy.

## Run on eex005

After a clean commit and same-source semantic tests:

```sh
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python \
  scripts/profile_memory_execution_remote.py \
  /home/wangziheng/wafer_simulator/runs/memory-execution-cost-001 \
  --tests /ABSOLUTE/SAME-SOURCE-TESTS/SEMANTICS.json
```

The output must be a new absolute path. Raw profiles and event tables remain on
eex005. The Git repository receives compact checked summaries only.
