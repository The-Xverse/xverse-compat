# Zenoh/SOME-IP gateway contract architecture review

**Date**: 2026-09-21

**Reviewer**: Codex, separate architecture pass at the user's request

**Scope**: Target-specific contract projection, exact platform identity, interface limits, lifecycle,
ownership, isolation, containment, authorization gates, public safety, and maturity.

**Disposition**: Accept the contract as a fail-closed review artifact. Reject provider implementation
or legacy execution while the platform plan contains unresolved blockers.

## Findings

| ID | Severity | Finding / impact | Required disposition | Status |
|---|---|---|---|---|
| ZS-R01 | BLOCKER | Environment identity, accountable host/containment owners, resource limits, and OS isolation attestation are absent. A process provider cannot establish a safe mutation boundary. | Resolve platform SD-R03 and regenerate/review the exact plan. | Open |
| ZS-R02 | MAJOR | Interface versions, wire subset, payload semantics, mappings, timing, discovery, and failure behavior remain unverified or restricted. Process status cannot demonstrate compatibility. | Resolve platform SD-R05 through restricted review and a public-safe contract projection. | Open |
| ZS-R03 | MAJOR | External readiness probe, shutdown escalation, and measured phase limits are not approved. Candidate timeouts are only safety ceilings. | Resolve platform SD-R04 with measurable results and owner-approved outcomes. | Open |
| ZS-R04 | MAJOR | Vendor binaries contain withheld historical paths and system runtime libraries are outside the artifact bundle. | Resolve platform SD-R08 by owner-approved disposition and a pinned environment. | Open |
| ZS-R05 | MINOR | Restricted artifact/configuration/evidence retention location and period are unassigned. | Resolve platform SD-R06 before completing selection. | Open |
| ZS-R06 | ADVISORY | The boundary may later relate to X-COM, whose runtime is not implemented. | Keep the relationship descriptive until its own accepted Spec Kit capability. | Open; non-blocking |

## Static-audit addendum

The later revision-pinned static interface audit and public projection narrow ZS-R02/ZS-R03 but do
not close them. Six selected routes and transformation classes are now documented, along with vsomeip
3.6.1 and unreliable event use. A compiled private endpoint, native-memory float ABI, unknown Zenoh
semantic version, payload-bearing logs, detached work, and absent graceful-stop/readiness API add
concrete environment, portability, evidence, and containment constraints. Provider implementation
remains rejected until the owner-reviewed closure packet resolves them.

## Positive assessment

The contract imports exact platform identities and keeps protocol details out of platform core. It
accepts only an explicit process action, caps ownership at the created process and recorded staged
resources, rejects ambient discovery and broad cleanup, preserves legacy immutability, and clearly
separates structural validity, planning eligibility, implementation authorization, execution permit,
and compatibility evidence.

No document-quality BLOCKER or MAJOR finding was found. The open findings depend on missing external
evidence and owner decisions; editing prose or provider code cannot close them.

## Review checklist

- [X] Exact catalog, provider, resource, source, artifact, and plan identities are recorded.
- [X] Public interface identities are explicit and unknown protocol/payload details remain bounded.
- [X] Prepare/start/observe/stop/cleanup behavior rejects discovery and unowned mutation.
- [X] Legacy checkout and external peers remain outside provider ownership.
- [X] All seven plan blockers map to contract closure evidence.
- [X] Public-safety and maturity claims are bounded.
- [ ] Environment, owners, limits, and isolation attestation are approved.
- [ ] Interface and readiness contracts are verified.
- [ ] Vendor-binary/environment and restricted-retention decisions are approved.
- [ ] Platform selected-component decision receives owner review.
- [ ] Explicit implementation authorization is recorded.

## Conclusion

This artifact advances compatibility T014 but does not complete it: the contract shape is explicit,
while its interface, isolation, readiness, containment, and owner-dependent values remain blocked.
T012–T016 and every execution gate remain open.
