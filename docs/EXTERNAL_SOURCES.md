# External source snapshots in this repository

**All Git source used by the project is delivered inside `wafer_simulator`.**
`third_party/` contains ordinary tracked files. A normal clone obtains these
files without Git submodule initialization, additional repositories or source
network downloads. Development is maintained on `main`.

| Directory under `third_party/` | Original source | Pinned commit | Use |
| --- | --- | --- | --- |
| `nw-design-for-wsi/` | [spcl/nw-design-for-wsi](https://github.com/spcl/nw-design-for-wsi) | `9470042` | WoW geometry, RapidChiplet and BookSim |
| `atlahs/` | [spcl/atlahs](https://github.com/spcl/atlahs) | `fb51a99` | Inspected current source pipeline |
| `atlahs-20250324/` | Same author repository | `e436c1d` | Historical generator used for source correspondence |
| `chakra/` | [mlcommons/chakra](https://github.com/mlcommons/chakra) | `9ff3e3e` | Official ET protobuf schema and reference reader |
| `TransformerEngine/` | [NVIDIA/TransformerEngine](https://github.com/NVIDIA/TransformerEngine) | `e5edd6c` | Captured GEMM ABI reference; not built or executed |
| `json/` | [nlohmann/json](https://github.com/nlohmann/json) | `9cca280` | Exact 3.11.3 header used by BookSim |

The [source lock](../configs/upstream_repositories.json) gives full SHAs and
runtime paths. `third_party/manifests/` records every retained file's SHA-256,
original Git blob ID/mode, original tree and commit object. All **3,317 tracked
upstream files** are retained byte-for-byte, including original notices and
tracked upstream support assets. Our changes stay outside these snapshots.
The two ATLAHS revisions are needed for the recorded comparison and successful
historical reconstruction; they are not two maintained simulator implementations.

Some upstream trees reference optional application/tool repositories through
nested `.gitmodules` files. Their gitlink identities are retained in manifests;
they are not expanded because this project does not execute them. The code
actually consumed by our adapters, schema processing and BookSim build is
included. Python packages and NVIDIA Nsight remain separately versioned runtime
dependencies. Full captured datasets and event tables stay on eex005.

## Offline restoration for existing runtime interfaces

Legacy adapters verify author commit IDs and the native builder creates isolated
Git worktrees. The main repository can reconstruct these exact source checkouts
**offline**, from vendored files and provenance metadata:

```bash
# Run on eex005, from this project checkout.
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/restore_upstreams_remote.py
```

This recreates the original tree and commit identities, with a shallow history
boundary and detached HEAD. It does not invent a new author revision. Existing
runtime checkouts are preserved and checked; differing files or pins cause an
error. `--check` makes the command read-only. `--root` allows an isolated
restoration under the remote project root. Untracked Python bytecode is counted
separately. The native build still applies our patch in an isolated worktree.

The [eex005 restoration receipt](results/source-bundle-001/VALIDATION.json)
checks all six source trees: 3,317 files and 332,722,614 bytes, restored without
fetching upstream repositories. Original commits and trees match, the project
has no remaining gitlinks, and the unchanged native patch passes `git apply
--check` in a fresh restored-author worktree. This is source/build-interface
validation; it does not rerun the accepted workload or rebuild its binary.

`configs/chakra_schema_requirements.txt` and `scripts/setup_chakra_remote.sh`
reproduce the separate protobuf environment. No TransformerEngine kernels are
installed or run to derive mathematical work counts.

Source forks created during preparation are no longer dependencies of this
project. The repository's source snapshots and manifests are the delivery.
Preserve author licensing: Chakra and TransformerEngine have Apache-2.0 and
component notices; nlohmann JSON has MIT notices. The inspected WoW and ATLAHS
revisions have no repository-wide license file; their provenance and original
notices are retained without relicensing.
