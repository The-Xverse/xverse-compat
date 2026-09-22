# Feature Specification: Controlled Gateway Rebuild

**Feature Branch**: `002-controlled-gateway-rebuild`

**Created**: 2026-09-21

**Status**: Implemented and validated; human acceptance pending

**Input**: User selected the recommended configurable rebuild for SD-0001, preserving the legacy
repository and prohibiting gateway execution.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rebuild from exact inputs (Priority: P1)

As a compatibility maintainer, I can rebuild a derivative gateway only from an exact frozen source,
an exact controlled patch bundle, and an explicit recipe so that the result is reviewable and does
not mutate the legacy checkout.

**Why this priority**: A configurable derivative cannot be trusted when its source or transformation
can drift.

**Independent Test**: Use a synthetic Git repository and patch bundle to prove exact revision/tree and
digest checks, isolated staging, and rejection of every mismatch without invoking a target gateway.

**Acceptance Scenarios**:

1. **Given** matching source, patch, and recipe identities, **When** preparation runs, **Then** one
   isolated staged tree is produced and the source checkout remains byte-for-byte unchanged.
2. **Given** any revision, tree, patch, path, or command mismatch, **When** preparation runs, **Then**
   it fails before applying or building anything.

### User Story 2 - Prove reproducible output (Priority: P2)

As a reviewer, I can require two clean independent builds to produce the same declared artifact
digest before a derivative is nominated.

**Why this priority**: One successful compilation does not establish reproducibility or a stable
artifact identity.

**Independent Test**: Build a synthetic fixture in two isolated directories, compare the exact
declared outputs, and prove that divergent or missing outputs fail closed.

**Acceptance Scenarios**:

1. **Given** deterministic build outputs, **When** the rebuild completes, **Then** both output digests
   match and a public-safe result records the new digest and input identities.
2. **Given** different output bytes or a missing output, **When** comparison runs, **Then** no accepted
   artifact result is emitted.

### User Story 3 - Keep target decisions explicit (Priority: P3)

As an architecture reviewer, I can distinguish the reusable rebuild mechanism from the restricted
target patch and from any permission to run the rebuilt gateway.

**Why this priority**: Configurability does not resolve peer ABI, readiness, containment, retention,
or execution authorization.

**Independent Test**: Review the public manifest and result contract and verify that no endpoint,
route identifier, payload value, private path, execution permit, or compatibility claim is present.

**Acceptance Scenarios**:

1. **Given** a valid reproducible derivative, **When** its result is reviewed, **Then** it remains
   execution-ineligible until the platform blockers and exact execution permit are resolved.
2. **Given** a patch that changes route mappings or undeclared files, **When** preparation runs, **Then**
   the rebuild is rejected even when the patch digest itself matches.

### Edge Cases

- Source checkout symbolic links, patch paths, declared output paths, and build working directories
  that escape their approved roots are rejected.
- A dirty source checkout is acceptable only because staging uses the exact committed tree; working
  tree changes are never copied.
- Patch bundles containing binary patches, mode changes, renames, deletions, absolute paths, or
  undeclared target paths are rejected.
- Build commands use explicit argument vectors and a minimal allowlisted environment; shell text is
  never interpreted.
- Interrupted or failed builds leave only disposable staging data and cannot produce an acceptance record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The mechanism MUST accept one explicit manifest with source revision, source tree,
  patch-bundle digest, exact Git/build-tool digests, allowed patch targets, build commands, output path,
  and public metadata.
- **FR-002**: Source revision and tree MUST match the manifest before staging.
- **FR-003**: Staging MUST export the committed tree into a newly created destination and MUST NOT copy
  uncommitted source state or write to the source checkout.
- **FR-004**: The patch bundle MUST be supplied externally, match its declared SHA-256 digest, and
  contain no path outside the staged tree.
- **FR-005**: Every patched path MUST be an exact member of the manifest allowlist; binary patches,
  renames, deletions, mode changes, and symbolic-link results MUST fail closed.
