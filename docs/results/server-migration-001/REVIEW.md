# Active runtime moved to hn072; historical evidence retained

The active runtime is `/Projects/haoning/wafer_simulator` on
`hn072@143.89.78.72` (`ee4e072`). New experiments no longer run on eex005.
Source remains one `main` branch with pinned ordinary upstream files. The local
`hn072` Git remote points to the new server's project bare repository. Passwords
and private keys are not stored in project files.

The native online, endpoint and standalone binaries were copied byte for byte.
The online binary remains
`d37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb`.
The project uses its own Python 3.13 environment on the project filesystem.
The migration gate passed 196 semantic/native-interface tests; scaling also
requires exact 4×4 local/remote S execution hashes from the accepted old run.
New-server wall times are never compared to old-server times as model speedups.

## Cleanup and recovery

On eex005, `/home/wangziheng/wafer_simulator/migration-20261009/` retains:

- `EVIDENCE.tar.gz`: 5,372,517,586 bytes; SHA-256
  `d235c06363dd4cda5b3dc4fb922d140bc92e5463cb82122ed3ac7beb21890930`.
- `MANIFEST.json`: 50,072 regular-file/symlink entries, 33,553,882,155 logical
  file bytes; SHA-256
  `6dceb372f8eab06c989488ac03c391bff2cd7cfbe0567ca3556c347cd691fa49`.
- Verification, representative restore checks and retirement receipts.

Every archived file was decoded and hashed independently, including exact
member-set, mode and symlink checks. Representative binary, JSON and NumPy
members were restored and rehashed. Before deletion, all live source files were
hashed again and accessible current-user process cwd/exe/fd/maps were checked
for active references. See [verification](ARCHIVE_VERIFIED.json) and
[retirement](RETIRED.json).

Only the verified expanded `runs`, `downloads`, `build`, `profiles`, `logs`,
`upstream`, `deps` and `.venv` directories were removed. Source checkout, bare Git,
archive and receipts remain; no other project was cleaned. Filesystem free space
increased by **26,513,375,232 bytes** during removal (shared-filesystem observation,
not a promise that other users' usage remained constant). The remaining project
is approximately 6 GiB. The cold archive remains on eex005; it has **not** all
been transferred to hn072. Active source and native binaries have migrated.

To recover a historical run, copy the archive (or extract the selected member on
eex005) to a fresh recovery directory, then extract the exact relative `runs/...`
or `downloads/...` member. Paths inside historical reports retain their original
provenance. Do not overwrite accepted new runs or unpack environments over the
active Python environment. `scripts/migrate_evidence_remote.py` documents the
content verification and deletion guard used here.
