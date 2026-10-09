# What the saved traces establish

This supplements the byte-exact [generated report](REVIEW.md). It uses the
original 18 application traces; there are no new application simulations or
policy changes. The observational reader ran at source `1382dfe` in
`runs/periphery-attribution-001` on hn072. Seven dedicated regressions pass;
analysis wall time is 27.903 seconds. Reproduction of that original analysis
uses its pinned source, because its frozen-source gate is deliberately strict.
The later [acceptance repairs](../memory-periphery-audit-fix-001/REVIEW.md)
independently revalidate all underlying executions at `cdc322e`.

## Earlier supply does not imply faster network service

In B, semantic matching finds **zero source packet-order reversals and zero
actual route changes** across all 92,525 packets between shared whole and
pipeline. Its greater application improvement therefore does not require a
change in those two observed properties. Readiness, service interleaving,
backpressure and destination work still change. This is not an intervention
that proves packet batching has no effect.

The B critical operation sequence admits a useful same-movement comparison:

| Critical block | Whole cycles | Pipeline cycles | Pipeline − whole |
|---|---:|---:|---:|
| `first17` W read | 10,383 | 6,543 | −3,840 |
| First local/compute block | 3,584 | 3,584 | 0 |
| Inter-operation C2C movement | 1,161 | 1,698 | +537 |
| `second17` V read | 10,377 | 7,042 | −3,335 |
| Second local/compute block | 3,584 | 3,584 | 0 |
| Final Y write | 2,214 | 1,110 | −1,104 |
| Complete chain | 31,303 | 23,561 | −7,742 |

W's first payload offset falls from 3,182 to 302 cycles. Its payload service
envelope, first payload ready to last payload finish, stays **6,177 cycles**.
V's first offset falls from 3,182 to 304, while its payload envelope increases
from **6,171 to 6,674 cycles**. The read transactions finish earlier despite
these envelopes. Supply timing and overlapped destination work matter; the
data do not establish universal network acceleration.

These matched blocks sum to the observed B change, but are not independent
causal effects. In A the selected critical operations change and bank
serialization exposure grows by 2,688 cycles, while makespan falls by 5,300.
Its DRAM-read median also rises from 6,421 to 7,241.5. The
[critical-chain plot](critical_chain.png) explains why transaction medians
alone cannot account for application time.

B's chain memory accounting falls by 5,776 cycles and network accounting by
1,966. A's corresponding reductions are 1,348 and 3,952. Their difference
closes the extra 2,442-cycle B benefit, but the changing chains prevent turning
those subtractions into separable interventions. Shared-link window counts
show real overlapping traffic, not a conversion from peer flits to queue delay.

## Report demand before inventing hardware limits

| Observed shared-pipeline envelope | A | B |
|---|---:|---:|
| Per-transaction end-to-end positions | 4 | 4 |
| Positions associated with one controller | 16 | 4 |
| Command-ready to final-commit transaction lifetime proxy | 4 | 1 |
| Delivered but uncommitted useful bytes, any interface | 16,384 | 16,384 |

The position count includes source queueing and remote work; it is not proof
of controller-resident storage. The lifetime proxy is one explicitly chosen
descriptor-like interval, not a hardware descriptor count. The RX envelope
adds useful bytes at native ejection+1 and removes a fragment at destination
commit; it cannot observe partial consumption during serialization or certify
FIFO capacity. Existing full-object staging remains within declared capacities.

No target DMA descriptor, total outstanding-fragment or RX budget exists yet.
The [window contract](../../MEMORY_WINDOW_CONTRACT.md) records globally visible
remote completion with no return delay. Both declared machines remain; selecting
a principal target requires controller ownership/lifetime, issue limits and a
buffer/notification protocol. None is inferred from the favorable ranking.
D1 remains the registered v1 candidate and has no application acceptance.

Compact reports and plots are published here; full profiles, matched movements
and directed-link activity tables remain on hn072. [RUN_COMPLETE.json](RUN_COMPLETE.json)
is the original server completion receipt; it includes large server-only files.
