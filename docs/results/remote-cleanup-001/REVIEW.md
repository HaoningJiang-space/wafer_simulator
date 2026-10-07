# Reclaim duplicate remote artifacts

The authorized cleanup removed **20 byte-identical bulk copies**, totaling
**13,318,329,573 logical bytes (12.4 GiB)**, on eex005. The project occupied about
41 GiB before and 29 GiB afterward. Filesystem availability also reflects other
users and processes; it is not the deletion accounting.

The [receipt](PRUNED.json) records each removed path, its retained canonical path,
size, original modification time and SHA-256. Canonical hashes were rechecked
after deletion. `scripts/prune_duplicate_runs_remote.py` restricts candidates
to exact named obsolete runs, requires terminal evidence, checks regular-file
identity, and rejects candidates referenced by current-user process working
directories or file descriptors.

Removed files are `trace.json`, `events.jsonl` and `checked_events.npy` for both
placements in runs 003, 004 and 005, plus the two duplicate traces in excluded
run 001. Their identical copies remain in accepted run 006. Unique configs,
stdout/stderr, audits, completion/exclusion markers and all reference 002,
006 and M1 results remain. Complete raw inputs and current normalization
artifacts remain on the server. No unrelated project was cleaned.

Historical reports may name one of the removed bulk paths. Resolve it through
`PRUNED.json` to the retained byte-identical file, or copy that canonical file
back if a historical command requires the old path. This relocation does not
change the original file's hash or invalidate the saved comparison.

The remote receipt is also retained at
`/home/wangziheng/wafer_simulator/runs/cleanup-duplicates-001/PRUNED.json`.
