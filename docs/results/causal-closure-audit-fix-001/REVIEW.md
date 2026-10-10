# G1 audit repairs and unchanged accepted results

The stricter comparator accepts all seven saved G1 cases. No Native build or
execution was repeated, and no predictor, contract, client or observation patch
changed. The new independently regenerated `RESULTS.json` has the identical
SHA-256 `15ff25e4c359200e74bde67d3dc2b89c2e1a617a53ea6adbf76b8b34adfb9ae3`
as the [original accepted results](../causal-closure-001/REVIEW.md).

Validation was run on `hn072@143.89.78.72` / `ee4e072`, source
`ad752f33cfdc81db7eb72352b3c56b6360ee0a94`. This is an audit repair receipt,
not a new G1 experiment, G2 result, application test or performance claim.

| Check | Result |
|---|---|
| Targeted semantic and audit regressions | 29 passed, including the original 13 |
| Saved cases independently regenerated and re-compared | 7/7 passed |
| Authenticated campaign artifacts | 156 |
| Real-data fault injections | 19 rejected |
| New Native executions | 0 |
| Accepted event files and comparison results | Unchanged |

## Repairs

Predicted service and allocation identities are checked for multiplicity before
dictionary indexing. The same protection covers predicted message/flit IDs.
Schema-3 observation records have a closed event/field set, strict integer and
boolean types, port identities, allocation stages and markers. Repeated JSON
keys are rejected during parsing. These checks also apply to in-memory records
passed directly to the comparator, so a consistent footer cannot hide an
unknown event or repeated begin/end.

The [formal protocol](../../CAUSAL_CLOSURE_PROTOCOL.md) now explicitly includes
real-data negative checks after successful independent readback **and** G1
accuracy acceptance. The script requires that receipt, authenticates its result
and comparator identity, and first verifies that unmodified evidence passes.
Its receipt is separate from unit tests and Native run counts.

Readback normally still requires all archived source hashes to match. The
explicit `--audit-revision` option permits only the exact published `b150be7`
comparator to be replaced. Its old SHA is checked against pinned Git source;
every simulation/observation/input source remains byte-pinned. The
[new receipt](VERIFIED.json) records old and new auditor identities.

## Regression and failure coverage

[Negative probes](NEGATIVE_PROBES.json) include the original seven faults plus
duplicate predicted services, allocations, messages and flits; unknown events
and repeated markers with consistent footer counts; missing/extra fields;
invalid booleans/stages; and duplicate observed input IDs. The 19 total includes
the previous seven; it is not 19 additional checks.

The first repair source `0c64e53` passed 28 targeted tests, but its readback
failed because a contract-loop variable shadowed the predicted service index.
This newly introduced comparator error was corrected in `ad752f3`. A small
16,600-byte, byte-verified copy of the original one-flit input and Native
records now exercises the entire positive comparison path. The
[initial test receipt](INITIAL_TESTS.json) and
[retrospective failure note](INITIAL_READBACK_FAILURE.json) are retained; the
failure did not modify or invalidate the accepted Native evidence.

Full test log and large raw evidence remain on the server. The final receipts
are `runs/causal-closure-audit-tests-002`,
`runs/causal-closure-audit-readback-002`, and
`runs/causal-closure-audit-negative-002`. Compact copies are enumerated and
byte-verified in [PUBLISHED_COPIES.json](PUBLISHED_COPIES.json).

The bounded G1 accuracy conclusion remains intact. Service compression and
application-level accuracy remain separate, untested questions.
