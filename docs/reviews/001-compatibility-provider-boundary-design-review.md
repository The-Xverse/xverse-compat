# Compatibility Provider Boundary Design Review

**Date**: 2026-09-20
**Scope**: `xverse-compat` Spec Kit feature `001-compatibility-provider-boundary` and the concrete
prototype provider API in sibling `xverse-platform`
**Method**: Separate read-only architecture pass after the initial design package
**Initial disposition**: Changes required before design acceptance or provider implementation
**Current disposition**: Repair and re-review complete; no BLOCKER or MAJOR finding remains open

## Finding summary

| Severity | Initially open | Currently open | Finding IDs |
|---|---:|---:|---|
| BLOCKER | 2 | 0 | CP-R01, CP-R02 |
| MAJOR | 2 | 0 | CP-R03, CP-R04 |
| MINOR | 2 | 0 | CP-R05, CP-R06 |
| ADVISORY | 0 | 0 | None |

## Findings recorded before repair

### CP-R01 — Non-process provider actions do not exist in the platform API

**Severity**: BLOCKER

The compatibility design permits `ProcessAction` or a future typed provider action. The concrete
platform `LifecycleProvider.start` accepts only `ProcessAction | None`, and the planner constructs an
action only when `provider_kind == "process"`. A non-process compatibility provider would therefore
receive `None` and need hidden target configuration, contradicting FR-003/FR-004 and the closed-set XDL
boundary.

**Required repair**: Bound current M3 compatibility implementations to explicit `ProcessAction`, or
introduce a separately specified platform-owned typed provider action before any non-process provider.
`None` must never mean target-specific ambient configuration.

### CP-R02 — Provider kind is selected but not enforced at runtime

**Severity**: BLOCKER

`LifecyclePlan` contains `provider_id` and `provider_kind`, but the concrete `LifecycleProvider`
protocol exposes only `provider_id`. `LifecycleController.start` checks only the ID, and later phases
compare the handle's provider ID only. Two providers sharing an ID but representing different kinds
cannot be distinguished by the runtime boundary.

**Required repair**: Make provider kind part of the imported provider identity and exact controller/
handle validation, or remove kind from selection through a reviewed platform contract change. Add
negative tests proving an ID match with a kind mismatch fails before mutation.

### CP-R03 — Provider resolution and construction remain ambiguous

**Severity**: MAJOR

The design rejects discovery and a second registry, but it does not define how the composition root
maps an exact plan provider pair to exactly one implementation or supplies isolated non-secret
construction inputs. A caller could still choose an arbitrary object or introduce an undocumented
factory configuration.

**Required repair**: Define deterministic explicit provider assembly: exact supported identity,
zero-or-one resolution, duplicate/unknown rejection, permitted constructor inputs, and no filesystem,
entry-point, network, or name-based discovery.

### CP-R04 — Platform version pin occurs after generic implementation tasks

**Severity**: MAJOR

Tasks T008–T011 implement and test the imported platform protocol, while T013 pins the platform
contract/package version later in the selected-target phase. This permits conformance work against a
moving prototype API and weakens reproducibility.

**Required repair**: Pin the exact platform API contract before any compatibility conformance code.
Keep the selected legacy artifact pin as a later target-specific gate.

### CP-R05 — The measurable negative-case target lacks a case catalog

**Severity**: MINOR

SC-003 requires at least ten negative conformance cases, but the design names categories without an
enumerated case catalog and stable expected outcomes.

**Required repair**: Add a conformance matrix with at least ten cases, expected failure boundaries,
and ownership/mutation assertions.

### CP-R06 — Repository maturity guidance is stale

**Severity**: MINOR

`xverse-compat/AGENTS.md` and `README.md` still say M2 requires specification and that no platform
runtime/catalog exists. The platform now has an approved M2 package and a prototype M3 fixture runtime.

**Required repair**: Update repository-local maturity text without changing the synchronized constitution.

## Positive assessment

The design correctly assigns target-specific translation to `xverse-compat`, preserves XDL as the
only authored selection model, keeps permits and evidence in the platform controller, forbids secrets
and ambient ownership, separates selection from execution authorization, and makes no compatibility,
parity, fidelity, or production claim. No M0 candidate was selected by inference.

## Repair disposition

| Finding | Resolution evidence | Status |
|---|---|---|
| CP-R01 | The specification and provider contract limit the current compatibility boundary to an explicit platform `ProcessAction`. A non-process target requires a separately specified typed action, and `None` cannot carry provider-private configuration. | Resolved |
| CP-R02 | Platform API `0.3.0` adds immutable provider kind to the protocol and ownership handle. The controller now validates the exact provider ID/kind pair at dispatch, returned-handle validation, later operations, and reconciliation; a wrong-kind test fails before provider mutation. | Resolved |
| CP-R03 | The provider contract defines an explicit composition root over a finite tuple of constructed providers, exact ID/kind matching, zero/multiple-match rejection, bounded constructor inputs, and prohibited discovery mechanisms. | Resolved |
| CP-R04 | T008 now pins the exact `xverse-xdl` package/API version before T009–T011 conformance implementation. The contract identifies the currently reviewed platform API as `0.3.0`; no compatibility code has been written. | Resolved |
| CP-R05 | Contract cases C01–C14 enumerate stable negative inputs, expected failure boundaries, and no-mutation expectations. | Resolved |
| CP-R06 | Repository README and AGENTS guidance now describe the approved M2/prototype M3 platform state and the process-action-only compatibility design. | Resolved |

The repair re-review found no new BLOCKER or MAJOR issue within this design-only scope. The imported
platform version is internally consistent across package metadata, module metadata, lock data,
Doxygen configuration, and CLI output. The platform focused M3 suite passes 20 tests, its complete
suite passes 84 tests, and its fixture validator still records eight public-safe events with
`legacyExecution:false`.

## Review gate

ACC009 is satisfied by the completed repair and re-review. ACC010 remains open for explicit human
design acceptance. Provider implementation requires its separate authorization and the T008 exact
dependency pin. Target selection and legacy execution remain separate later gates; this review
selects no M0 candidate and grants neither authority.
