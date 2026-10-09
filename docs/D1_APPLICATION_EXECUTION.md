# Completing the registered D1 applications after interface extraction

The controls in `configs/shared_spatial_service.json` and the original
[protocol](SHARED_SPATIAL_SERVICE_PROTOCOL.md) remain unchanged. Run the
27 D0/D1/S cells, three repetitions and 18 native reference replays on hn072.
Reuse `runs/d1-components-001`: 38 cases / 152 executions at pinned `2c4ed6b`,
with all 20 singleton cases exact and the 1,700-condition D0 rule verified.
Read back existing component evidence; do not launch new calibration/probes.

The common v1 frontend now calls the public `compile_case` with explicit
bank interfaces and whole-object policy. Before applications, all 27 input
identities are checked; the 18 D0/S projections and all physical/work/plan
identities must match accepted records. Each result records the explicit
organization, transaction policy, selected model, actual backend and contract
hash. Prediction never reads S application timestamps, overlaps or routes.

Source-byte changes since dc18ed1/2c4ed6b are enumerated, not silently ignored:
only the reviewed geometry/port validation, interface declarations, public
frontend extraction, private import/CLI compatibility and this orchestration's
metadata/provenance changes may differ. Original source bytes are verified in
Git against archived hashes. Network algorithms, timing/storage, workloads,
machine/control configs, native integration/binary and D0 calibration stay
protected. Unknown changes fail the source gate. Completion additionally
requires exact accepted D0/S event hashes at all nine inputs.

The old component registration, cases, machine identities, network contracts,
native configuration semantics, original manifests, audits, message hashes and
singleton durations are rechecked. Reuse is conditional on those checks, not
on merely having an old COMPLETE file. Concurrent component deviations remain
observations of the registered approximation, not calibration adjustments.

Report every layout pair with signed gap error and the original 100-cycle
budget; report 2% application-time passes and global Local/A/B choices/regret.
Correct direction alone is not full acceptance. Separate execution from whole
fresh-worker cost, audits/logging, CPU, parent/child RSS, events/output size,
replay and evidence readback. Original D0 calibration (628.031 s) and D1 component
validation (24.775 s) are one-time costs reported separately from new predictions.
No retuning, shared-pipeline arm, holdout workload or hardware claim belongs here.
