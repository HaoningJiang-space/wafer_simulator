# Collective source facts and target completion contract

Every CPU collective in the complete 16-rank Chakra source now has explicit
input/output roles and logical bytes. Calls with source-backed communicator
identity can be matched across ranks. A separate target adapter maps supported
logical collectives to memory, network and reduction demands with finite storage
and explicit completion conditions. This does not yet lower the whole capture
or produce a new application time.

The [complete independent raw readback](VALIDATED.json) used source commit
`2360c9064d121fd65b4c4e5803818cfeab8f3615`. It read all 4,530,939 nodes, retaining
counts of all 4,530,939 parent entries and 5,258,091 data-dependency entries.
The [summary](SUMMARY.json) reports:

| Quantity | Count |
|---|---:|
| CPU collective calls with recovered operand roles and bytes | 33,632 |
| Calls with explicit group/communication-sequence identity and matching source wait | 3,840 |
| Matched collective instances | 2,790 |
| Instances with supported logical semantics | 2,766 |
| Matched instances whose reduction operator remains unresolved | 24 |
| Coalesced calls without sufficient communication identity | 29,792 |
| Attached GPU collective records | 6,496 |
| GPU records whose `comm_size` differs from logical input bytes | 6,272 |
| Parser errors / unowned GPU collective records | 0 / 0 |

Call counts are per rank; instance counts combine participants. The 2,766
supported instances consist of 20 sixteen-rank allgathers, 20 sixteen-rank
barriers, 6 sixteen-rank allreduces, 1,120 singleton allreduces and 1,600 singleton
broadcasts. Thus **2,720 are singleton operations**; the total is not evidence
that the capture's large training collectives are already resolved.

The 29,792 coalesced calls have tensor roles and volumes but lack a source-backed
group/communication-sequence pair. A tensor ratio indicating 16 participants
does not select a communicator or match corresponding calls. They remain
unresolved, not dropped or paired by timestamp/order. Logical records retain
call IDs, tensor argument ports, attached GPU IDs and matching source wait IDs.

Two concrete decoding distinctions matter. First, a coalesced call's returned
Work object is not the output tensor; output buffers are among input arguments.
Second, a WorkNCCL wait's final placeholder `1` is not its communicator size.
The normalizer also separates logical input bytes from Chakra's sum over source
input descriptors. These distinctions are checked against raw records and
the [pinned author references](../../COLLECTIVES.md).

## Target resource and completion validation

The [101 semantic regressions](tests.log) passed on eex005 at
`ddb249e` ([receipt](SEMANTICS.json)). That commit only refines target rank-local
completion; source-normalization and raw-check code is unchanged from the
full-source run above. No duplicate full normalization run was needed.

The explicit direct-exchange/rank-order-SUM policy produces memory byte demands,
network transfers and scalar additions. Tests independently check volumes,
target reachability, co-location, shared finite capacity, atomic admission,
destination write completion and staging lifetime. Rank-local wait completion
is distinct from global collective termination, avoiding an added global barrier.
These are semantic regressions, not reduced application experiments.

Target storage currently requires distinct immutable input/output versions and
holds staging until global completion. Source aliasing, allocation epochs and
exact layout still need binding. Barrier has a rendezvous condition but no
timed control-message protocol. No calibrated target rates or full application
scheduler is supplied by this milestone. See the [contract](../../COLLECTIVES.md).

## Evidence and remaining integration

Full artifacts (93 MiB) stay on eex005 at
`/home/wangziheng/wafer_simulator/runs/collective-source-003`.
`VALIDATED.json` records hashes of every rank ledger, match table and
`LOGICAL.json`. [STARTED.json](STARTED.json) records the source interpreter,
packages and accepted source-support identity. Original raw input identities
remain in `runs/chakra-source-003/DECODED.json` and `SOURCE_SUPPORT.json`.
The same-configuration Chakra capture is not established to be the accepted
GOAL capture, so this is not another M0/M1 timing comparison.

The first processing attempt failed a tuple/list shape comparison during
independent readback. A subsequent attempt exposed the wait-placeholder
misinterpretation. Their logs and superseded artifacts remain on the server;
`collective-source-003` is the accepted result. The checked source files and
their original notices are committed inside `wafer_simulator`, without changing
the author implementation in place.

Next, recover the missing coalesced identities where the source permits, and
bind original collective ports to explicit tensor versions and call ownership.
This is required before these demands can enter complete target execution.
No new BookSim run or placement experiment was launched. The frozen 006 binary
and native patch retain SHA-256
`9807d4a81c07e29bf1f40dec11fbc9dad9f64d66319c6dbdd5103c04b4256255`
and `2e44498b90fd5f06c6ff58a09141d38c6dd1979d477a6d7fcb93118ff9f40344`.
