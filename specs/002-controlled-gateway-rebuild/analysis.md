# Specification analysis: Controlled Gateway Rebuild

**Date**: 2026-09-21
**Mode**: Read-only Spec Kit analysis before implementation

## Findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| A01 | Resolved MAJOR | Committing a patch can disclose the removed compiled endpoint and proprietary source context. | Keep the patch external; commit only its digest and public decision metadata. |
| A02 | Resolved MAJOR | Copying a checkout can incorporate dirty or ignored host files. | Export the exact verified commit tree twice. |
| A03 | Resolved MAJOR | A valid patch digest alone does not constrain which files it changes. | Parse patch headers, prohibit unsafe operations, and enforce an exact target allowlist before `git apply`. |
| A04 | Resolved MAJOR | Build commands can become an implicit shell or ambient executable lookup. | Use argument arrays, no shell, an external absolute executable allowlist, and a minimal explicit environment. |
| A05 | Resolved MAJOR | Reproducible compilation could be misread as compatibility or execution approval. | Result schema contains only build identities/digests and the specification preserves all runtime gates. |
| A06 | Resolved MINOR | A single build cannot demonstrate repeated output. | Export, patch, and build twice in independent roots and compare exact outputs. |
| A07 | Open BLOCKER | The actual restricted SD-0001 patch, peer serialization decision, and configuration values are not approved inputs. | Implement/test the envelope only; require T015 before target patch supply and a later permit before any execution. |

## Coverage

| Requirement group | Tasks |
|---|---|
| FR-001–FR-006 input/staging/patch safety | T005, T007–T008 |
| FR-007–FR-010 build/reproducibility/result | T006, T009–T010 |
| FR-011–FR-015 public safety and target gates | T005–T006, T012–T015 |
| FR-016–FR-018 documentation/result/containment boundary | T010–T15 |

Every functional requirement maps to a task. A07 blocks the target patch, not the reusable controlled
fixture implementation authorized in this increment.
