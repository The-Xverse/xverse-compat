# Implementation Plan: Controlled Gateway Rebuild

**Branch**: `002-controlled-gateway-rebuild` | **Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)

## Summary

Implement a Python library and CLI that validate an exact source/patch manifest, export the committed
Git tree into two disposable stages, apply the digest-pinned external patch, execute explicit allowlisted
build steps without a shell, and emit a result only for matching outputs.

## Technical Context

**Language/Version**: Python 3.11 or newer

**Primary Dependencies**: Python standard library and host Git; no new Python dependency

**Storage**: Caller-selected disposable work root; canonical JSON result

**Testing**: Standard-library `unittest` with synthetic temporary Git repositories and builders

**Target Platform**: Linux build host with Git

**Project Type**: Build-time compatibility tooling and CLI

**Performance Goals**: Deterministic validation; two attempts; no long-running process or network use

**Constraints**: No legacy checkout write, target patch publication, shell, ambient executable lookup,
gateway/peer execution, private values, or compatibility claim; directory staging is not OS containment

**Scale/Scope**: One source commit, one patch, up to a small ordered build-step set, one output

## Constitution Check

- Production safety: PASS; only committed source is exported and the source checkout is read-only.
- Domain neutrality: PASS; mechanism is target-neutral despite the first candidate context.
- XDL centrality: PASS; this build tool does not create deployment configuration.
- Standards interoperability: PASS; Git unified diff and SHA-256 are used without semantic replacement.
- Compatibility before migration: PASS; output is an external derivative and legacy remains unchanged.
- Repository boundaries: PASS; build/adapter tooling belongs to `xverse-compat`.
- Maturity/evidence: PASS; reproducibility is distinct from interoperability and runtime evidence.
- Reproducibility/public safety: PASS; exact identities are recorded and restricted contents omitted.

Post-design check: PASS. Platform ADR-0017 records the cross-repository decision before implementation.

## Project Structure

```text
specs/002-controlled-gateway-rebuild/
├── spec.md
├── clarifications.md
├── research.md
├── data-model.md
├── plan.md
├── quickstart.md
├── analysis.md
├── validation.md
├── tasks.md
├── contracts/
│   ├── rebuild-manifest.md
│   └── rebuild-result.md
└── checklists/
    ├── requirements.md
    └── acceptance.md

src/xverse_compat/
└── rebuild.py

scripts/
└── rebuild.py

tests/
└── test_rebuild.py
```

**Structure Decision**: Add one module to the existing package and a thin repository CLI. The target
patch and build outputs remain external inputs/artifacts.

## X-Verse architecture gates

The design and synthetic implementation gates pass. Target patch acceptance, environment, interface,
runtime, compatibility, parity, retention, and execution gates remain open.
