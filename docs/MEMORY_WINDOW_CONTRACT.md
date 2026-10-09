# Memory-periphery window: ideal commit visibility

This clarifies the unchanged `014130d` transaction policy. It does not insert
events, messages, service delays or a new timing parameter into the old runs.
The configuration name remains `shared_pipeline`; its window feedback assumption
is **ideal_commit_visibility**.

| Question | Current contract |
|---|---|
| What is protected? | Four logical end-to-end fragment positions per transaction |
| Who holds the window? | The execution-policy DAG, with globally visible completion |
| Position acquired | Source fragment service becomes ready, including FCFS waiting |
| Release for read | Destination compute SRAM fragment write completes |
| Release for write | Destination memory bank fragment commit completes |
| Source learns release | Same simulator boundary; zero notification propagation |
| Notification path / messages | None; one read request/command or one final write ack remains |
| Controller-wide descriptor/position limit | Unmodeled; no target hardware budget supplied |
| Staging allocation | Full objects reserved until operation retirement, unchanged |
| Endpoint RX storage and commit-linked credit | Uncertified |

For a read whose endpoints occupy different tiles, chunk j may become source-
ready at exactly chunk j-4's remote SRAM commit cycle. FCFS can delay its actual
start, but the DAG carries no return notification latency. The write source has
the analogous same-boundary visibility of a remote bank commit. A remote
semantic regression records this behavior explicitly; it is not validation of
a realizable control loop.

BookSim router/VC credits describe native flit transport. They do not communicate
the later Python-side SRAM/bank commit to this source window. Whole-object
staging capacity and four positions per transaction do not imply four physical
slots or 16 KiB of storage for the entire controller.

If a future target adopts a source-owned end-to-end outstanding window, it must
define ownership, allocation and release, a completion notification path, its
latency/traffic, and controller-wide descriptor/position budgets. Source reuse
then follows source receipt of the notification, not remote commit alone. A
source-buffer or NIC-resource window may instead release at local handoff or
actual NIC release. These are different contracts; do not add arbitrary per-
fragment acks before choosing one. Any changed policy requires a separate
registered reference, starting with read/write and shared-controller cases.

The whole-to-pipeline comparison changes a combination of policies: service
fragment size, FCFS interleaving, latency instance count, data readiness, stage
overlap and ideal window feedback. A 64 KiB bank access becomes sixteen 4 KiB
services, each with 30-cycle trailing latency (30 versus 480 instance-cycles).
These latency intervals can overlap and cannot be added as application delay.
Control bytes and useful bank/channel bytes remain unchanged; this is not a
pure overlap intervention. External-controller traffic also uses this policy.
Underlying native packets remain one flit; 4 KiB is the DMA fragment size.

Both whole and ideal pipeline remain declared candidates. No principal hardware
contract is selected from their A/B ranking. D1 stays registered under v1 whole,
with no claim for ideal pipeline or any future notification protocol.
