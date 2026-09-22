# Tasks: Controlled Gateway Rebuild

**Input**: Design documents in `specs/002-controlled-gateway-rebuild/`

## Phase 1: Spec Kit design package

- [X] T001 Create the feature pointer, specification, requirements checklist, and clarifications.
- [X] T002 Record research, data model, manifest/result contracts, implementation plan, and quickstart.
- [X] T003 Record platform ADR-0017 before implementation.
- [X] T004 Analyze cross-artifact coverage and constitution alignment.

## Phase 2: Controlled fixture tests

- [X] T005 Write manifest validation, source identity, path, patch, environment, and command tests.
- [X] T006 Write two-stage reproducibility, mismatch, failure, and source-immutability tests.

## Phase 3: Rebuild mechanism

- [X] T007 Implement strict models, canonical digests, and public-safe errors in `src/xverse_compat/rebuild.py`.
- [X] T008 Implement exact Git identity/export and patch validation/application without source writes.
- [X] T009 Implement allowlisted no-shell build attempts and deterministic output comparison.
- [X] T010 Implement the thin CLI in `scripts/rebuild.py` with atomic result writing.

## Phase 4: Documentation and review

- [X] T011 Extend Doxygen inputs/documentation and package exports for the rebuild mechanism.
- [X] T012 Run tests, lock/prerequisite, compile, Doxygen, placeholder, link, and public-safety checks.
- [X] T013 Conduct a separate architecture review before repairing any findings.
- [X] T014 Repair BLOCKER/MAJOR findings and record final validation.
- [ ] T015 Obtain human acceptance before supplying an SD-0001 restricted patch.

## Dependencies

T001–T004 precede code. T005–T006 precede T007–T010. T011–T012 follow implementation. T013 is a
separate review pass; T014 follows that review. T015 remains a human gate and does not authorize target
execution.
