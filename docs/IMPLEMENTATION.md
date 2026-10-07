# One maintained implementation

The active implementation is the CSR-frontier version used by full run 006.
The user requested keeping only the fastest current version in the codebase.
The historical selection below used available progress from complete-input
runs. Both placements have since completed, and direct 002–006 full-event
equivalence [passed](results/model-boundary-001/implementation_equivalence.json).
The original progress observations below are not isolated end-to-end speedups.
Duplicate bulk files in obsolete 003–005 runs now resolve to their byte-identical
006 copies through the [cleanup receipt](results/remote-cleanup-001/REVIEW.md);
unique logs and audit records remain.

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

The unified build passed remote verification at source commit `1cb822b`:

- All 134 tracked native C/C++/header/parser/Makefile inputs match the selected
  run 006 build byte for byte. Their canonical hash map has SHA-256
  `01b37cd9302ce58941c4f4b17098a26d1a599f8dd135dd834778d5fdeda95e99`.
- Rebuilt using GCC 8.5.0 and the same `-O3 -g -std=c++17` flags. New binary
  SHA-256: `fbd6fca12ec2d5d123b23ae1affcf3a84f465b38b2a694a29f7451a25d919f42`.
  Build paths changed, so native source identity and execution reports, rather
  than binary equality, establish preservation.
- The 18 native/workload semantic tests and three independent readback tests
  passed. Fourteen native input/report pairs match saved CSR evidence exactly;
  network metrics and dependency-profile accounting also match/pass.
- Checked-container ownership/credit-reset tests passed. The 1,500-round
  arbitration output matches the frozen reference hash.

Evidence resides under
`/home/wangziheng/wafer_simulator/runs/fastest-consolidation-001/`, including
`source-equivalence.json`, `acceptance.json`, and `tests/`. The source manifest
records compiler/platform details and every compared source hash.
Combined patch SHA-256:
`2e44498b90fd5f06c6ff58a09141d38c6dd1979d477a6d7fcb93118ff9f40344`.

This is packaging validation. The full performance and event-equivalence
experiments already running use the identical native source and continue with
their original binary identities; no duplicate full campaign was launched.