- **FR-006**: Preparation MUST validate the complete patch before applying it and MUST leave no
  partially accepted staged tree on failure.
- **FR-007**: Build steps MUST use ordered argument vectors, explicit relative working directories,
  bounded per-step timeouts, no shell, and an environment assembled only from declared names and values.
- **FR-008**: Build executables MUST be selected from an exact allowlist, resolved independently of
  the source or patch bundle, and match manifest-pinned SHA-256 identities.
- **FR-009**: The mechanism MUST perform two clean builds in distinct roots and compare SHA-256 for the
  exact declared regular-file output.
- **FR-010**: The result MUST bind the source revision/tree, manifest, patch, Git, build-tool, and
  build-step digests, both output digests, final artifact digest, and a `reproducible` boolean.
- **FR-011**: Public results and errors MUST omit command output, source excerpts, environment values,
  private addresses, credentials, and sensitive paths.
- **FR-012**: A successful rebuild MUST NOT imply protocol compatibility, readiness, parity, production
  suitability, selected-component acceptance, or execution authorization.
- **FR-013**: The initial implementation MUST be validated only with controlled synthetic fixtures;
  it MUST NOT run the gateway, a peer, a production workload, or any repository-supplied executable.
- **FR-014**: The target patch MUST remain a separately controlled input until peer serialization,
  endpoint/configuration, shutdown, logging, and readiness decisions are owner-reviewed.
- **FR-015**: Route mappings and public interface identity MUST remain unchanged unless a later explicit
  decision names and authorizes that change.
- **FR-016**: The mechanism MUST provide complete Doxygen-visible documentation for its public and
  internal Python symbols.
- **FR-017**: The result writer MUST atomically create a new file, refuse replacement, and expose no
  host path or raw operating-system error when writing fails.
- **FR-018**: Directory staging MUST NOT be described as OS containment; real target use requires an
  approved external filesystem/process/network isolation boundary.

### Key Entities

- **Rebuild Manifest**: Immutable public-safe declaration of allowed inputs, operations, and output.
- **Controlled Patch Bundle**: Restricted unified-diff input identified by digest and bounded paths.
- **Staged Source**: Disposable export of the exact committed source tree.
- **Build Attempt**: One isolated invocation sequence with an explicit environment and output.
- **Rebuild Result**: Public-safe evidence that binds inputs to two matching outputs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tests cover at least twelve positive and negative cases, including identity drift, patch
  escape, undeclared targets, shell prohibition, environment isolation, missing output, and mismatch.
- **SC-002**: Two independent synthetic builds yield one identical SHA-256 artifact result while the
  source checkout hash remains unchanged.
- **SC-003**: Every failure occurs before an acceptance result and exposes only a stable public error code.
- **SC-004**: Public-safety scans find zero private endpoints, credentials, absolute home paths, source
  excerpts, or restricted patch contents in committed feature artifacts.
- **SC-005**: A separate architecture review has no unresolved BLOCKER or MAJOR defect in the rebuild
  mechanism before it is used with a restricted target patch.

## Assumptions

- The source is a local Git checkout containing the exact pinned commit and tree.
- The restricted patch store and its access policy are external to this repository.
- CMake/Ninja details for SD-0001 remain target recipe data; the reusable mechanism is build-system neutral.
- User authorization permits this controlled mechanism and build-only validation, but no legacy process execution.

## X-Verse capability obligations

**Compatibility impact**: Adds a build-time compatibility tool only. It changes no platform API,
legacy repository, route mapping, protocol, or production interface.

**Failure semantics**: Identity, path, patch, command, environment, build, and reproducibility failures
return stable public codes and produce no accepted result.

**Observable outcomes**: A validated manifest, isolated staged/build roots, two digest observations,
and a public-safe result document.

**Maturity**: Rebuild-envelope implementation for controlled fixtures. Target patch and derivative
gateway remain blocked and runtime-unverified.

**Exclusions**: Target patch content, private configuration, peer ABI choice, provider implementation,
gateway/peer execution, runtime readiness, compatibility/parity claims, artifact retention approval,
and production deployment.
