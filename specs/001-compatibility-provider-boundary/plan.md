# Implementation Plan: Compatibility Provider Boundary

**Branch**: `001-compatibility-provider-boundary` | **Date**: 2026-09-20 | **Spec**: [spec.md](spec.md)

## Summary

Implement the accepted companion-side boundary against the exact platform lifecycle API using a
controlled in-memory process-action fixture and explicit provider composition root. Prove fail-closed
conformance while preserving separate target-selection and execution gates.

## Technical Context

**Language/Version**: Python 3.11 or newer

**Primary Dependencies**: `xverse-xdl==0.4.0`, locked and content-pinned

**Storage**: In-memory controlled fixture state only; Markdown specification and review evidence

**Testing**: Standard-library `unittest` conformance suite proving C01–C14; Doxygen coverage/build check

**Target Platform**: Local Python test environment; no external target or process

**Project Type**: Compatibility adapter/provider repository

**Performance Goals**: Deterministic bounded tests; timeout behavior proven without external execution

**Constraints**: No completed target selection, target-specific code, subprocess, network access,
secrets, or legacy modification; the SD-0001 contract candidate remains blocked

**Scale/Scope**: One composition root, one controlled in-memory fixture, C01–C14 conformance cases

## Constitution Check

- Production safety: PASS; design reads existing evidence and performs no legacy action.
- Domain neutrality: PASS; the contract contains no automotive-specific platform semantics.
- XDL centrality: PASS; provider ID/kind comes from the existing validated XDL-derived plan.
- Compatibility before migration: PASS; future provider wraps an unchanged external boundary.
- Repository direction: PASS; platform owns neutral lifecycle policy, compat owns target translation.
- Maturity/evidence: PASS; design, fixture conformance, lifecycle, compatibility, and parity remain distinct.
- Reproducibility/public safety: PASS; exact selection fields and withheld evidence rules are required.

Post-design check: PASS. No ADR is needed because ADR-0014 and ADR-0015 already establish the
cross-repository catalog and lifecycle decisions; this feature applies them without changing them.

## Project Structure

```text
specs/001-compatibility-provider-boundary/
├── spec.md
├── clarifications.md
├── research.md
├── data-model.md
├── plan.md
├── quickstart.md
├── analysis.md
├── validation.md
├── tasks.md
├── contracts/provider.md
├── contracts/zenoh-someip-gateway.md
├── contracts/zenoh-someip-interface-projection.md
└── checklists/
    ├── requirements.md
    └── acceptance.md

docs/reviews/
├── 001-compatibility-provider-boundary-design-review.md
├── 002-compatibility-provider-conformance-implementation-review.md
└── 003-zenoh-someip-gateway-contract-review.md

src/xverse_compat/
├── __init__.py
└── provider.py

tests/
└── test_provider_conformance.py

scripts/
└── check_doxygen.py

pyproject.toml
uv.lock
platform-api.lock.json
Doxyfile
docs/doxygen/mainpage.md
```

**Structure Decision**: Keep all target-neutral compatibility code in one small package importing
platform models directly. The composition root receives constructed providers explicitly. The fixture
models the process-action contract in memory and never invokes the declared executable. Target code
remains additionally selection-gated.

## X-Verse architecture gates

Design and authorization gates pass. The target-neutral runtime/test gate applies to T008–T011.
Target compatibility, parity, fidelity, and production gates remain explicit future gates.
