# Feature Specification: Compatibility Provider Boundary

**Feature Branch**: `001-compatibility-provider-boundary`

**Created**: 2026-09-20

**Status**: Target-neutral conformance implemented and reviewed; human implementation acceptance pending

**Input**: Define the `xverse-compat` side of the M3 provider boundary without duplicating platform
catalog, planning, permit, ownership, evidence, or XDL semantics.

## User Scenarios & Testing

### User Story 1 - Review one compatibility-provider boundary (Priority: P1)

As an architecture reviewer, I can see exactly what a compatibility provider receives, what it may
do, what it must return, and which responsibilities remain in `xverse-platform`.

**Why this priority**: Repository ownership and dependency direction must be unambiguous before a
legacy-specific implementation is selected.

**Independent Test**: Review the provider contract and responsibility matrix without consulting
implementation code or inferring behavior from a legacy repository.

**Acceptance Scenarios**:

1. **Given** a platform lifecycle plan and selected provider ID/kind, **When** the contract is read,
   **Then** provider actions, ownership-handle rules, failure propagation, and evidence boundaries are explicit.
2. **Given** platform permit and journal semantics, **When** responsibilities are compared, **Then**
   the compatibility repository neither redefines nor bypasses them.

### User Story 2 - Prove a future provider conforms safely (Priority: P2)

As a provider implementer, I can use a target-neutral conformance suite to prove exact-handle
ownership, idempotency, bounded actions, reconciliation, and fail-closed errors before connecting a
legacy artifact.

**Why this priority**: Generic safety behavior should be proven independently from one target's behavior.

**Independent Test**: Run future contract tests against a controlled compatibility fixture with no
legacy checkout or production process access.

**Acceptance Scenarios**:

1. **Given** an unknown or forged handle, **When** observe, stop, cleanup, or revalidation is requested,
   **Then** the provider rejects it without discovering or mutating an ambient resource.
2. **Given** repeated or concurrent lifecycle calls, **When** the conformance suite runs, **Then** no
   duplicate external resource is created and only exact owned state can change.

### User Story 3 - Gate a selected legacy provider (Priority: P3)

As an owner/reviewer, I can require a complete selected-component decision before any target-specific
provider code or execution work begins.

**Why this priority**: M0 found several plausible boundaries but no owner-supported target or verified runtime baseline.

**Independent Test**: Attempt to advance with a missing target, mutable artifact, incomplete lifecycle,
secret dependency, or absent authorization and verify that the implementation task remains blocked.

**Acceptance Scenarios**:

1. **Given** only M0 inventory evidence, **When** provider implementation is proposed, **Then** the
   proposal remains blocked until an owner-reviewed decision pins all required fields.
2. **Given** an approved selection record but no execution permit, **When** the provider is reviewed,
   **Then** implementation may be assessed but no legacy lifecycle action is authorized.

### Edge Cases

- An implementation cannot claim ownership from a PID, port, path, service name, or discovery result.
- A provider ID/kind unknown to the compatibility package fails closed; it does not fall back to a generic shell.
- A secret-dependent selection remains visible for review but cannot be planned or executed in M3.
- A provider restart cannot reconstruct mutation authority without exact persisted-handle revalidation.
- Logs and exceptions cannot expose credentials, private addresses, sensitive paths, or proprietary payloads.

## Requirements

### Functional Requirements

- **FR-001**: `xverse-compat` MUST own legacy-specific provider implementations and deployment glue;
  domain/business logic MUST remain in the unchanged external component.
- **FR-002**: A compatibility provider MUST implement an exact-version-pinned public lifecycle provider
  contract supplied by `xverse-platform`; this repository MUST NOT copy or redefine platform models.
- **FR-003**: Provider selection MUST use the exact provider ID and kind already present in the
  validated XDL-derived lifecycle plan. An explicit composition root MUST resolve exactly one
  statically supplied implementation and reject zero or multiple matches; no second provider
  descriptor or ambient registry is permitted.
- **FR-004**: A current M3 compatibility provider MUST accept only an explicit platform `ProcessAction`
  from the plan and MUST NOT infer
  commands, targets, paths, ports, credentials, or cleanup scope from the host environment.
- **FR-005**: `start` MUST return an opaque platform-compatible ownership handle bound to execution ID,
  action ID, provider ID, provider kind, and exact external resource identity.
- **FR-006**: `observe`, `stop`, `cleanup`, and `revalidate` MUST require exact equality with a handle
  previously issued by that provider; discovery data never grants mutation authority.
- **FR-007**: Start and stop behavior MUST be idempotent for one activated execution, and mutations for
  one catalog/environment identity MUST not create concurrent duplicate resources.
- **FR-008**: Every provider action MUST obey the action timeout and return only declared lifecycle
  observations; delay completion alone MUST NOT be reported as readiness.
