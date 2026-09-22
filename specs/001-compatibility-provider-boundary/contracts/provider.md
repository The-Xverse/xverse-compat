# Compatibility Provider Contract

## Authority

The normative catalog, lifecycle, permit, handle, diagnostic, and evidence semantics live in
`xverse-platform/specs/005-component-catalog-compat-runtime/contracts/`. This contract assigns the
implementation boundary in `xverse-compat`; it does not redefine those types.

Before any conformance implementation, the compatibility project pins one exact `xverse-xdl`
package/API version. The current reviewed platform API is `0.4.0`; no floating version, branch name,
or unpinned source reference satisfies the implementation gate. Local development additionally checks
`platform-api.lock.json`, which pins the complete packaged sibling source surface by file count and
SHA-256 tree digest.

## Current action boundary

Current M3 compatibility providers receive an explicit platform `ProcessAction`. The platform's
in-memory fixture is a mechanics proof and does not define an external compatibility action. A
non-process target remains blocked until a separate platform feature defines a typed action and adds
it to the lifecycle plan digest. `None` never means provider-private target configuration.

## Provider assembly

The caller supplies a finite tuple of already constructed provider implementations to an explicit
composition root. Each implementation declares immutable `provider_id` and `provider_kind` values.
Resolution compares both values with the lifecycle plan and must produce exactly one match.

- Zero matches fail before permit consumption or mutation.
- Multiple matches fail as ambiguous before permit consumption or mutation.
- Construction inputs are limited to the selected immutable artifact, reviewed isolation attestation,
  explicit execution root, executable allowlist, and explicit non-secret environment.
- Package entry points, filesystem scanning, environment-variable selection, network discovery,
  process inspection, ports, service names, and fallback providers are prohibited.

## Operations

| Operation | Provider input | Provider output | Required rejection |
|---|---|---|---|
| `start` | Exact `ProcessAction`, execution ID, action ID, timeout | Exact provider-issued ownership handle carrying provider ID/kind | Unsupported provider/action, unpinned target, missing isolation, duplicate conflicting execution |
| `observe` | Exact issued handle, timeout | Declared lifecycle/readiness status | Forged/altered/unknown handle, unavailable observation represented as success |
| `stop` | Exact issued handle, timeout | Idempotent stopped status | Unowned resource, broad process/service cleanup, inferred target |
| `cleanup` | Exact issued handle, timeout | Owned-resource cleanup status | Running/unowned resource, target-wide cleanup |
| `revalidate` | Complete persisted handle | Boolean exact-ownership result | Reconstruction from PID, name, path, port, address, or discovery |

## Responsibility matrix

| Responsibility | Platform | Compatibility provider |
|---|---:|---:|
| XDL validation and catalog derivation | Owns | Consumes selected result only |
| Lifecycle planning and digest | Owns | Does not modify |
| Permit validation and activation | Owns | Never receives permit authority |
| Mutation exclusion and phase ordering | Owns | Obeys one dispatched action |
| Target-specific invocation/observation | Does not infer | Owns for selected target |
| Concrete resource creation | Records result | Owns exact action |
| Ownership handle model | Owns type and semantics | Issues exact populated handle including provider ID/kind |
| Handle validation against provider state | Requires | Owns exact comparison |
| Intent/outcome evidence journal | Owns | Returns public-safe observations only |
| Secret resolution | Deferred | Prohibited in M3 |
| Legacy source changes | Prohibited | Prohibited |

## Failure boundary

Provider failures are stable, fail-closed, and public-safe. Restricted stdout/stderr, paths, addresses,
payloads, and credentials remain outside returned messages. The controller maps provider failure into
the platform lifecycle diagnostic and evidence sequence. A failed action does not authorize retry,
fallback, ambient discovery, broad cleanup, or another target.

## Selection and execution gates

A target implementation requires the completed platform selected-component decision record. Running
that implementation additionally requires the exact platform execution permit. Neither this contract,
a conformance fixture, nor a compiled provider grants target execution authority.

The first target-specific projection is the blocked
[Zenoh/SOME/IP gateway contract candidate](zenoh-someip-gateway.md). Its presence makes the proposed
boundary reviewable but does not satisfy the selected-component, implementation, or execution gates.

## Negative conformance matrix

Each case must prove both the expected failure and the absence of unauthorized mutation.

| Case | Input | Expected result |
|---|---|---|
| C01 | Unknown provider ID | Resolution fails before activation; zero starts |
| C02 | Correct ID, wrong provider kind | Identity mismatch before activation; zero starts |
| C03 | Duplicate exact ID/kind implementations | Ambiguous resolution failure; zero starts |
| C04 | Missing `ProcessAction` for compatibility provider | Action-model failure; no hidden configuration lookup |
| C05 | Relative executable or working directory | Plan/action rejection; zero starts |
| C06 | Executable outside allowlist or working directory outside root | Isolation failure; zero starts |
| C07 | Requested secret-like or absent environment value | Fail closed; no secret resolution or start |
| C08 | Forged handle with altered execution/action/provider/resource field | Observe/stop/cleanup rejected; owned resource unchanged |
| C09 | Repeated matching start/stop | Same resource/terminal state; no duplicate mutation |
| C10 | Concurrent mutation for one catalog/environment identity | One action succeeds and the other is rejected/serialized |
| C11 | Readiness mismatch, unavailable observation, or timeout | `not-ready`, `unavailable`, or timeout; never success |
| C12 | Restart with unverifiable persisted handle | Revalidation false; observation-only/unowned state |
| C13 | Provider failure containing restricted target detail | Stable public-safe failure; restricted detail withheld |
| C14 | Cleanup by name, PID, port, path, or discovery result | Rejected because no exact issued handle exists |
