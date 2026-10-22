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

4. Planning review 1 (2026-10-22, independent read-only): NOT READY. HIGH: (H1) the selection had
    been derived from `examples/zenoh_vehicle.py`, which no example imports at `eef3f717`; the
    running examples publish `ego_vehicle/speed` (int km/h text, default session) and
    `vehicle/status/{throttle,steering,braking}_status` (float text, peer session to a router at
    `:7447`) and the only subscriber (`adas/cruise_control/engage`) prints; no example applies a
    received actuation. (H2) the package required `inheritedHandles: false` while Profile 0.2 has
    the constant `"closed"`; also five actions exactly, `XVERSE-PLAN-…` blocker codes, no
    NOT_AVAILABLE maturity. (H3) eclipse-zenoh Python is 1.9.0 on the 3.13 toolchain and 1.3.4 on
    the system 3.10 user site, not 1.3.4 alone. MEDIUM: G4 overstated (spec 001 has T001–T011
    ticked; only a header lag), `/usr/bin/python3.10` omitted from D4-1, partial delivery
    presented as settled (now decision D4-4), D4-3 engineer-resolvable (now a limitation),
    descriptor dependencies and the router descriptor missing. LOW: `is_plannable`/
    `execution_eligible` are properties; the CLI takes resource files; the digest rejection is a
    catalog-derivation diagnostic; scenario control is derived, not a Note 21 element; chassis
    acknowledgements missing. All verified against the artifacts before repair; every item
    repaired in the thesis package (research.md rewritten; spec, plan, data model, contract,
    quickstart, tasks and inventory patched; revision 2). Brake actuation is now `adapter`
    (blocked until D4-1); only speed and brake status are `supplied`. Second review requested.

5. Planning review 2 (2026-10-22): H1–H3 and M1–M3 resolved; new MEDIUM M5 (dependency edges
    belong to the experiment Profile `dependsOn` on Scenario steps, projection.py:436,518, not to
    Deployment text), M6 (inventory/quickstart strings), M7 (pygame display and operator-input
    dependencies of the selected examples). All verified and repaired in the thesis package
    (revision 3); brake status is now `blocked (unattended)`. Review 3 requested for confirmation.
