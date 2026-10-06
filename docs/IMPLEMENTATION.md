# One maintained implementation

The active implementation is the CSR-frontier version used by full run 006.
The user requested keeping only the fastest current version in the codebase.
The selection below uses available progress from complete-input runs; final
end-to-end timings and full-event equivalence remain pending.

## Selection evidence, 2026-10-06 10:59:56 UTC

For each placement, compare time to the same ejected-flit count. Elapsed times
are interpolated between 60-second progress samples; they exclude constructor
and final output/audit time. All runs use the same complete capture and controls.

| Implementation | Baseline: 31,948,647 flits, seconds | Rotated: 56,469,642 flits, seconds |
| --- | ---: | ---: |
| Completion-corrected reference, 002 | 9,360.00 | 9,360.00 |
| Routing references, 003 | 2,676.08 | 3,732.65 |
| Dense state, 004 | 2,058.91 | 2,713.05 |
| Node reuse, 005 | 2,088.56 | 2,754.50 |
| CSR frontier, 006 | 2,033.82 | 2,696.06 |

CSR leads both comparisons, by about 1.2% and 0.6% over 004. These small
differences are observational: runs overlap, the logs are sampled, and one
earlier common-work point favored 004 slightly in the rotated case. They do not
establish a statistically stable advantage or a completed speedup. CSR is the
single maintained choice using the available evidence; no new variant is being
introduced to chase a small difference.

Source evidence is each existing run's `baseline/stdout.log` and
`ours_rotated/stdout.log` under `/home/wangziheng/wafer_simulator/runs/`.
The native semantics passed 18 tests and 14 exact report comparisons before
consolidation. Full-run event-hash checks remain active.

## Active entry points

| Responsibility | Maintained path |
| --- | --- |
| Author source | `third_party/nw-design-for-wsi`, pinned at `9470042fb2d8b5368556e46cc75ac818dbf31522` |
| Native changes | `patches/booksim-wafer.patch` |
| Complete experiment controls | `configs/llama16_fixed_state.json` |
| Remote build | `scripts/build_remote.sh` → `build/booksim/` |
| Correctness verification | `scripts/test_remote.sh NEW_TEST_DIRECTORY [SAVED_REFERENCE]` |
| Full execution | `scripts/run_full_remote.sh NEW_RUN_DIRECTORY` |
| Full-event comparison | `scripts/verify_full_replay.py` |

The combined patch contains the exact native source changes previously obtained
by applying completion, topology-reference, dense-state, node-reuse and CSR
patches in order. Source layout within the native implementation is retained;
consolidating the patch does not merge the graph, profiler, network, allocator
or credit responsibilities into one module. Python layer boundaries are also
unchanged.

Older patches, variant configs and variant build/run scripts were removed from
the working tree. They remain in Git history at `f530c82`. Remote processes,
frozen build worktrees, inputs and evidence were not deleted or restarted.
Their running wrappers can still invoke the retained full-event verifier.
The pinned author binary remains a test oracle, not a maintained product variant.

## Consolidation acceptance

Verify the combined patch produces the same native sources as the selected run
006 build, rebuild on eex005, and require the semantic reports and arbitration
grants to match saved evidence. This is packaging validation; no new full
performance campaign is needed solely to rename/repackage identical code.
Remote results are recorded here after verification.
