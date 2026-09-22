# Zenoh/SOME-IP gateway provider contract candidate

**Status**: Drafted for review; implementation and execution blocked

**Platform decision**: [`SD-0001`](../../../../xverse-platform/specs/005-component-catalog-compat-runtime/decisions/SD-0001-zenoh-someip-gateway.md)

This contract projects the target-specific provider boundary for the unchanged
`The-Xverse/zenoh2someip_bridge` candidate. It consumes the platform-owned XDL graph and lifecycle
plan. It does not redefine protocol behavior, implement a provider, approve the selected-component
decision, or authorize an external process.

The platform [selection-closure packet](../../../../xverse-platform/specs/005-component-catalog-compat-runtime/evidence/SD-0001-closure-packet.md)
is the single evidence-intake checklist. This repository does not duplicate or privately complete it.
The [interface projection](zenoh-someip-interface-projection.md) records the strongest public contract
supported by static evidence and the limits that still require owner/runtime verification.

## Exact selection

| Field | Required value |
|---|---|
| Catalog identity | `xdl://io.xverse.compat.legacy/deployment/sd0001-gateway-candidate#binding/gateway-process-binding` |
| Provider | ID `zenoh-someip-gateway-provider`, kind `process` |
| Component | `xdl://io.xverse.compat.legacy/component/zenoh-someip-gateway`, version `0.1.0` |
| System | `xdl://io.xverse.compat.legacy/system/zenoh-someip-gateway-system`, version `0.1.0` |
| Deployment | `xdl://io.xverse.compat.legacy/deployment/sd0001-gateway-candidate`, version `0.1.0` |
| Runtime Profile | `xdl://io.xverse.runtime/profile/compatibility-runtime`, version `0.2.0` |
| Source revision | `7c393c9f5a49239c76122486c49cb1993164475c` |
| Artifact | `sha256:6ce98220d1c4997a20d2b85464e7e1550e8347d68c572bfb63586c150f41f946` |
| Candidate plan | `sha256:ccab18b9980cae1be7537cd13be9f3cbd5b2a0e6a3ddae33a3a98a8560a699cf`; blocked |

The provider must accept only the exact platform `ProcessAction` in that plan. It must not discover a
binary, configuration, working directory, environment, peer, interface, or fallback from repository
layout, process state, network state, or provider-private defaults.

## Interface boundary

The public contract contains four directional identities: `zenoh-ingress`, `someip-egress`,
`someip-ingress`, and `zenoh-egress`. They describe the candidate boundary only. Protocol versions,
wire subset, mappings, payload schemas, units, timing, discovery, delivery, and failure behavior remain
unverified or restricted. The provider must not transform payloads beyond the unchanged gateway's
approved artifact behavior or report interface compatibility from process readiness alone.

Static audit now bounds that artifact behavior to four configured forward routes and two reverse
routes, with the transformations and hazards defined in the interface projection. A compiled private
endpoint, native-memory float encoding, digest-only Zenoh version identity, payload-bearing logs,
unreliable events, detached work, and absent graceful-stop/readiness API remain explicit constraints.

## Lifecycle behavior

| Phase | Provider responsibility | Required failure behavior |
|---|---|---|
| Prepare | Validate the exact artifact, staged relative configuration, execution root, executable allowlist, environment allowlist, isolation attestation, and owner-approved external prerequisites. | Reject any mismatch before mutation; perform no discovery or repair. |
| Start | Receive the platform action and start exactly one gateway process with no shell, closed inherited handles, and no ambient environment. Return one exact provider-issued ownership handle. | Reject an unplannable plan, unsupported action, missing limit, or conflicting execution; never start a fallback. |
| Observe | Evaluate only the future owner-approved external probe for both protocol boundaries and the minimal approved message path. | Return unavailable, not-ready, or timeout; never infer readiness from process survival, output text, or a delay. |
| Stop | Revalidate the full ownership handle and apply the future approved bounded signal/escalation policy to that process group only. | Report remaining state after timeout; never stop by executable name, port, path, or ambient PID. |
| Cleanup | Remove only disposable staged resources recorded in the handle and preserve retained evidence. | Reject partial or rediscovered ownership; never scan shared paths or processes. |

The current 30/10/30/10/10-second phase values are unmeasured candidate safety ceilings. They cannot
be treated as accepted service levels until SD-R04 is resolved.

REF-001 reports S-CORE before the gateway, while the revision-pinned current launcher starts the
gateway before S-CORE. The provider must not encode either order until the selected decision supplies
an owner-approved prerequisite and readiness contract.

## Ownership and containment

The maximum provider-owned scope is the one process it creates and disposable files it stages inside
the approved execution root. Zenoh routers, SOME/IP peers, S-CORE containers, AutoVerse, other host
processes, shared ports, physical devices, retained evidence, and every legacy checkout remain outside
its ownership. Host owner, containment owner, resource limits, network boundary, filesystem boundary,
and the matching isolation attestation are unresolved.

## Fail-closed blockers

The target implementation gate remains closed while any of these platform plan blockers exists:

- `XVERSE-PLAN-ARTIFACT-RETENTION-UNAPPROVED`
- `XVERSE-PLAN-ENVIRONMENT-UNPINNED`
- `XVERSE-PLAN-INTERFACE-CONTRACT-UNVERIFIED`
- `XVERSE-PLAN-OWNER-UNASSIGNED`
- `XVERSE-PLAN-READINESS-UNVERIFIED`
- `XVERSE-PLAN-RESOURCE-LIMITS-UNAPPROVED`
- `XVERSE-PLAN-VENDOR-BINARY-DISPOSITION`

Removing a code from XDL requires the corresponding reviewed evidence; changing provider code cannot
resolve it. After every blocker is closed, implementation still needs explicit authorization. Any
later lifecycle action additionally requires a matching unexpired single-use platform permit.

## Evidence and maturity

Returned status and diagnostics must be public-safe and must not expose raw payloads, restricted
mapping/configuration values, private addresses, credentials, or sensitive paths. Exact restricted
evidence retention remains unresolved. Maturity is **target-specific contract candidate; runtime
unverified**. This contract establishes no compatibility, parity, fidelity, safety, performance, or
production-readiness claim.
