# Quickstart: Validate the Compatibility Provider Boundary

## Resolve the Spec Kit feature

From `xverse-compat`:

```sh
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

The result must resolve `specs/001-compatibility-provider-boundary`.

## Review order

1. Read [spec.md](spec.md) for scope and gates.
2. Read [contracts/provider.md](contracts/provider.md) for operations and responsibility ownership.
3. Compare the imported platform contracts in sibling `xverse-platform/specs/005-component-catalog-compat-runtime/contracts/`.
4. Read [tasks.md](tasks.md) and distinguish completed target-neutral conformance from gated target work.
5. Read both separate architecture reviews before accepting the implementation.

## Reproduce the implementation checks

From `xverse-compat`:

```sh
uv sync --frozen
uv lock --check
uv run python -m unittest discover -s tests -v
uv run python scripts/check_doxygen.py --self-test
```

The restricted agent environment redirects uv's cache to a writable temporary directory:

```sh
UV_CACHE_DIR=/tmp/xverse-compat-uv-cache uv lock --check
```

## Expected result

The package imports exact platform API `0.4.0`, validates its reviewed source content pin, passes the
C01–C14 target-neutral suite, and generates complete Doxygen output. It completes no legacy target
selection, invokes no subprocess, duplicates no platform lifecycle type, and grants no target execution authority.

The [gateway contract candidate](contracts/zenoh-someip-gateway.md) can be reviewed as a target-specific
projection. Its seven plan blockers prohibit provider implementation and external execution.
