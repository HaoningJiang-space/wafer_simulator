# Pinned source repositories

The external repositories actually used by this project are now also hosted
under **HaoningJiang-space**, with their author history and license files.
The main repository records exact Git submodule commits, not moving branch
heads. Author files remain unchanged; BookSim modifications remain in `patches/`.

| Source | Owned GitHub fork | Pinned commit | Use |
| --- | --- | --- | --- |
| WoW | [nw-design-for-wsi](https://github.com/HaoningJiang-space/nw-design-for-wsi) | `9470042` | Geometry, RapidChiplet, BookSim |
| ATLAHS | [atlahs](https://github.com/HaoningJiang-space/atlahs) | `fb51a99`, `e436c1d` | Current inspected pipeline and historical capture generator |
| Chakra | [chakra](https://github.com/HaoningJiang-space/chakra) | `9ff3e3e` | Official protobuf schema and source semantics |
| TransformerEngine | [TransformerEngine](https://github.com/HaoningJiang-space/TransformerEngine) | `e5edd6c` | Reference for the captured GEMM ABI; not built or executed |
| nlohmann JSON | [json](https://github.com/HaoningJiang-space/json) | `9cca280` | Exact 3.11.3 BookSim header dependency |

Each pin has a `wafer-pinned-<short SHA>` branch in its fork. The
[source lock](../configs/upstream_repositories.json) records full SHAs, original
repositories, owned forks, submodule paths and remote runtime paths. ATLAHS has
two checkouts of the same repository because both revisions were used; they
are not interchangeable.

To fetch the source after cloning the main project:

```bash
git submodule update --init
```

Do not add `--recursive` just to reproduce this project: ATLAHS contains further
application and simulator submodules that this work does not execute. The six
direct checkouts include all Git source dependencies currently consumed by our
adapters and build scripts. Python environment packages and NVIDIA Nsight are
separately versioned dependencies, not copied source repositories.

The established eex005 runtime paths can be restored with:

```bash
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/restore_upstreams_remote.py
```

Use `--check` for a read-only verification. Existing checkouts at another commit
or with changes are preserved and cause an error. No reset, clean or upstream
source edit is performed. Untracked Python bytecode files under `__pycache__`
are counted separately as runtime products. Builds still apply patches in isolated worktrees.

The Chakra schema environment has its own pinned requirements and
[setup script](../scripts/setup_chakra_remote.sh); it does not install Chakra's
optional tracing stack or change the native simulator environment. Source
datasets, Nsight exports, full event tables and application results stay on
eex005. Git contains compact receipts and hashes for those artifacts.

Preserve upstream licensing. Chakra and TransformerEngine have Apache-2.0 and bundled component notices;
nlohmann JSON has MIT notices. WoW and the inspected ATLAHS revisions do not
provide a repository-wide license file. Forking does not relicense them; their
original notices and provenance are retained.
