# Does distance lengthen sustained response service without other traffic?

Freeze the accepted 27-cell scaling evidence at `da54cd1`. Do not implement U2,
change hardware or network parameters, change routing, sweep buffer/VC counts,
or rerun applications. This is a component mechanism test on hn072.

Primary comparison: on the same complete 6×6 physical graph, issue one
65,536-byte response from `dram-0-0` to `sram-(6*h)`, for h=0..5 C2C hops.
All routes include one HB link; only the destination/path length changes.
The column path is unique if routing stays minimal. Verify every actual flit
uses exactly the expected HB plus C2C path; never replace it with a guessed path.

All 1,024 payload flits (64 bytes each, one-flit packets as in S) are eligible
at cycle zero. No other requests/messages are submitted. The target graph and
all router, link, VC, credit, packet and endpoint settings are unchanged. This
explicitly begins after response data is available; it neither times a DRAM
transaction nor substitutes for a complete workload. No source-memory supply
or receiving-memory policy is changed in an application.

Matched comparison: isolate the four preregistered 65,536-byte critical responses
from the accepted 4×4/6×6 B runs. Preserve each message's source/destination,
bank, bytes, original eligibility cycle and complete machine graph. Start the
network empty and advance it to that cycle before submission. Compare to the
original concurrent full-work result, without rerunning or truncating that work.
Removing background traffic also removes historical network state. Report this
as the combined background-state effect, not a unique congestion/credit cause.

Ten conditions, two fresh native processes each, one exact command-stream
replay per condition. Require source and binary hashes, same semantic config
(excluding output paths), complete all-flit audit, drained close and repeated
event equality. The old saved execution/config/topology files used in comparison
must match the accepted artifact manifest. Refuse timeout or partial output.

Measure first-flit injection wait, injection span, first/last receive boundaries,
complete-response duration, finite-message byte rate, middle-half injection
rate and inter-flit gap histogram. Record full per-flit path/timing traces.
Do not call the middle-half rate an asymptotic bandwidth measurement.

Also inspect the already saved concurrent runs: count other messages' flits on
each critical directed link during that message's first-to-last link-arrival
window. This establishes temporal sharing rather than merely common routes.
Compare whole-run activity to that window, preserving the distinction between
nominal capacity, momentary activity and effective packet service.

Interpretation is conditional. If isolated injection span/rate worsens with
path length, the single-path pipeline/credit mechanism merits further study.
If it stays stable while matched concurrent responses slow, shared resource and
background-state effects must be retained. Both can occur. First-flit wait=0
does not imply uninterrupted message injection. No outcome is required for
acceptance; do not tune parameters or automatically create another model.
