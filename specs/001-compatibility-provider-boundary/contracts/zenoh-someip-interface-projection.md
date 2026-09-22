# Zenoh/SOME/IP candidate interface projection

**Status**: Static contract candidate; interoperability unverified

**Evidence**: Platform [SD-0001 static interface audit](../../../../xverse-platform/specs/005-component-catalog-compat-runtime/evidence/SD-0001-static-interface-audit.md)

This public-safe projection constrains a future provider around the exact SD-0001 artifact. It does
not reproduce restricted route identifiers or configuration, alter the legacy gateway, define a new
payload format, prove compatibility, or authorize implementation/execution.

## Provider-visible boundary

- One process consumes an exact platform `ProcessAction` and the pinned candidate bundle.
- Four configured Zenoh→SOME/IP routes and two configured SOME/IP→Zenoh routes exist.
- Exact keys, service/instance/event-group/event identities, addresses, ports, and mappings remain in
  restricted evidence.
- The provider must not parse, transform, discover, or replace message payloads. All candidate message
  behavior belongs to the unchanged gateway artifact.
- The provider may expose only public-safe lifecycle/readiness results; raw target logs must be
  discarded or retained only under an approved restricted policy.

## Static protocol limits

| Concern | Candidate boundary |
|---|---|
| Zenoh identity | Exact library digest is pinned; semantic version is unavailable. |
| Zenoh connection | Client mode with one compiled-in private endpoint; no selected external configuration input exists. |
| SOME/IP identity | Bundled vsomeip file version 3.6.1, SONAME major 3; peer compatibility unverified. |
| Discovery/transport | Service discovery uses UDP; selected event request/offer operations use unreliable reliability. |
| Forward payloads | Three float32-related routes and one one-byte boolean route; float encoding is host-native and lacks a portable byte-order/ABI schema. |
| Reverse payloads | Two routes forward SOME/IP payload bytes unchanged to Zenoh. |
| Special timing | One forward route schedules a 100 ms zero-reset pulse and suppresses certain duplicates. This source behavior is not a platform retry/readiness policy. |
| Delivery behavior | Loss, order, duplication, reconnect, acknowledgement, congestion, and queue/backpressure behavior are unverified. |

## Readiness contract required before implementation

A future approved external probe must establish all of the following within bounded time:

1. the approved Zenoh peer is reachable through the pinned network boundary;
2. the approved SOME/IP service/instance/event groups reach the required availability state;
3. one approved forward input produces the expected SOME/IP event bytes;
4. one approved reverse event produces the expected Zenoh payload bytes;
5. echo suppression prevents a gateway-origin publication from re-entering the forward path;
6. invalid payload, unavailable peer, loss, timeout, and process exit produce classified failure;
7. stop/containment leaves no provider-owned process and records any outstanding detached work.

Process survival, console text, service availability alone, or a fixed delay cannot satisfy readiness.
The probe peers, payloads, identifiers, capture location, and expected bytes must be separately pinned
and owner-approved.

## Implementation prohibitions

The future provider must not:

- override or infer the compiled endpoint, routes, peer identities, or payload formats;
- expose raw logs, identifiers, payloads, addresses, or configuration in public diagnostics;
- claim portable float interoperability without a reviewed ABI/serialization decision;
- claim graceful shutdown from process termination alone;
- build or invoke the source test tools unless they become separately pinned approved artifacts;
- remove the interface/readiness/environment blockers based on this static projection.

This projection advances compatibility T014 but cannot complete it until the target owner approves
the restricted mapping, peer contract, environment, readiness probe, shutdown behavior, and evidence
handling.
