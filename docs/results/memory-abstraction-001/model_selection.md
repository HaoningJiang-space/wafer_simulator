# Model choice for the accepted machine and work

See [REVIEW.md](REVIEW.md) for contracts, complete figures, cost and evidence.

| Intended judgment | U0 | U1 | S |
|---|---|---|---|
| Complete application within 2% of S | Fails all 3 layouts | Fails all 3 layouts | Conditional mechanism reference |
| Every layout gap within 100 cycles of S | Fails all 3 pairs | Fails all 3 pairs | Reference |
| Reject concentrated storage qualitatively | Yes, including retained staging effect | Yes, including bank/controller sharing | Yes |
| Distinguish near and opposite | Predicts a tie | Predicts a tie | Near wins by 3,193 cycles |
| Candidate-set worst regret in S | 3,193 cycles | 3,193 cycles | 0 |
| Per-bank capacity | Unmodeled; aggregate only | Checked | Checked |
| Per-controller conservative staging | Checked | Checked | Checked |
| DRAM spatial network contention | Unmodeled | Unmodeled | Modeled by existing BookSim |
| Hardware calibration | Declared assumptions | Declared assumptions | Declared assumptions |

U0/U1 remain cheaper diagnostic representations. Use S for these registered
layout and quantitative timing decisions. Do not claim S is silicon truth or
that flit-level detail is the minimum sufficient model. The current experiment
establishes failure of these particular aggregate projections; it has not tested
every possible spatial approximation.

Freeze all three models. Extend physical-scale/work coverage under explicit
legal geometry and scaling rules before proposing another model mechanism.
