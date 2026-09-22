# X-Verse Compatibility Code Reference {#mainpage}

This reference documents the compatibility-provider conformance and controlled-rebuild package. It
imports the exact platform lifecycle API rather than copying platform models.

## Package boundary

The `xverse_compat` package currently contains:

- an explicit composition root that resolves one exact provider ID/kind pair;
- an in-memory process-action fixture that validates isolation, allowlist, environment-name, timeout,
  idempotency, and exact-handle rules; and
- a controlled derivative-rebuild envelope that verifies exact Git and external patch identities,
  creates two clean stages, runs only allowlisted no-shell build tools, and compares exact outputs.

The rebuild envelope is build-time tooling. Its tests use only synthetic repositories and fixture
builders. It never runs the resulting artifact, publishes the restricted target patch, or changes a
legacy checkout.

The provider contract and maturity gates remain normative in
`specs/001-compatibility-provider-boundary/`; rebuild rules live in
`specs/002-controlled-gateway-rebuild/`. Fixture and reproducibility evidence prove only their stated
mechanics. They do not establish compatibility, parity, fidelity, migration completion, runtime
readiness, or production suitability.

## Documentation workflow

Python docstrings are the symbol-documentation source. Generate and validate the reference with:

```sh
python3 scripts/check_doxygen.py --self-test
```

Generated HTML is disposable output under `build/doxygen/` and is not versioned.
