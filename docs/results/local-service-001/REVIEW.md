# Local service reconstruction: VC ownership precedes switch service

The bounded study is complete on `hn072` (`ee4e072`). At the selected output
24→36, the overlapping three-flow cases contend in **VC allocation**. The
single output VC then filters access to switch allocation: no recorded switch
allocation call contains multiple requesting inputs. Describing the observed
2:1 flow counts as simultaneous input-fair switch arbitration misses this
service boundary.

Given actual local input arrivals and processed downstream credit returns, a
small local state machine reconstructs request eligibility, allocator pointers
and all four service clocks exactly for offsets 0, 509 and 3,000. It does not
receive Native eligibility or service clocks as prediction inputs. It still
receives the surrounding network's arrival and credit-return boundaries, so
this is conditional reconstruction, not an independent network backend or an
application accuracy result.

## Fixed inputs and behavior preservation

S, D0, D1, physical rates, routing configuration, v1 whole-object execution,
accepted events and the 100-cycle design-gap budget remain unchanged. No new
application execution, full backend, parameter fit or fairness weight was added.

Two isolated observation builds each ran the same three accepted components.
All six runs preserve the complete Native messages/flits, input identity,
protocol bytes and final drain record. This includes source generation,
first/last injection and first/last ejection clocks. The accepted S executable
is unchanged. Upstream files in `third_party/` were not edited: reviewed patches
were applied to isolated server build copies.

The first build records VC/switch requests, pointers, grants, ownership,
occupancy, commits and output sends. The second adds processed credit returns
and declared pipeline/channel timing. Both observe only router 24's output to
router 36. The observer reads service state and writes a separate sidecar; it
does not change the Native protocol or move its existing observation phase.

## What actually competed

The following counts are independently recomputed in [RESULTS.json](RESULTS.json).
A multi-request call has more than one requesting input for this output.
An owned/no-request VC call has no request while the output VC is unavailable.

| Ready offset | VC calls | Multi-input VC calls | Owned/no-request VC calls | Switch calls | Multi-input switch calls |
|---:|---:|---:|---:|---:|---:|
| 0 | 5,099 | 2,026 | 2,027 | 3,072 | 0 |
| 509 | 5,119 | 2,047 | 2,047 | 3,072 | 0 |
| 3,000 | 3,072 | 0 | 0 | 3,072 | 0 |

The pinned router runs single VC, non-speculative allocation, speedups one,
one-iteration iSLIP, VC/switch delays one and single-flit packets. A VC grant
makes its input active; switch service is eligible on the following cycle.
Sending the tail releases VC ownership with `wait_for_tail_credit=0` while
consuming a downstream credit. Ownership and credit capacity are separate
states. New VC allocation cannot bypass the current owner simply because
another input already has queued data.

Across all observed switch calls, credit is available; the minimum remaining
credit count is 13. Thus this particular output's switch service never waits
for a full downstream buffer in these components. This does not establish that
credits, upstream blocking or downstream state are irrelevant elsewhere.
Observed input queue peaks for upstream routers 12/25 are 23/31 at offsets
0 and 509, and 1/1 at offset 3,000. These are measured occupancies, not a
certified minimum hardware buffering budget.

## Curves and the scope of the 2:1 observation

The five curve pairs are regenerated from accepted traces, with fixed
128-cycle windows and absolute Native clocks. Curves show output **sink
arrivals**, not grants. They include all traffic on each selected output and
carry cumulative plateaus through the full plotted interval.

| Saved case | Selected output | Output flits | Curve |
|---|---|---:|---|
| Three-flow offset 0 | 24→36 | 3,072 | [PNG](curves/three-shared-stagger-0/output.png), [SVG](curves/three-shared-stagger-0/output.svg) |
| Three-flow offset 509 | 24→36 | 3,072 | [PNG](curves/three-shared-stagger-509/output.png), [SVG](curves/three-shared-stagger-509/output.svg) |
| Three-flow offset 3,000 | 24→36 | 3,072 | [PNG](curves/three-shared-stagger-3000/output.png), [SVG](curves/three-shared-stagger-3000/output.svg) |
| 6×6 B critical output | 46→34 | 6,962 | [PNG](curves/6-B-critical-output/output.png), [SVG](curves/6-B-critical-output/output.svg) |
| 7×7 B critical output | 56→42 | 6,929 | [PNG](curves/7-B-critical-output/output.png), [SVG](curves/7-B-critical-output/output.svg) |

Offsets 0 and 509 each have 31 complete windows inside the intersection of
both input branches' first-to-last sink-arrival spans. Every such window
contains 32 flits from router 12 and 32 from router 25; consecutive outputs
inside that intersection alternate input identity. Offset 3,000 has no
intersection. Two flows share router 12's FIFO, accounting for its branch's
work division. This is consistent with the measured VC request/pointer/grant
sequence; it is not a fitted universal input-fair capacity rule. A branch's
first-to-last span alone does not prove continuous eligibility.

The B curves show both steady output and periods of changed/slower service,
particularly at 7×7. They were reconstructed without new application runs.
No application eligibility/credit observer was run, so their irregular periods
cannot be assigned to a particular queue, VC or credit cause. This study does
not allocate the D1 application-gap error to these mechanisms.

## Two levels of local reconstruction

First, a one-output iSLIP replay receives actual requests and advances its own
pointer, comparing grants and pointers separately for VC and switch. All three
components match. Cross-output accept competition is rejected rather than
silently supplied from Native. This layer verifies the allocator operator
conditional on observed eligibility.

