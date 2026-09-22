# Controlled derivative-rebuild implementation review

**Date**: 2026-09-21

**Reviewer**: Codex, separate architecture pass after the first implementation and test run

**Scope**: Exact input identity, patch containment, source immutability, command execution, output
identity, reproducibility, public safety, target-use gates, and maturity claims.

**Initial disposition**: Accept the feature design and synthetic test direction. Repair CR-R01,
CR-R02, and CR-R04 before implementation acceptance. Keep CR-R03 as an explicit external target-use
gate; a filesystem stage is not a containment boundary.

## Findings recorded before repair

| ID | Severity | Finding / impact | Required disposition | Initial status |
|---|---|---|---|---|
| CR-R01 | BLOCKER | Patch validation allowlisted `diff --git` targets but did not bind every `---`/`+++` header to that same target. A crafted patch could make the parser and Git disagree about the mutated path. | Parse each file block, require matching old/new/diff paths, and allowlist every path before `git apply`. Add a negative test. | Open |
| CR-R02 | MAJOR | The result bound logical build steps but not the exact Git and build-tool executable bytes. Two hosts could emit the same result identity from different tool inputs. | Pin executable SHA-256 values in the manifest, verify before staging, and carry them into the public result. | Open |
| CR-R03 | MAJOR | Separate directories prevent state reuse but do not constrain filesystem, process, or network effects of an approved build executable or source build logic. | State this limit explicitly and require an owner-approved OS containment/environment attestation before any restricted target patch is used. | Open external gate; no synthetic fixture blocker |
| CR-R04 | MAJOR | The CLI could replace an existing result path and unhandled write failures could expose a host path in a traceback. | Require a new result path and convert write failures into one stable public error. Add CLI coverage. | Open |
| CR-R05 | MINOR | Timeout behavior was specified but not exercised by the initial 19 tests. | Add a bounded timeout negative test. | Open |
| CR-R06 | ADVISORY | A reproducible derivative may be mistaken for a compatible X-COM implementation. | Keep the tool in `xverse-compat` and retain explicit no-runtime/no-compatibility language. | Open; non-blocking |

## Positive assessment

The implementation exports an exact committed tree, excludes dirty source state, leaves the source
checkout unchanged, keeps target patch content external, invokes tools without a shell, uses a minimal
manifest environment, performs two clean attempts, rejects output symbolic links, discards command
output, and exposes stable public-safe errors. No gateway, peer, production workload, or network path
was invoked by the test suite.

## Repair verification

The distinct repair pass made these changes:

- CR-R01 resolved: each patch block requires identical `diff --git`, old, and new paths, and every
  path must be allowlisted before Git sees the patch. A disagreement negative test passes.
- CR-R02 resolved: the manifest pins SHA-256 for Git and every logical build executable; the runner
  verifies them before staging and the public result binds those digests without host paths.
- CR-R04 resolved: the result writer creates an fsynced temporary file, links it atomically to a new
  destination, refuses replacement, and maps host write failures to `result-write-failed`.
- CR-R05 resolved: a fixture that exceeds its one-second step ceiling is rejected and its stage is removed.

CR-R03 remains an external target-use gate. Documentation now states that staging directories are not
OS containment, and ACC010 blocks supplying the restricted patch until that environment is approved.
CR-R06 remains a non-blocking naming/maturity constraint.

Final verification: 41 total compatibility tests pass, Doxygen covers six production files and indexes
nine files without warnings, compilation and lock checks pass, both package artifacts build, Spec Kit
resolves feature 002, and local-link/placeholder/public-safety scans pass.

## Review checklist

- [X] Review occurred after the first implementation and test pass.
- [X] Findings distinguish mechanism defects from external target-use evidence.
- [X] Source and patch contents remain outside the review document.
- [X] Every parsed patch path is bound to one allowlisted in-place target.
- [X] Exact Git and build-tool executable digests are verified and reported.
- [X] CLI result writes are new-file-only and public-safe on failure.
- [X] Timeout behavior is covered.
- [X] No BLOCKER or MAJOR implementation defect remains after repair.
- [X] Real target use remains blocked on OS containment and ACC010.

**Final disposition**: PASS for the reusable controlled-rebuild mechanism and synthetic fixture
evidence. REJECT use with an SD-0001 restricted patch until ACC010 and CR-R03's external containment
gate are satisfied. This review grants no execution permission.
