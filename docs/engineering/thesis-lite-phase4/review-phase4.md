# Thesis Lite Phase 4 (compatibility descriptors) — engineering review log

Branch `candidate/phase4-descriptors-20261022` from `e162477`. Planning package (authoritative):
`distributed_safety_critical_thesis/specs/003-thesis-lite-artifact-adapters/`. Findings are numbered
and recorded before any repair. Legacy repositories (CARLA, carla-simulator-bridge, Zenoh) are
read-only throughout; no selected artifact is executed in this phase.

1. Planning package written (2026-10-22): spec (FR-001–FR-010, V01–V07, decisions D4-1–D4-3),
    plan, research with the read-only artifact inventory (review/artifact-inventory-20261022.json),
    data model, descriptor-admission contract, quickstart, tasks. Independent read-only planning
    review requested; T03 code waits for its verdict.

2. Platform content lock is stale (gap G5). `platform-api.lock.json` pins `xverse-xdl` 0.4.0 as a
    22-file tree `7d730f85…`, which matches platform commit `4ed17352b` only. The accepted main
    `744b66f9c` (code tree of `63f5cb8c7`) has 26 files, digest `def80396…`; intermediate commits
    `56506d2c9` (23), `199de0baa`/`c4b8225c1` (24), `0d7ebdde4`/`1f17794e5`/`de6be649b` (26) all
    differ. Consequence: `test_platform_dependency_source_matches_content_lock` fails against the
    accepted main with "platform package file set differs from the reviewed pin". This is the
    situation the scope document anticipates ("an old compatibility manifest does not remain valid
    merely because an additive platform change passes its own tests"). Repair scope: re-pin to
    the accepted main at P4-T06 admission, after review, with the 26-file digest recorded and the
    Phase 1–3 revisions named; no repair before then.

3. Baseline (2026-10-22, worktree at `e162477`, venv `/dev/shm/compat-p4-venv` with the platform
    wheel `xverse_xdl-0.4.0` built from main `744b66f9c`, sha `94fe115e…`, the same wheel identity
    as the accepted Maestro run 22a-1): `pytest tests -q` gives 40 passed, 1 failed; the failure
    is finding 2. The conformance test locates the platform as `ROOT.parent / "xverse-platform"`,
    so the worktrees directory carries a symlink `xverse-platform -> /home/jefferson/xverse-platform`
    (read-only use; not part of the delivery). Host load at the run: 4.4.