Second, [local_service_state.py](../../../src/wafer_sim/analysis/local_service_state.py)
receives only local flit arrival identities/times, processed credit returns and
the declared contract. It maintains per-input FIFO heads, one output-VC owner,
credit balance, separate VC/switch pointers and pending crossbar sends. It
computes eligibility and service without reading observed requests or grants.

| Offset | Flits / four clocks each | Allocation calls checked | Boundary / eligibility / pointer mismatches |
|---:|---:|---:|---:|
| 0 | 3,072 / 12,288 | 8,171 | 0 / 0 / 0 |
| 509 | 3,072 / 12,288 | 8,191 | 0 / 0 / 0 |
| 3,000 | 3,072 / 12,288 | 6,144 | 0 / 0 / 0 |
| Total | 9,216 / 36,864 | 22,506 | 0 / 0 / 0 |

The four clocks are VC commit, switch commit, output send and downstream sink
arrival. The local pipeline uses the declared crossbar delay 2 and channel
latency 17. Sink arrival is send + 17 + 1 under the existing native read/write
observation phases; that extra boundary is retained, not fitted to message
completion. This supported domain also requires routing delay zero,
`vc_busy_when_full=false` and the declared unbounded output buffer. It is not
a general router model or evidence that all retained state is globally minimal.

The event loop skips empty/blocked intervals, but only 18 cycles in each busy
overlap case versus 1,838 in the separated case. It still handles each flit;
no useful busy-service compression, runtime speedup or algorithm novelty is
established. The earlier common-source 60-cycle release discrepancy is not
closed: source release and complete-message prediction remain outside this
conditional local model.

## Acceptance and provenance

[TESTS.json](TESTS.json) records 13 remote regressions, including FIFO order,
VC ownership, distinct pipeline boundaries and supplied-credit blocking/drain.
The earlier seven-test run is contained in this set and is not added to it.
[NEGATIVE_PROBES.json](NEGATIVE_PROBES.json) records four additional real-data
faults rejected: missing credit return, missing switch commit, an incorrect
but internally consistent stored boundary table, and one wrong Native grant.
These probes are not counted as additional suite tests.

[VERIFIED.json](VERIFIED.json) records a fresh independent readback at
`343df8094a7630b49af7e8e22b3bbb0cedda50dd`: 59 observation artifacts,
26 reconstruction artifacts and nine accepted reference artifacts checked.
The reader rebuilds comparison boundaries from raw flits plus the sidecar;
it does not trust `BOUNDARIES.json` or summary metrics. It recomputes both
replays, eligibility, pointers and service clocks before accepting them.

The second observation and 13-test suite used
`a0b3b320eccc138ca9ad67c08afd5b562c622c99`; the first used
`7a8f6c14175cf32cab0740cef72ede7970c0fb0b`. Binary identities are:

- Accepted S: `d37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb`.
- First observer: `a57e62ca6f7ef9ae5df9b504bcf4400d924369ffacc095bc1cc8416f40c41d80`.
- Second observer: `d55bc6e86d0197168ab14da54ef9b840aac458dc1d2b1279c8b79e8bed2ab51e`.

[OBSERVATION_STARTED.json](OBSERVATION_STARTED.json) pins source files,
compiler, Python, packages, affinity, input manifest and test identity.
[OBSERVATION_COMPLETE.json](OBSERVATION_COMPLETE.json) and
[CURVES_COMPLETE.json](CURVES_COMPLETE.json) pin the server artifacts.
[PUBLISHED_COPIES.json](PUBLISHED_COPIES.json) verifies every copied receipt,
plot and window CSV byte-for-byte against its server source. Large sidecars,
event tables, builds and raw network records remain on hn072 under
`/Projects/haoning/wafer_simulator/{runs,build}`.

The raw second `SUMMARY.json` has an outdated aggregate sentence saying that
eligibility is supplied by Native. It is preserved as
[OBSERVATION_SUMMARY.json](OBSERVATION_SUMMARY.json). Typed per-case flags and
the independently recomputed result distinguish the two replay layers. A later
writer edit corrects only that scope sentence; the readback accepts exactly
that normalized source change, retaining checks on all observer/model bytes.
Original events, summaries and receipts have not been rewritten.

## Reproduction and decision

The [protocol](../../LOCAL_SERVICE_RECONSTRUCTION.md) lists tests, isolated
build and component entry points. Use fresh output/build directories and
same-source receipts; do not overwrite the accepted campaigns. Current-main
readback of the archived second campaign requires no new Native execution:

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.local_service_study \
  /Projects/haoning/wafer_simulator/runs/local-service-components-002 \
  /Projects/haoning/wafer_simulator/runs/local-service-reconstruction-002 \
  /Projects/haoning/wafer_simulator/runs/d1-components-001 \
  docs/results/shared-spatial-service-001/VERIFIED.json \
  /Projects/haoning/wafer_simulator/runs/local-service-readback-NEW
```

This closes conditional local-service reconstruction. The result supports
retaining input FIFO identity, VC ownership and phase boundaries before
compressing repeated service. It does not prove an independent network,
100-cycle application-gap recovery, physical hardware accuracy or a new
simulation algorithm. A next bounded method experiment would need to generate
surrounding arrivals and feedback independently, or test compression of these
established local transitions. Neither is implemented or automatically started
by this milestone; no application matrix or D2 follows from this receipt.
