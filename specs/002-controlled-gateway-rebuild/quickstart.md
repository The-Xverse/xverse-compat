# Quickstart: Controlled Gateway Rebuild

Validate the implemented mechanism without a legacy target or network process:

```sh
UV_CACHE_DIR=/tmp/xverse-uv-cache uv run python -m unittest tests.test_rebuild
python3 scripts/check_doxygen.py --self-test
```

To prepare a future reviewed target build, place its manifest and restricted patch outside the
repository, provide an explicit executable allowlist through the embedding caller, and use a new empty
work root. The CLI intentionally requires the executable mappings as repeated arguments and never
reads ambient tool choices from the source tree.

```sh
python3 scripts/rebuild.py \
  --manifest /controlled/public-manifest.json \
  --source /read-only/exact-source \
  --patch /controlled/restricted.patch \
  --work-root /disposable/rebuild \
  --tool approved-builder=/absolute/reviewed/builder \
  --result /controlled/public-result.json
```

This command is an example contract only. Do not run it against SD-0001 until the restricted patch,
toolchain/environment, OS containment, and artifact-retention decisions are reviewed. The manifest
must pin SHA-256 identities for Git and every logical build tool. A successful result never permits
running the output.
