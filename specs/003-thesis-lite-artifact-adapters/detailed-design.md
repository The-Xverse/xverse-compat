# Detailed design: Phase 4 compatibility descriptors (owner side)

Planning authority: `distributed_safety_critical_thesis/specs/003-thesis-lite-artifact-adapters/`
(spec FR-001–FR-010, V01–V07, descriptor-admission contract; planning reviews 1–3, READY FOR
DETAILED DESIGN on 2026-10-22). This document maps those requirements onto `xverse-compat` code and
data. It adds no requirement.

## Modules

| Module | Responsibility | Requirements |
| --- | --- | --- |
| `xverse_compat.selection` | Load and validate the artifact-selection record and artifact pins (fail closed); recompute pin digests from local files | FR-001, FR-002, FR-009 |
| `xdl/selection/aeb-sim-selection.json` | The record itself: streams, dispositions, pins, not-selected items, open decisions | FR-001, FR-002 |
| `xdl/descriptors/aeb-sim/*.xdl.yaml` | XDL graph (System, Components, Deployment, Profile) for the selected processes | FR-003, FR-004, FR-005 |
| `xverse_compat.descriptors` | Validate the graph with `xverse_xdl` at the pinned platform revision, derive the catalog, check the admission rules the schema does not cover (committed revision, declared dependencies, blocker codes, stream traceability) | FR-003, FR-004, FR-009 |
| `xverse_compat.contracts` | Contract-verification table: each statement with its evidence reference and status | FR-006 |
| `xverse_compat.adapters.bridge_samples` | Decode recorded bridge samples (`ego_vehicle/speed`; `vehicle/status/*` kept for an attended case) into observation records; reject malformed/stale/duplicate/out-of-range | FR-007 |
| `xverse_compat.admission` | Build the admission record (hashes, platform revision, Phase 1–3 revisions, verification log, blockers, `executionAuthority: absent`) and re-pin `platform-api.lock.json` at admission | FR-008, G5 |

## Data flow

selection record → pins (digests recomputed) → descriptors (validated; catalog derived; blockers
declared, so not plannable; never execution-eligible) → contract table (statements cite the inventory) → fixtures → admission
record. No step starts a selected artifact. Each step is a pure function of files on disk and
returns stable diagnostics (`SelectionError`, `DescriptorError`, … with a code).

## Fail-closed rules (beyond the platform schema)

- Every required stream appears exactly once with one disposition; `supplied`/`adapter` name a
  supplier; `blocked` names a gap id.
- A pin's `sourceRef` carries a 40-hex commit (`…@<sha>`) or the pin is a release artifact with a
  runnable digest; `availability: present` requires `digest` (`sha256:` + 64 hex) and
  `digestCommand`; `NOT_AVAILABLE` requires `reason`.
- Descriptor `artifacts[].digest` equals the pin digest; a binding's `planningBlockers` carry
  `XVERSE-PLAN-THESIS-G<n>` for every open gap that affects it; the `observe` condition names
  observable evidence (RPC reply, sample, file), never a duration.
- Nothing in the code resolves a path by discovery, opens a socket, or spawns a process.

## Limits

Fixture success is not artifact compatibility (Phase 7). The pin set changes with D4-1. The
descriptors describe the committed bridge revision `eef3f717…`, not the dirty working tree.
