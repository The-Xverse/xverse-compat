# Data Model: Compatibility Provider Boundary

This feature adds no runtime model. It assigns ownership around platform-owned M3 entities.

## Referenced platform entities

| Entity | Owner | Compatibility-provider use |
|---|---|---|
| `LifecyclePlan` | `xverse-platform` | Read exact provider/action/environment and immutable selection data. |
| `ProcessAction` | `xverse-platform` | Receive the only compatibility action supported by current M3. |
| `OwnedResourceHandle` | `xverse-platform` | Populate and return an opaque handle for the exact created resource. |
| `LifecycleResult` | `xverse-platform` | Receive controller-composed lifecycle status; provider returns only action observations. |
| `ExecutionPermit` | `xverse-platform` | Never received or managed by the provider. |
| `EvidenceRecord` / journal | `xverse-platform` | Never written directly by the provider. |

## Compatibility-owned concepts

### Provider implementation

Target-specific code that implements the imported lifecycle protocol. Identity is an exact supported
provider ID/kind pair carried through the plan and every issued handle. It contains invocation and
observation translation only, never domain logic.

### Provider composition root

An explicit finite tuple of already constructed providers supplied by the caller. Resolution compares
the exact plan ID/kind pair, returns exactly one match, and rejects zero or multiple matches. It performs
no package entry-point, filesystem, environment, network, process, port, or service discovery.

### Provider-owned resource table

Restricted in-memory or durable provider state mapping an opaque handle ID to the complete issued
handle and exact external resource identity. Equality over the complete handle, including provider
ID and kind, gates all later actions. If state cannot be revalidated after restart, the provider returns false.

### Conformance case

A target-neutral input/expected-outcome pair testing ownership, idempotency, concurrency, timeout,
readiness, reconciliation, public safety, or failure behavior.

## State ownership

```text
platform plan + activation
          │ exact action
          ▼
compat provider ── creates/observes/stops one selected external resource
          │ exact issued handle + public-safe observation
          ▼
platform controller ── records ordered evidence and lifecycle result
```
