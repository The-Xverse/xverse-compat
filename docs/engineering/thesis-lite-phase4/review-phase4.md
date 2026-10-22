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

6. Planning review 3 (2026-10-22): M5–M7 and LOW confirmed resolved; M8 (self-consistency) repaired
    by dropping `manual_control_zenoh.py` and the router from the smallest set; the selected set is
    the CARLA 0.9.15 server and `automatic_control_zenoh.py` (speed feed only). Reviewer verdict
    on M8's repair: READY FOR DETAILED DESIGN; DRAFT; NOT READY FOR IMPLEMENTATION. Detailed
    design and the P4-T01/T02 records start here; T03 code follows the owner-side unit specs.

7. P4-T01/T02 increment (2026-10-22): owner-side detailed design and unit specifications
    (specs/003-thesis-lite-artifact-adapters/), `xverse_compat.selection` (fail-closed loader for
    the selection record and pins; digest recomputation that never raises), the record
    `xdl/selection/aeb-sim-selection.json` (pins carla-server present, bridge-auto present,
    carla-python-client NOT_AVAILABLE; eight streams: vehicleSpeed supplied, five adapter streams
    blocked by G1, brakeStatus and wheelSpeedEscStatus blocked by G2), and `tests/test_selection.py`
    (U-SEL-01…12). Result: 12 passed; U-SEL-12 recomputed both present digests from the host
    artifacts (match). `scripts/check_doxygen.py`: documentation validation passed. No artifact
    executed.

8. P4-T03 increment (2026-10-22): descriptor graph `xdl/descriptors/aeb-sim/` (Profile 0.2
    resource, System aeb-sim-host, Components carla-server and bridge-auto, Deployment with the
    carla-server-binding and bridge-auto-binding), `xverse_compat.descriptors` (platform validation
    with the Profile schema from the sibling platform checkout, catalog derivation, owned rules:
    committed/release revision, no duration wording in readiness, declared dependencies, stream
    traceability, G1 blocker on NOT_AVAILABLE dependencies, at least one blocker per plan, digest
    equality with the pins, never execution-eligible), and `tests/test_descriptors.py`
    (U-DSC-01…05 with ten layered negatives). Facts learnt and corrected in the thesis package:
    (a) artifact `sourceRef` must be a URI reference, so the scp-style `git@github.com:` form was
    replaced by `https://github.com/…/carla-simulator-bridge.git@<sha>` in descriptors and pins;
    (b) the platform defines `is_plannable` as blocker-free and `execution_eligible` as always
    false, so Phase 4 plans are "derived with blockers, not plannable, never eligible", not
    "plannable but blocked"; (c) a digest-less bound artifact fails the platform binding gate
    `XDL-BINDING-ARTIFACT-INTEGRITY` before catalog derivation (which rejects it again). The
    bridge binding names `/usr/bin/python3.10` as the candidate interpreter (the bridge recipe's
    own system Python) with blocker XVERSE-PLAN-THESIS-G1 pending D4-1. Result: `pytest tests`
    58 passed, 1 failed (the G5 content-lock test, unchanged); documentation validation passed.

9. P4-T04/T05 increment (2026-10-22): contract-verification table `xdl/selection/aeb-sim-contracts.json`
    (15 statements C-01…C-15; 10 verified with absolute path:line or inventory-hash evidence, 3
    NOT_VERIFIED and 2 mismatch, each with a blocker; rows for G1–G5) loaded by
    `xverse_compat.contracts` (fail-closed: evidence form, unknown hash, missing blocker, gap
    without a row). Two defects found by the tests before commit and repaired: the loader's first
    run rejected C-11 because the inventory held only a 16-hex prefix of the selected example's
    digest (inventory completed, thesis revision 5, full sha256 with its command, vendored as
    `xdl/selection/artifact-inventory-20261022.json`, sha 3dac2eaa…); and the negative test showed
    that an all-digit hash matched the path:line pattern (hash form is now checked first and a
    line reference must be an absolute path). Bridge-sample adapter
    `xverse_compat.adapters.bridge_samples` (declared keys only; int km/h and unit-float decoders;
    range, freshness, per-key sequence uniqueness; no Zenoh import) with the hand-authored fixture
    `tests/fixtures/bridge-samples/ego-speed-hand-authored.jsonl` (no live capture exists; each
    line records its origin). Tests U-CON-01/02 (+1 negative) and U-ADP-01…08. Suite: the only
    failure is the G5 content-lock test; documentation validation passed. `zenohd` 1.10.1
    confirmed from the package database (dpkg), not executed.

