# Validation: Compatibility Provider Boundary

**Date**: 2026-09-20
**Result**: PASS for T008–T011; human implementation acceptance recorded
**Maturity**: Controlled target-neutral conformance implementation; exact platform candidate and
target-specific contract drafted, selected-target decision incomplete

## Spec Kit and artifact checks

The companion prerequisite command resolves `specs/001-compatibility-provider-boundary` and reports
the research, data model, provider contract, quickstart, and tasks. Feature/review Markdown files were
checked with no unresolved template markers or broken local links. FR-001–FR-021, SC-001–SC-007,
T001–T019, ACC001–ACC017, and conformance cases C01–C14 are contiguous.

## Architecture result

The [separate design review](../../docs/reviews/001-compatibility-provider-boundary-design-review.md)
initially found two BLOCKER, two MAJOR, and two MINOR issues. All six were repaired. Re-review found no
new BLOCKER or MAJOR issue. The repaired design preserves repository ownership, legacy immutability,
permit/evidence ownership, and separate selection/execution gates while matching platform API `0.4.0`.

The [implementation review](../../docs/reviews/002-compatibility-provider-conformance-implementation-review.md)
initially found two MAJOR and three MINOR issues; final re-review added one MAJOR parent-traversal
finding. All six are repaired, and the final review found no new BLOCKER or MAJOR issue.

## Implementation checks

- `xverse-xdl==0.4.0` is exact in package metadata and `uv.lock`; `platform-api.lock.json` additionally
  pins the complete 22-file local package surface by file count and path/content SHA-256.
- Seventeen compatibility tests pass: C01–C14 plus source-policy, exact-version, and content-pin checks.
- C10 proves catalog/environment mutation exclusion through two platform controllers and distinct
  execution IDs; C11 proves `unavailable`, `not-ready`, and timeout outcomes.
- C06 rejects parent traversal in isolation roots, executable allowlists, action executables, and
  working directories as well as direct out-of-bound paths.
- Python compilation passes. Four production/support files have complete docstrings; Doxygen indexes
  all six Python sources, emits no warning, and passes its negative coverage self-test.
- `uv build` produces both `xverse_compat-0.1.0.tar.gz` and a pure-Python wheel. The source archive
  contains the platform content manifest and Doxygen configuration; the wheel contains all three
  `xverse_compat` modules.
- `uv lock --check` resolves 21 compatibility packages without changing `uv.lock`.
- The platform regression suite passes 90 tests. Platform Doxygen indexes all 30 Python
  files without warnings, and its 20-package `uv lock --check` passes.

No target-specific provider, target selection, legacy action, subprocess, network access, or legacy
repository change occurred. The fixture validates process actions entirely in memory.

Platform SD-0001 now pins the Zenoh/SOME-IP candidate identity, graph, and artifact. Its open
environment/ownership, readiness, interface, vendor-binary, and evidence-retention findings mean this
does not satisfy T012 or authorize target code.

The user later authorized a build-only evidence pass. Platform now records a reproducible candidate
gateway and deterministic bundle without executing it or modifying the legacy checkout. This resolves
the absence of a candidate digest, while target-owner acceptance, durable retention, vendor-binary
disposition, the environment, and lifecycle/interface contracts keep T012–T014 open.

The target-specific gateway contract and separate review fix exact selection, ownership ceilings,
fail-closed lifecycle behavior, and blocker mapping. The review has one external BLOCKER, three MAJOR,
one MINOR, and one ADVISORY finding open; all depend on missing evidence or owner decisions. No
target-specific provider code or external action was added.

The platform closure packet now maps each plan blocker to acceptable public and restricted evidence
and records the unresolved startup-order disagreement. It is referenced rather than duplicated here;
no blocker is closed by the supplemental architecture documents.

The subsequent static audit supplies a six-route public interface projection and pins the available
vsomeip/Zenoh artifact evidence. It also finds a compiled private endpoint, native-memory float ABI,
payload-bearing logs, unreliable events, detached work, and absent graceful-stop/readiness API. These
are documented constraints; they do not satisfy T012–T014 or authorize provider code.

## Gate status

- Specification quality: PASS
- Structural and link validation: PASS
- Design review: PASS with CP-R01–CP-R06 resolved
- Human design acceptance: PASS (ACC010)
- Target-neutral implementation review: PASS with CP-I01–CP-I06 resolved
- Human implementation acceptance: PASS (ACC017, user-approved 2026-09-20)
- Target-specific contract: DRAFT REVIEWED; REQUIRED VALUES OPEN
- Target-specific provider implementation: NOT AUTHORIZED
- Legacy target selection: EXACT CANDIDATE NOMINATED; REQUIRED DECISION FIELDS OPEN
- Legacy execution: NOT AUTHORIZED
