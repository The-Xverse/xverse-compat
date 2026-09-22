# Compatibility Provider Conformance Implementation Review

**Date**: 2026-09-20

**Scope**: Authorized T008–T011 exact dependency pin, explicit provider composition root, controlled
in-memory process-action fixture, C01–C14 tests, package metadata, and Doxygen tooling

**Method**: Separate architecture and implementation pass after the first complete green test run

**Initial disposition**: Changes required before T008–T011 acceptance

**Current disposition**: Repair and final re-review complete; no BLOCKER or MAJOR finding remains open

## Findings recorded before repair

| ID | Severity | Finding / impact | Required repair |
|---|---|---|---|
| CP-I01 | MAJOR | `xverse-xdl==0.3.0` is exact by version, but `uv.lock` resolves it from the mutable sibling source directory. Source content could change without a version change, weakening T008 reproducibility and the contract's prohibition on unpinned source references. | Add a deterministic content lock covering the complete packaged platform source/schema/profile surface and fail validation on version, file-set, or digest drift. |
| CP-I02 | MAJOR | C10 launches the same provider execution/action concurrently and proves provider idempotency. It does not prove the platform controller's required exclusive mutation boundary for two execution IDs sharing one catalog/environment identity. | Run two controllers with distinct permits/execution IDs against a blocking controlled provider and prove the second start fails with the stable concurrent-mutation diagnostic and performs no second mutation. |
| CP-I03 | MINOR | `observe` returns a mutable activation object from `_activation` after releasing its lock, then reads status outside the lock. A concurrent stop or cleanup can change the observed value outside the intended critical section. | Validate the exact handle and copy the status while holding the provider lock. |
| CP-I04 | MINOR | C11 proves `unavailable` and timeout outcomes but not the ordinary readiness-mismatch path that must map a nonmatching observation to `not-ready`. | Add an explicit mismatched-status test through the platform controller. |
| CP-I05 | MINOR | README, quickstart, task state, and validation still describe a zero-code design after the authorized implementation was added. | Update maturity, commands, completed tasks, results, and exclusions after repairs pass. |
| CP-I06 | MAJOR | Final repair re-review found that lexical containment accepts a working directory containing `..`, such as `/opt/xverse/conformance/../outside`. The fixture performs no execution, but this would teach an unsafe path-validation rule to future providers. | Reject parent traversal in the execution root, executable allowlist, action executable, and action working directory; extend C06 with traversal cases. |

## Positive assessment

The implementation imports platform-owned models, uses an explicit finite composition root, requires
the exact provider ID/kind pair, validates a `ProcessAction` without executing it, keeps state in
memory, rejects forged handles, exposes stable public-safe provider failures, and contains no process,
network, ambient-environment, entry-point, or filesystem-discovery mechanism. The first pass completed
16 tests, warning-clean Doxygen generation, Python compilation, and lock resolution without selecting
or contacting a legacy target.

## Repair disposition

| Finding | Resolution evidence | Status |
|---|---|---|
| CP-I01 | `platform-api.lock.json` now pins the complete 21-file packaged platform source/schema/profile surface. `verify_platform_pin` checks package version, exact file count, and deterministic path/content SHA-256; its negative test proves digest drift fails. | Resolved |
| CP-I02 | C10 now holds the platform mutation lock in one controller while a second controller uses a distinct permit and execution ID for the same catalog/environment identity. The second activation receives `XVERSE-RUNTIME-CONCURRENT-MUTATION`, and the provider creates exactly one resource. | Resolved |
| CP-I03 | Observation validates the exact handle and copies status while holding the provider state lock. | Resolved |
| CP-I04 | C11 now proves `unavailable`, ordinary mismatch mapped to `not-ready`, and elapsed timeout outcomes. | Resolved |
| CP-I05 | README, AGENTS, quickstart, specification status, task state, acceptance checklist, and validation now describe the implemented target-neutral boundary and preserve later gates. | Resolved |
| CP-I06 | Provider construction and action validation reject parent traversal in the execution root, executable allowlist, action executable, and working directory. C06 covers traversal through both construction and action paths. | Resolved |

The final repair re-review found no new BLOCKER or MAJOR issue. The exact version constraint was authored with the initial fixture patch; the uv lock and content
manifest were completed before capability acceptance and before any target-specific work. Updating
the local platform dependency now requires a reviewed version/content-pin change.

## Re-review evidence

- Compatibility suite: 17 tests pass, including C01–C14 and positive/negative dependency-pin checks.
- Compatibility documentation: four production/support files pass docstring coverage; Doxygen indexes
  all six Python files with no warning; its negative coverage self-test passes.
- Compatibility lock: `uv lock --check` resolves 21 packages without changing `uv.lock`.
- Packaging: `uv build` succeeds for the source archive and pure-Python wheel; archive inspection
  confirms the content-pin manifest/Doxygen inputs and all three package modules are present.
- Platform regression: all 84 tests pass; Doxygen indexes all 28 Python files; its 20-package lock passes.
- Spec Kit resolves the feature; compilation, local links, placeholders, public-safety patterns, and
  prohibited process/discovery-import checks pass.
- No process, network connection, legacy target, execution permit for a legacy action, or legacy
  repository modification occurred.

## Repair gate

CP-I01–CP-I06 are resolved. T008–T011 satisfy their technical gates. Human implementation acceptance
ACC017 remains pending before selected-target work begins.
