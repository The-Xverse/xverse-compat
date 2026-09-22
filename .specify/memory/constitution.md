<!--
Sync Impact Report: 2.0.0 → 2.1.0 (SADS traceability obligation, 2026-09-21).
Modified: Capability acceptance gates and Development workflow now require explicit disposition of
applicable REF-002 SADS requirements and complete the platform-baseline component list.
Added: public-safe SADS requirement allocation and conflict/deferment rules.
Removed: none.
Updated: spec-template.md and tasks-template.md in all three repositories; ADR-0018 and the platform
SADS traceability register identify simulation/FMI, UI/results, and security baselines explicitly.
Reviewed: plan-template.md and bundled generic commands; no further changes needed.
Deferred: each allocated SADS requirement still requires its own accepted Spec Kit capability.
-->
# X-Verse vNext Constitution

## Core Principles

### I. Production safety
Existing The-Xverse repositories MUST remain read-only dependencies unless the user explicitly
names an authorized repository and change. Do not create branches, commits, issues, PRs, tags,
CI changes, API changes, deployment changes, or vNext dependencies in legacy repositories.
Only the three new vNext repositories are implementation destinations for this program.

### II. Domain neutrality
The platform core MUST represent multi-industry cyber-physical systems. Automotive terminology
and behavior MUST live in domain profiles, adapters, or blueprints, not core semantics.

### III. XDL centrality
XDL MUST be the canonical versioned system/deployment/experiment representation. Future XDL
work MUST start with a semantic model and YAML/JSON schemas, not a custom grammar or unrelated
configuration language. No XDL implementation is authorized by M0.

### IV. Standards interoperability
Integrate existing standards through references, bindings, and adapters. Any replacement or
reimplementation of SysML, UML, SSP, FMI, or protocol semantics MUST have a documented need and ADR.

### V. Logical and physical separation
Logical identity MUST remain separate from realization and environment-specific deployment.
A device's identity MUST survive a change between simulated, virtual, physical, and hybrid realization.

### VI. Physical hardware as a first-class concern
Execution contracts MUST account explicitly for physical devices and hybrid experiments,
including lifecycle and failure semantics. Concrete tools are providers, not core primitives.

### VII. Platform foundations before compatibility and migration
Implement and accept the main domain-neutral platform components and their stable extension contracts
before implementing integrations with legacy organizational repositories. Legacy integrations MUST
then consume public protocols, APIs, executables, and artifacts through external compatibility
boundaries, and MUST precede any migration or replacement claim. Do not require production repository
restructuring or infer legacy compatibility from an owned platform fixture.

### VIII. Blueprint isolation and repository boundaries
Dependencies MUST flow from blueprints through domain profiles and XDL/platform APIs to runtime
abstractions. Reverse dependencies are prohibited. Use only xverse-platform, xverse-compat, and
xverse-blueprints initially; additional repositories require an independent lifecycle and ADR.

### IX. Explicit fidelity and maturity
Every claim MUST distinguish implemented/demonstrated, partial/under stabilization, architectural
target, and exploratory/PoC. Documentation and source inspection are not runtime verification.
Simulation, network, and timing fidelity MUST be declared and backed by evidence.

### X. Reproducibility and traceability
Record versions, source revisions, environment assumptions, observations, and evidence gaps.
Facts MUST be distinguishable from inference and unknowns. Public documentation MUST summarize
private implementations without copying proprietary source, secrets, or sensitive infrastructure.

## Capability acceptance gates
Every capability MUST have a specification, acceptance criteria, appropriate tests/checks,
documentation, compatibility impact, failure semantics, observable outcomes, and an accurate maturity
label. Major architectural decisions MUST have ADRs before implementation. Apply architecture,
compatibility, runtime, test, reproducibility, and documentation gates. For documentation-only M0,
runtime checks are explicitly not applicable; coverage and evidence validation are required.
Each capability MUST identify every applicable REF-002 SADS requirement ID and mark it implemented,
partial, allocated, deferred, superseded, conflicting, or needing clarification. A target requirement
is not implementation evidence, and no requirement may disappear silently when scope is divided.

## Development workflow
Use one Spec Kit specification per capability: constitution → specify → clarify → plan → tasks →
analyze → implement → separate architecture review. The platform owns the cross-repository M0
specification. All three repositories keep synchronized constitutional rules.
M0 covers setup and read-only inventory only. Human review of boundaries, classifications,
interfaces, and dependencies precedes M1. Metamodel, XDL, orchestration, adapters, and later
milestones remain targets until separately implemented and validated.
Platform-owned core, runtime, Maestro, simulation/model execution and FMI boundaries, X-COM, devices,
time, faults, Argus, security, results, UI, SDK, and CLI capability baselines MUST be accepted before
target-specific legacy adapter or parity work resumes.

## Governance
The approved architecture guidance in xverse-platform is the authoritative architectural baseline.
Explicit user instructions take precedence; record any authorized deviation and its impact.
Amendments MUST document the reason, impact, and synchronized changes to affected constitutions,
agent rules, templates, and specifications. Use semantic versioning: major for incompatible
principles, minor for added obligations, patch for clarifications. Review every capability against
this constitution and classify architecture findings as BLOCKER, MAJOR, MINOR, or ADVISORY.

**Version**: 2.1.0 | **Ratified**: 2026-09-20 | **Last Amended**: 2026-09-21
