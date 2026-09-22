# Tasks: Compatibility Provider Boundary

**Input**: Design documents in `specs/001-compatibility-provider-boundary/`

## Phase 1: Spec Kit design package

- [X] T001 Create the companion repository's first Spec Kit feature pointer and specification.
- [X] T002 Record clarification decisions and research for contract ownership and selection gates.
- [X] T003 Define referenced entities and the platform/compat responsibility boundary.
- [X] T004 Define provider operations, exact-handle rules, failures, and gate semantics.
- [X] T005 Map requirements to tasks and complete cross-artifact analysis.

## Phase 2: Separate design review

- [X] T006 Conduct the separate architecture review and record findings before repair.
- [X] T007 Repair all BLOCKER and MAJOR findings, rerun checks, and record validation.

## Phase 3: Target-neutral implementation

- [X] T008 Pin `xverse-xdl==0.4.0` in the package/uv lock and content-lock its complete local source surface.
- [X] T009 Create conformance tests using only a controlled in-memory compatibility fixture.
- [X] T010 Implement the imported process-action provider protocol without copying platform models.
- [X] T011 Prove the C01–C14 matrix, including exact identity/handles, idempotency, exclusivity,
  timeouts, readiness, reconciliation, public safety, and no direct permit/journal authority.

## Phase 4: Selected target gate

- [ ] T012 Obtain an owner-reviewed platform selected-component decision with every required field.
  Platform SD-0001 pins the Zenoh/SOME/IP candidate identity and artifact, but its owner-dependent
  blocking findings remain open.
- [ ] T013 Pin the selected immutable target artifact and its public-safe provenance.
  Platform SD-0001 now pins a reproducible candidate archive, but target-owner acceptance, durable
  retention, and selected-decision T012 remain prerequisites for completing this task.
- [ ] T014 Specify target-specific interface, lifecycle, isolation, and containment behavior. A
  reviewed draft now fixes the exact boundary and fail-closed behavior; unresolved interface,
  environment, readiness, owner, limit, retention, and vendor-binary evidence prevents completion.
  The platform closure packet is the authoritative evidence-intake checklist. A static public
  interface projection is drafted, but restricted owner/peer review and runtime evidence remain absent.
- [ ] T015 Obtain explicit authorization before implementing the target-specific provider.
- [ ] T016 Implement and test the selected provider without modifying a legacy checkout.
- [ ] T017 Obtain an exact execution permit before any selected legacy lifecycle action.

## Phase 5: Evidence and acceptance

- [ ] T018 Record selected lifecycle evidence and limitations without compatibility/parity inflation.
- [ ] T019 Complete final M3 cross-repository review and human acceptance before M4.

## Dependencies

T001–T005 precede design review. T006 precedes T007. The user authorized T008–T011 on 2026-09-20;
T008 precedes T009–T011. T012–T15 precede target code. T016 precedes T017, and T017 precedes any legacy action.
T018–T019 require selected-target evidence; fixture evidence cannot satisfy them.
