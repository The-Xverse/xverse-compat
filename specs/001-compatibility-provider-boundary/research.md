# Research: Compatibility Provider Boundary

## Decision 1: Import the platform lifecycle protocol

**Decision**: A future provider implements the public lifecycle protocol and returns platform-owned
handle/status types through an exact-version dependency on `xverse-xdl`. The pin is established before
any conformance code and updated only through review. For the local unpublished dependency, the
complete packaged source/schema/profile file set is additionally protected by a reviewed SHA-256 tree
manifest so a mutable sibling path cannot drift while retaining the same version.

**Rationale**: One authoritative model prevents drift in permits, ownership, evidence, and failure semantics.

**Alternatives considered**: Copying protocol classes into this repository was rejected because it
would create two lifecycle contracts. A transport-neutral remote API is deferred until required.

## Decision 2: Static, exact provider selection

**Decision**: A compatibility package advertises only exact supported provider ID/kind pairs in code.
An explicit composition root receives a finite tuple of provider instances, requires exactly one pair
match, and fails on no match or duplicates. The pair is already authored in the validated XDL Profile
payload and selected in the lifecycle plan.

**Rationale**: This avoids ambient discovery and a second provider-configuration language.

**Alternatives considered**: Entry-point discovery and directory scanning were rejected for M3 because
they weaken closed-set reproducibility. A separately authored registry duplicates XDL selection.

## Decision 3: Limit current compatibility actions to processes

**Decision**: Current M3 compatibility implementations accept only the platform `ProcessAction`.
The platform fixture remains a non-external mechanics proof. A non-process target requires a separate
platform-owned typed-action specification and API change before compatibility implementation.

**Rationale**: The concrete protocol accepts `ProcessAction | None`; treating `None` as hidden target
configuration would violate the closed-set plan and make action digests incomplete.

**Alternatives considered**: Provider-private configuration was rejected. A generic untyped payload
was rejected because it would create a second configuration language.

## Decision 4: Platform owns authorization and evidence

**Decision**: Providers perform only exact target actions and return observations/handles. The platform
controller owns permit validation, action ordering, mutation exclusion, and journal writes.

**Rationale**: Providers cannot broaden authority or create evidence that bypasses controller ordering.

**Alternatives considered**: Provider-managed permits or journals were rejected as duplicated policy.

## Decision 5: Target decision precedes target code

**Decision**: No target-specific package begins until the platform selected-component decision record
is complete and owner-reviewed; execution remains separately permit-gated.

**Rationale**: M0 identified alternatives and evidence gaps but did not establish an owner-supported baseline.

**Alternatives considered**: Choosing the most documented repository was rejected because documentation
does not establish runtime suitability or authorization.