10. P4-T06 increment (2026-10-22): `xverse_compat.admission` builds `xdl/selection/aeb-sim-admission.json`
    binding the platform source surface (26 files, def80396…), the `xdl/schemas` and `xdl/profiles`
    trees, the Phase 1–3 revisions (c1fd213cd…, c2997c0f8…, 63f5cb8c7d…) and platform main
    744b66f9c3…, the selection record, the recomputed pins (present pins match), the descriptors
    with their catalog identities and plan digests, the contract table and inventory, the fixture,
    and the verification log; it states `executionAuthority: absent` and lists the blockers
    (RESOURCE-LIMITS-UNAPPROVED, THESIS-G1…G5, THESIS-UNEXECUTED). Building the record re-pins
    `platform-api.lock.json` to the same surface (previous pin kept inside the record), which
    closes G5: run A before the re-pin 73 passed / 1 failed (content lock), run B after it 74
    passed / 0 failed (`verification-20261022-{a,b}.log`); the final record cites run B.
    `verify_admission_record` recomputes every binding and fails closed (U-ADM-04 negatives:
    altered platform surface, altered descriptor hash, authority not absent, foreign platform
    tree). `scripts/admit_phase4.py` reads the revisions with read-only `git rev-parse` and
    refuses a platform checkout whose HEAD is not the named main. Documentation validation passed.
    Next: independent read-only review of the whole candidate (P4-T07), then the acceptance package.

11. Implementation review 1 (2026-10-22, independent read-only): FAIL, no HIGH, four MEDIUM; all
    verified against the artifacts before repair. (M1) the bridge example's license was recorded
    as Apache-2.0; its header is MIT (Intel Labs 2018; only the unselected zenoh_vehicle.py is
    Apache-2.0): corrected in the thesis inventory (revision 6, re-vendored), research.md and the
    pin. (M2) `verify_admission_record` was weaker than its docstring and finding 10 claimed: it
    now recomputes the verification-log hash, compares the on-disk `platform-api.lock.json` with
    the admitted lock (exact key set and values, so the added `platformRevision` key is no longer
    accepted silently), re-derives every descriptor plan and compares digests and blockers, and
    checks the platform revision when the caller names it; the admission script also refuses a
    platform checkout with uncommitted changes in the pinned surface; U-ADM-04 gained the
    wrong-revision, tampered-lock, tampered-log and altered-plan negatives. (M3) record and log
    inconsistencies: the record had been built twice so the superseded 22-file pin was lost; the
    record is rebuilt from the original lock and keeps the superseded pin across rebuilds
    (`previousPlatformLock` 22 files, 7d730f85…); G5 is "repaired in the candidate, closes on
    acceptance and merge", not closed, and the record keeps `XVERSE-PLAN-THESIS-G5` and C-15 as
    mismatch with that wording; finding 9's counts were wrong: the table has 9 verified, 3
    NOT_VERIFIED, 3 mismatch; the selection record and descriptors now cite inventory revision 6.
    (M4) owned rules narrower than the contract: `XVERSE-PLAN-THESIS-UNEXECUTED` is now required
    on every binding and plan; a `path:line` evidence reference is accepted only when the
    inventory hashes that file (`cited_files`, seven files added); the duration pattern covers
    singular units, number words, "after", "elapsed" and "timer". LOW items repaired:
    `releaseArtifact` must be a JSON boolean, `sourceRef` needs a URI scheme, `localPath` must be
    absolute without traversal, `release:` revisions need a digit, bound artifacts' `sourceRef`
    must equal the pin's, payloads over 32 chars and non-finite or future reception times are
    diagnostics. Wording corrected: `/usr/bin/python3.10` is where the recipe's `python3`
    resolves on this host, an inference, not recipe text. Not repaired (recorded): C-09 is a
    universal negative evidenced by the two files that contain subscribers; the platform
    in-memory lifecycle fixture is not exercised with the Phase 4 plans (FR-007 fixtures are the
    owned samples and descriptors). Result after repair: run A (original lock) 75 passed /
    1 failed (content lock), run B (re-pinned) 76 passed; record verified with expected revision.
    Second implementation review requested.

12. Implementation review 2 (2026-10-22, same reviewer): PASS, no open HIGH or MEDIUM; M1–M4
    confirmed resolved with file:line; the rebuilt record checked (superseded pin kept, run B
    cited, blockers listed, vendored inventory equal to the thesis copy, all seven cited-file
    hashes recomputed by the reviewer). Two LOW residuals, both repaired here: the descriptor's
    interpreter note now says `/usr/bin/python3.10` is where the recipe's `python3` resolves on
    this host (inference); `contracts.py` recomputes a cited file's hash at load when the file is
    present (`-DRIFT`). The record was rebuilt (run C, 76 passed) with the review verdict in its
    `review` field; `acceptance` stays null. The reviewer's note that the thesis-side
    `specs/003-…` package is untracked in the thesis repository is carried to the acceptance
    package (thesis commits happen only on the author's request). Candidate state for P4-T07: the
    acceptance package is presented to the author; no merge into `xverse-compat` main, no
    canonical-note change, and no execution of any selected artifact follow from this record.
