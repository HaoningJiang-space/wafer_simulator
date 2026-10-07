# M0/M1 placement comparison

Both full placement pairs passed completion audits. The native binary and per-placement network/mapping are identical across models.

| Model | Baseline (s) | Rotated (s) | Baseline minus Rotated (ms) | Placement speedup |
| --- | ---: | ---: | ---: | ---: |
| M0 | 1.738783916 | 1.736418652 | 2.365264 | 1.001362151 |
| M1 | 2.040325219 | 2.027207062 | 13.118157 | 1.006471049 |

The comparison changes only source-verified local transfers. Both original endpoint costs are replaced by target-network service; remaining local costs and every original dependency are preserved.

See M1/attribution.md for both actual critical chains and message phases; M1_local_stages/LOCAL_STAGES.json classifies the retained local stages. MODEL_COMPARISON.json additionally compares the same original inter-host messages across models. All-message means span different populations after expansion.

This is not calibrated native WoW training time, thermal evidence, matched physical cost, or a universal placement ranking. Message records do not identify internal router/port/VC causes.