- **FR-009**: Provider failures MUST fail closed and expose a stable public-safe failure classification
  to the platform controller without leaking restricted target output.
- **FR-010**: The platform controller MUST remain the authority for execution permits, activation,
  lifecycle ordering, mutation locks, intent/outcome evidence, and `evidence-incomplete` behavior.
- **FR-011**: A provider MUST NOT issue, broaden, consume, or persist execution permits and MUST NOT
  write directly to the platform evidence journal.
- **FR-012**: Provider-specific diagnostics and observations MUST be deterministic and public-safe by
  default, with restricted details referenced through approved local evidence rather than embedded.
- **FR-013**: Provider implementation MUST use only an explicitly selected immutable artifact or
  controlled fixture and MUST leave every legacy source checkout unchanged.
- **FR-014**: Process-like execution MUST require a reviewed isolation boundary, exact execution root,
  executable allowlist, closed inherited handles, explicit non-secret environment, and no implicit shell.
- **FR-015**: M3 compatibility providers MUST NOT resolve or inject secrets; a secret dependency blocks
  provider implementation and execution pending a separate capability.
- **FR-016**: A target-neutral conformance suite MUST cover forged handles, idempotency, concurrency,
  timeouts, readiness mismatch, interruption/revalidation, public safety, and unowned cleanup rejection.
- **FR-017**: Target-specific provider implementation MUST remain blocked until the platform selected-
  component decision contract is completed and owner-reviewed with exact revisions, artifact,
  environment, interfaces, lifecycle, containment owner, exclusions, and evidence policy.
- **FR-018**: Legacy execution MUST additionally require an explicit matching platform execution permit;
  an approved selection or provider implementation alone grants no execution authority.
- **FR-019**: Fixture conformance or lifecycle success MUST NOT be described as protocol compatibility,
  application parity, fidelity, production readiness, or migration completion.
- **FR-020**: This implementation increment MAY create only a controlled target-neutral in-memory
  provider fixture, explicit composition root, and conformance tests. It MUST create no target-specific
  provider, external descriptor, legacy action, subprocess invocation, network connection, or legacy
  repository modification.
- **FR-021**: A non-process target MUST remain blocked until a separate platform specification defines
  its typed action model; a missing action MUST NOT carry or imply provider-private target configuration.

### Key Entities

- **Provider Binding**: Exact provider ID/kind already selected by an immutable platform lifecycle plan.
- **Compatibility Provider**: Legacy-specific implementation of the platform-owned lifecycle protocol.
- **Provider Action**: Explicit typed start, observe, stop, cleanup, or revalidation request.
- **Ownership Handle**: Opaque platform model issued by the provider for one exact external resource.
- **Conformance Fixture**: Controlled target-neutral implementation used to test provider invariants.
- **Selected-Component Decision**: Platform-owned owner-reviewed gate required before target implementation.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every provider operation and every platform/compat responsibility has exactly one owner in
  the contract matrix, with no duplicated permit, plan, journal, or XDL model.
- **SC-002**: All FR-001–FR-021 map to explicit design or future implementation tasks and acceptance checks.
- **SC-003**: At least ten negative conformance cases are specified before any target-specific provider is implemented.
- **SC-004**: Review finds no route from provider selection to mutation without both an owner-reviewed
  selected-component decision and a matching platform execution permit.
- **SC-005**: Public documentation contains no credential, private infrastructure, proprietary excerpt,
  unsupported compatibility claim, or inferred owner approval.
- **SC-006**: A separate architecture review has no unresolved BLOCKER or MAJOR finding before this
  provider-boundary design is treated as complete.
- **SC-007**: The target-neutral suite proves all C01–C14 cases with zero subprocess or legacy execution,
  and the complete compatibility test suite passes from the exact locked dependency environment.

## Assumptions

- The platform M3 contracts and prototype lifecycle types are the source of truth and remain prototype APIs.
- Provider packaging language is deferred until one target is selected; any conformance implementation
  must first pin the exact `xverse-xdl` package/API version.
- The first compatibility implementation uses a controlled in-memory process-action fixture before any
  legacy artifact; it validates action and ownership boundaries without invoking a process.
- M0 candidates remain evidence for a later human selection; none is selected by this feature.

## X-Verse capability obligations

**Compatibility impact**: Defines the companion-side contract only; no legacy or platform interface changes.

**Failure semantics**: Unknown providers, malformed actions, unowned handles, missing isolation,
secret dependencies, and incomplete selections fail closed without target mutation.

**Observable outcomes**: Reviewable provider contract, responsibility matrix, conformance requirements,
gated task list, analysis, validation record, and architecture review.

**Maturity**: Approved provider-boundary design with an authorized target-neutral conformance fixture;
no target-specific compatibility provider or legacy runtime evidence.

**Exclusions**: Target selection, provider code, descriptors, secrets, legacy execution, protocol conversion,
application parity, production deployment, remote discovery, and changes to legacy repositories.
