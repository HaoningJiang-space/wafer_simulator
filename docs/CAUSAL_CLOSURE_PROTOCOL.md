# G1: independent causal closure on a bounded merge network

Status: registered implementation, not an accuracy receipt. This experiment
composes the established local single-VC transitions before testing compression.
S/D0/D1, all accepted events and wafer application controls remain unchanged.
No application or G2 performance experiment is authorized by this protocol.

The explicit [contract and seven cases](../configs/causal_closure.json) use four
routers: endpoints 0/1 enter router 0, endpoint 2 enters router 1; both feed
router 2, which feeds router 3 and receiver endpoint 3. Reverse credit channels
are explicit counterparts of every link. The tree has unique routes. This is
a network component, not a new physically qualified wafer organization.

The primary contract retains 64-byte single-flit packets, one private 32-flit
VC, iSLIP once, non-speculative allocation, speedups one, allocation delays
one, crossbar delay two, zero routing/credit-processing delays and
wait_for_tail_credit=0. Router links use 17 cycles; endpoint links one.
A separately labelled two-flit-capacity diagnostic exercises real credit
blocking. It does not replace or fit the primary 32-flit contract.

Cases: one flit, one long response, three long flows with ready offsets
0/509/3,000, queued same-source messages, and the tight-credit diagnostic.
Only external message ready/source/destination/flit counts and declared
contract enter the independent predictor. Persist its result before launching
Native. Native input arrivals, eligibility, grants or credit timestamps may be
used only by the comparator afterwards. There is no calibration from finishes.

All internal data arrivals must come from predicted upstream service/channel
progress; all internal credits from predicted downstream buffer release or
endpoint consumption. Source generation, injection and drainage are also
predicted. Preserve the Native Evaluate-before-Update boundaries and return
credit propagation; do not release VC early in the same allocation cycle.

For each case run the unchanged accepted S binary, then an isolated observation
build on the identical input/configuration. The observer must preserve full
Native messages/flits, protocol and final drain. It observes all four forward
outputs, including receiver ejection, without modifying service state. Upstream
patches are applied only in isolated build copies, never in third_party.

G1 compares every flit's generated/injected/ejected, first router arrival,
router path and link arrivals; message generation/first-last injection/
first-last ejection/finish; local VC/switch commits/output sends; processed
credits and sent credits at all four routers and the source endpoints; and
observed allocation requests, pointers, ownership, credits, FIFO heads and
occupancy. Missing events, capacity violations, incomplete drainage or timeout
fail. Store counts and first discrepancies, not only final durations.

Build/test/run on hn072 under /Projects/haoning/wafer_simulator with clean main,
same-source test/build receipts, full source/binary/input/environment/output
hashes and fresh directories. Keep traces/sidecars/builds on the server; publish
compact checked receipts. Accepted S executable bytes and old evidence remain.
A completion receipt means the execution/analysis finished; a separate accuracy
boolean must report whether G1 passed, including a completed negative result.

This candidate handles only the registered tree, forward traffic, one VC,
single-flit packets and no competing other outputs. It makes no general NoC,
wafer hardware, application-gap, speedup or novelty claim. G2 is deferred even
if G1 succeeds. A failure is localized to its earliest boundary, with fixes
required to follow pinned service semantics rather than tuned rates or delays.
