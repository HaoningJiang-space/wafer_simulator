# Local service reconstruction: bounded protocol and unexecuted preparation

**Status: registered preparation; execution requires checked receipts.** The
temporary local network/Git restriction was removed before execution. Credentials
remain outside this project. This protocol itself is not a build, test, native
equivalence or model-accuracy receipt. Read-only patch applicability checks are
source inspection, not native validation.

## Question and fixed scope

Does local input identity plus actual service eligibility explain the native
three-flow behavior that end-to-end equal-flow sharing misses? Keep S, D0, D1,
whole-object v1 inputs, physical rates and the 100-cycle gap criterion unchanged.
This protocol creates no application backend and runs no application.

1. Read accepted native `three-shared-stagger-0/509/3000` repetition-zero events.
   Reconstruct input arrivals and cumulative output **sink arrivals** at 24→36,
   with fixed 128-cycle count windows. Also read the 6 B output 46→34 and 7 B
   output 56→42, marking `first17/phase/4` and `first21/phase/4` spans. Plot the
   full selected output, not only target flits. Existing native grants/credits
   are not inferred from channel observations.
2. Build an isolated observation binary using pinned upstream ordinary files,
   the accepted wafer patch and the new observation patches. Observe only
   router 24's output to router 36, for the same three small components.
   Preserve the accepted binary and original event files.
3. Replay a one-output iSLIP operator against actual local requests. Begin its
   pointer at zero from the pinned constructor and advance independently. Compare
   grants and pointers at every allocation call, separately for VC and switch.
   Reject cross-output accept competition instead of feeding observed accept
   decisions back into the replay. This is **conditional diagnosis**, not
   independent arrival, feedback, source-release or message-completion prediction.
4. A second observation build adds processed credit returns. A bounded local
   state replay receives actual input arrivals and actual credit returns, then
   computes FIFO heads, VC ownership, credit balance, eligibility, pointers and
   pipeline boundaries itself. Native requests/service clocks are comparison
   targets only. Surrounding network boundaries remain externally supplied.

## Source finding: observe VC allocation as well as switch allocation

The native defaults specify iSLIP for **both** VC and switch allocation. Under
single VC, non-speculative operation, `_VCAllocEvaluate()` first checks output
VC ownership (`IsAvailableFor`) before submitting a request. `_VCAllocUpdate()`
takes that VC and makes the input active. Only then can it enter switch allocation.
`BufferState::SendingFlit()` releases ownership on a tail when
`wait_for_tail_credit=0`; it also increments downstream buffer occupancy. Returned
credit reduces that occupancy separately.

Thus VC ownership and credit capacity are distinct. A busy output VC can prevent
an input from reaching switch competition; an active owner may legally have
`vc_available=false`. Do not interpret that flag as a universal switch
ineligibility test. With one output VC, the observed two-branch alternation may
already be chosen in VC allocation, leaving little switch-level competition.
This is a source-supported possibility, not a new trace result.

The observation draft therefore records:

- VC and switch pre/post request snapshots, actual input-port IDs, upstream
  router identity, round-robin pointer and raw allocator match;
- head flit/message, queue occupancy, VC state, target route membership and
  whether a fresh VC/switch evaluation is pending;
- output VC owner/availability, credit slots/fullness and output-buffer occupancy;
- successful VC commit, switch commit and output-channel send per flit.
- processed credit returns and declared pipeline/channel delays (second build).

An upstream router ID such as 12 is not the router-local input-port index.
The recorded attachment links these identities. Existing full channel traces
supply local input arrival and downstream sink arrival. All clocks retain the
native observation phase; no existing channel scan or `_Step()` is moved.

## Gates and limits

The observer supports one VC, speedups one, one-iteration iSLIP, VC/switch delays
one, no speculative allocation and no held switch. It rejects unsupported
contracts. Its getters and sidecar writes do not set network service state.
That design intent requires empirical equivalence before acceptance.

**Equivalence gate:** for all three components, the observation run must match
the accepted input, every message/flit record, native protocol and final drain
record. This includes generated, first/last injection and first/last ejection
clocks. A missing close, timeout, partial sidecar or unmatched observed flit fails.
No valid event identity is repaired by changing a reference or stripping fields.

**Conditional service gate:** reproduce the independent pointer trajectory and
grants for both stages, or report mismatches/unsupported accept competition.
Distinguish raw allocation match, successful state update, channel send and sink
arrival. Window counts are descriptive; they do not establish a new fairness
coefficient, permanent queue occupancy or available bandwidth.

**Independent model gate:** not implemented. Correct conditional replay alone
does not establish independently predicted source release, upstream arrivals,
downstream eligibility or whole-message completion. In particular it does not
close the common-source 60-cycle boundary cancellation. New independent service
work should proceed only after the conditional evidence is read and checked.
There is no automatic transition from this campaign to the application matrix.

## Prepared entry points (hn072 only)

Commit the preparation on `main` and synchronize it before running. Then use
fresh directories, leaving old artifacts untouched:

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_local_service_remote.py \
  /Projects/haoning/wafer_simulator/runs/local-service-tests-001
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.local_service \
  /Projects/haoning/wafer_simulator/runs/d1-components-001 \
  /Projects/haoning/wafer_simulator/runs/d1-applications-001 \
  docs/results/shared-spatial-service-001/VERIFIED.json \
  /Projects/haoning/wafer_simulator/runs/local-service-reconstruction-001
bash scripts/build_local_service_remote.sh \
  /Projects/haoning/wafer_simulator/build/booksim-local-service-001
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.local_service \
  --output /Projects/haoning/wafer_simulator/runs/local-service-components-001 \
  --binary /Projects/haoning/wafer_simulator/build/booksim-local-service-001/online_booksim \
  --tests /Projects/haoning/wafer_simulator/runs/local-service-tests-001/TESTS.json
```

The reconstruction produces five curve pairs and fixed-window tables from old
data. Event tables and sidecars stay on the experiment server. Native observations
run only the three registered small components. Source/binary/input/environment
and output hashes, same-source tests, compiler identity and original binary
immutability are required. New plots must be visually inspected after generation.
No speedup, hardware calibration, algorithm novelty or application accuracy is
claimed by this preparation.
