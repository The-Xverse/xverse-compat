# Validation: Controlled Gateway Rebuild

**Status**: Mechanism validated; human acceptance and target patch remain pending

## Results

- Spec Kit prerequisites resolve `specs/002-controlled-gateway-rebuild` with its research, data model,
  contracts, quickstart, and tasks.
- All 41 compatibility tests pass: 17 existing provider-conformance cases and 24 controlled-rebuild
  cases. Rebuild coverage includes exact source/patch/tool identity, dirty-tree exclusion, traversal,
  path-header disagreement, environment safety, no-shell tool selection, timeout, missing/symbolic
  output, atomic result creation, two-stage equality, mismatch rejection, and source immutability.
- Python compilation passes for package, scripts, and tests.
- Doxygen covers all six production Python files, indexes all nine Python files, emits no warnings,
  and passes its negative coverage self-test.
- `uv lock --check --offline` resolves 21 packages. Package version `0.2.0` builds as both sdist and
  wheel; the rebuild module is in both, while the repository CLI/tests are correctly present in the
  sdist.
- Placeholder, local-link, and public-safety scans pass for the feature, implementation, review, and
  affected platform decision records.
- The platform retains 90 passing tests, valid M3 fixture evidence, and an exact valid-but-blocked
  SD-0001 report with seven blockers and `legacyExecution:false`.

## Review disposition

The separate architecture pass initially found one patch-path BLOCKER and two implementation MAJOR
findings. The repair pass binds every patch header to one allowlisted in-place target, pins and reports
exact Git/build-tool executable digests, and writes results atomically without replacement. Timeout
coverage was added. No BLOCKER or MAJOR mechanism defect remains.

Directory staging remains explicitly non-containment. An actual SD-0001 patch requires ACC010 plus an
approved OS containment/environment attestation and the existing interface, peer, retention, resource,
and owner decisions. No target patch, gateway, peer, or production workload was invoked.
