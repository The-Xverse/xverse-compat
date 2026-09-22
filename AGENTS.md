# X-Verse vNext Engineering Rules

## Repository responsibility
Owns external descriptors, compatibility adapters, and deployment glue for unchanged legacy assets. Keep business/domain logic out; no adapters or XDL descriptors are implemented in M0.

## Production safety
Existing The-Xverse repositories are production assets and immutable by default. Unless the user
explicitly authorizes a specific repository and change, do not modify them or create branches,
commits, issues, PRs, tags, CI/CD changes, package/image/API/topic/protocol renames, deployment
changes, or vNext dependencies in them. Read-only inspection is permitted. Integration must use
external XDL descriptors, compatibility adapters, orchestration, public APIs/protocols, or existing
artifacts. Never execute a production workload as part of M0 discovery.

## Architecture
X-Verse is a domain-neutral CPS platform; automotive is a specialization. Dependencies flow:
blueprints → domain profiles → XDL/platform APIs → runtime abstractions. The reverse is prohibited.
Separate logical identity from realization; physical devices are first-class. Prefer standards
interoperability and parallel evolution over replacement. Record major decisions in ADRs before
implementation. XDL is canonical; do not invent competing configuration languages.

## Spec Kit and quality
Read `.specify/memory/constitution.md` and the relevant `.specify/commands/speckit.<stage>.md`.
Use the official workflow and one specification per capability. Commands are agent instructions,
not executable shell scripts. The canonical M0 feature is in xverse-platform; companion setup is
tracked there. Do not duplicate its specification in companion repositories.
Each feature requires acceptance criteria, validation, documentation, compatibility impact,
failure semantics, observable behavior, and an accurate maturity classification. Keep implemented,
partial, target, and exploratory work distinct. Source inspection does not demonstrate runtime success.
Conduct a separate review pass; record findings before repairing them in a subsequent pass.
Each capability must identify applicable REF-002 SADS requirement IDs and preserve an explicit
implemented/partial/allocated/deferred/superseded/conflicting/needs-clarification disposition. The
SADS is target input, not proof that a capability exists.

## Model recommendations
Before each substantive next step, tell the user which model and reasoning effort offer the
best expected cost-effectiveness for that specific task. Consider Terra, Luna (called Lua by
the user), Sol, and Astra; briefly explain the choice and when a cheaper option or escalation
is justified. Distinguish task-based judgment from measured results; do not claim benchmarks
or exact costs without evidence. Verify current pricing when quoting it, and distinguish API
prices from account usage. Do not claim to switch models unless a switch actually occurred.
This recommendation is informational and does not add a new approval gate to authorized work.

## Current boundary
Setup, M0, M1, M2 XDL Core, and capability 004 loader/validator work are approved in
`xverse-platform`. The platform also contains the reviewed M3 prototype catalog, planner, permit,
evidence, exact provider ID/kind ownership boundary, and isolated fixture runtime. This repository's
first feature now implements an explicit composition root and controlled in-memory process-action
conformance fixture against exact platform API `0.4.0`. A target-specific gateway contract candidate
exists, but no target-specific provider, completed legacy selection, execution authorization,
compatibility proof, or parity evidence exists.
Current M3 compatibility actions are process-based; non-process actions require a separate platform
capability. Keep changes local and public-safe.

Capability 002 implements a build-time controlled derivative-rebuild envelope using only synthetic
fixtures. It may verify and build exact source plus an external digest-pinned patch in two isolated
stages, but it must not store restricted patch contents, alter a source checkout, run an output, or
claim runtime compatibility. Supplying an SD-0001 target patch remains human-gated by ACC010.

Platform ADR-0018 now requires platform-first delivery. Target-specific compatibility adapters,
SD-0001 derivative work, legacy execution, and parity are deferred until the main platform capability
baselines and stable extension contracts are accepted. Preserve existing evidence and mechanisms; do
not treat the deferral as rejection or authorization to change a legacy repository.

## Source of truth
The authoritative baseline is `xverse-platform/docs/architecture/XVERSE_VNEXT_ARCHITECTURE_AND_CODEX_GUIDANCE.md`.
The platform owns architectural governance; each companion owns its responsibility above.
No individual maintainers or approval assignments are inferred.

## Platform subsystem names
Refer to platform orchestration as **Maestro**, communication as **X-COM**, and observability as
**Argus**. Their Python namespaces are `xverse.maestro`, `xverse.xcom`, and `xverse.argus`.
Generic XDL/metamodel concepts retain their semantic names. Platform ADR-0016 owns this decision.
