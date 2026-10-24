# Review log: Phase 8 WP-01, evaluation observer v2 (xverse-compat)

Candidate `candidate/phase8-wp01-ground-truth-observer-20261024`, base main `9d1f3f3` (tag
`xverse-lite-v1.0.0-rc.1`). Specification: thesis `specs/002-assured-aeb` rev 3g,
`implementation-plan.md` WP-01 (GA-07) and code facts K-1 to K-15, `decisions.md` §H (first
increment, under the author's delegation of 2026-10-24, flagged for the author's review). The
requirements are FR-021, FR-028 and FR-037 and the canonical-note decision DYN-002 (runtime safety
mechanism separated from evaluation ground truth). Findings are recorded before repairs. The maturity
is an engineering increment verified on owned fakes only: not M1, not AEB evidence, live behaviour
unverified (E8-3a).

## Findings

1. **Design record: evaluation observer v2 (2026-10-24, before any code).**
   - **Scope.** Extend the passive observer `src/xverse_compat_carla/observe.py` (K-6) from one role to a
     declared set of roles: the ego (`xverse-lite-ego`), the WP-02 target (`xverse-lite-target`) and any
     other owned role with the `xverse-lite-` prefix (`scenario.ROLE_PREFIX`, K-7). The in-adapter
     ground-truth export stays refused for a live source (`main.py` 82–84; `sources.py` 225,
     `actors=None`): this increment does not touch `main.py`, `sources.py`, `protocol.py` or
     `groundtruth.py`.
   - **Process and passivity (unchanged from v1).** The observer is its own CARLA client process. It calls
     only `Client`, `set_timeout`, `get_world`, `get_map().name`, `wait_for_tick`, `get_actors()`,
     `WorldSnapshot.find` and, for vehicle roles, `get_control()`. It never ticks, never applies settings,
     never applies control, never spawns and never destroys an actor. The adapter remains the only tick
     owner and actuator writer ([A7] 36–38).
   - **Invocation.** A new repeatable option `--track ROLE` selects v2, mutually exclusive with `--role`;
     exactly one of the two is required. Each tracked role must match `xverse-lite-[a-z0-9-]+`, and
     duplicates are refused (argument error, exit 2). The restriction to the owned prefix makes v2
     observe owned actors only; the baseline harness, whose legacy role is `ego_vehicle`, stays on v1.
   - **Output schema `xverse-compat.evaluation-observer/2` (JSON Lines, evaluation-only).**
     - Header: `header: true`, `schema`, `evaluationOnly: true`, `groundTruth: true`, a `label`
       ("EVALUATION-ONLY GROUND TRUTH: never a runtime input (DYN-002; FR-021)"), the declared `roles`
       in order, the `clock` declaration, the `map` name, the `passive` declaration (no tick, settings,
       control, spawn or destroy), `startedWallNs` and `startedMonotonicNs`.
     - One record per received frame: `frame`, `simElapsedS`, `simElapsedNs`, `simDeltaS`,
       `observerMonotonicNs` and `roles`, an object with one entry per declared role.
     - Role entry, observed: `status: "observed"`, `id`, `typeId`, `location` [m], `rotationDeg`
       (pitch, yaw, roll), `velocity` [m/s], `acceleration` [m/s²], `speedMps`, `accelForwardMps2`
       (projection on the forward vector, as v1) and, for a `vehicle.*` actor only, `cachedControl`
       (labelled as in v1: the control reported to the observer client, not an actuator measurement).
     - Role entry, not observed: `status` is `absent` (no live actor carries the role), `ambiguous`
       (several do; their `ids` are listed, none is chosen), `not-in-snapshot` (the actor is not in that
       frame's snapshot) or `non-finite` (a state value is NaN or infinite; no value is written).
     - Footer: `footer: true`, `schema`, `frames`, `tickTimeouts`, `observedFrames` per role, `stoppedBy`
       (`duration`, `SIGTERM`, `SIGINT` or `error`), `error` (null or one line) and `endedMonotonicNs`. A
       file is complete only with a footer whose `stoppedBy` is not `error`.
   - **Clock.** Records are keyed by the simulation frame (`snapshot.frame`) and the simulation time
     (`snapshot.timestamp.elapsed_seconds`, `delta_seconds`): the simulator clock is the canonical clock
     (note [N] 866). `simElapsedNs` uses the single compat `seconds_to_ns` rule (`timeconv.py`), which is
     the rule of the adapter items' `originNs` and of the offline export's `elapsedNs`, so an offline oracle
     joins runtime evidence and ground truth on `frame` exactly. `observerMonotonicNs` is the observer's
     receipt time, recorded for diagnosis only and never a join key. A passive client can miss frames;
     gaps are visible in `frame` and are not filled.
   - **Never reaches a runtime unit (FR-021, DYN-002).**
     - Separate process: `observe` is an entry point only. No module under `src/` imports it; the Phase 7
       adapter check and the blueprint harness launch it as a subprocess.
     - No import by runtime units: the transitive in-repository import closure of the runtime entry
       modules (`xverse_compat_carla.main`, `xverse_compat.live.driver`, `xverse_compat.live.stimulus`,
       `xverse_compat.live.loop`) excludes `xverse_compat_carla.observe`. The observer imports only the
       standard library, `carla` and `.timeconv`: no transport (socket, Zenoh, subprocess) and nothing of
       `xverse_compat` or `xverse_xdl` (`protocol.FORBIDDEN`).
     - No flow: the observer writes no protocol message and nothing on standard output. The runtime flows
       stay the four of `protocol.FLOWS` and `carla_client.FLOWS`, no XDL descriptor declares an observer
       flow, and the runtime intake `carla_client.parse_outbound` refuses every v2 line under both
       protocol identifiers.
     - Separate output path: v2 creates `--out` exclusively (`open(..., "x")`), so an existing path,
       including a FIFO, a socket or `/dev/stdout`, is refused and never written. The harness chooses a
       path under the run directory that it does not pass to any runtime unit.
   - **Failure behaviour (v2, fail-closed).**
     - Argument errors: exit 2 before any connection or file.
     - Connection or world failure: one stderr line, exit 3, no output file.
     - Existing output path: one stderr line, exit 3, the existing path untouched.
     - A tick timeout (`wait_for_tick` `RuntimeError`): counted in `tickTimeouts`, observation continues
       to the duration bound, as v1.
     - Any other exception after the header: a best-effort footer with `stoppedBy: "error"`, one stderr
       line, exit 3. Lines are serialized with `allow_nan=False`.
     - An actor that dies is resolved again on the next frame; a role is resolved again while it is
       `absent`, `ambiguous` or dead.
   - **Backward compatibility.** `--role ROLE` keeps the v1 code path and its output schema unchanged:
     the `ego` record and its members, the header and the footer read by blueprint `report.py` and
     `soak/audit.py`, the truncating open and the exit status. The Phase 7 and S1 harness
     (`run-live.sh` `--role xverse-lite-ego`, `run-baseline.sh` `--role ego_vehicle`) and
     `xverse_compat.live.adapter_check` are unchanged. A v1 characterization test pins this.
   - **Tests (offline, fake `carla` in `sys.modules`, fake world in the `tests/live/test_phase7_live.py`
     style), in `tests/carla/test_observe_v2.py`.**
     - v1 characterization: the record members and values for one role, unchanged.
     - v2 schema: header label and clock declaration; per-frame entries for ego, target and an extra
       owned role; the `absent`, `ambiguous`, `not-in-snapshot` and `non-finite` statuses; `simElapsedNs`
       equals `seconds_to_ns`; footer counts.
     - Passivity: the fake world and actors raise on `tick`, `apply_settings`, `spawn_actor`,
       `try_spawn_actor`, `destroy` and `apply_control`; a v2 run completes without calling them.
     - Failure: connection failure (exit 3, no file), existing output path (exit 3, untouched), an error
       after the header (error footer, exit 3), tick timeouts counted, SIGTERM footer.
     - Arguments: `--role` with `--track`, neither, a duplicate, a role outside the owned prefix.
     - Separation: the AST import checks above; `parse_outbound` refuses each v2 line; nothing on stdout;
       `FLOWS` unchanged; the live `--ground-truth` refusal still holds (existing test
       `test_n2_live_ground_truth_export_is_refused_before_binding`).
   - **Out of scope here.** The blueprint wiring (`run-live.sh`, `lib-live.sh`) of WP-01 is a separate
     `xverse-blueprints` increment, and the live check belongs to E8-3a.
2. **Implementation of finding 1 (2026-10-24).**
   - **Change.** `src/xverse_compat_carla/observe.py` only. `main` parses the mutually exclusive `--role`
     (v1) and repeatable `--track` (v2) options and dispatches. The v1 body moved unchanged into
     `_observe_v1`; its diff is the docstring and the `--role` option line only. v2 is `_observe_v2`,
     with `_entry` for one role and `_line` (`allow_nan=False`). The module imports the standard library,
     `carla` (lazily) and `.timeconv`. `main.py`, `sources.py`, `protocol.py` and `groundtruth.py` are
     unchanged, so the live `--ground-truth` refusal stands.
   - **Tests.** `tests/carla/test_observe_v2.py`: 24 tests, offline, with a fake `carla` module in
     `sys.modules`, a fake world, `ActorList` and actors whose mutating methods raise, and the observer's
     signal handlers captured instead of installed.
     - v1: `test_wp01_v1_role_schema_is_unchanged` pins the header, record (`ego` members and values) and
       footer members; `..._existing_output_is_still_truncated`.
     - v2 schema: `..._header_labels_ground_truth_and_declares_clock_and_passivity`,
       `..._records_every_declared_role_per_simulation_frame` (ego, target and the camera role;
       `simElapsedNs == seconds_to_ns`; one actor listing while every role stays alive),
       `..._absent_ambiguous_not_in_snapshot_and_non_finite_are_never_guessed`,
       `..._resolves_a_role_again_after_its_actor_dies_or_appears`.
     - Passivity: `..._never_mutates_the_world_or_any_actor` and the AST check
       `test_wp01_observer_source_calls_no_mutating_carla_method`.
     - Failure: connection failure (exit 3, no file); an existing path and `/dev/stdout` refused (exit 3,
       untouched); a lost server after the header (error footer, exit 3); a non-finite simulation clock
       (error footer, exit 3); tick timeouts counted; duration 0 ends with `stoppedBy: "duration"`; six
       argument errors exit 2 before any connection or file.
     - Separation: `test_wp01_no_runtime_unit_imports_the_observer` (AST import closure of
       `xverse_compat_carla.main`, `xverse_compat.live.driver`, `.stimulus`, `.loop`),
       `test_wp01_no_module_imports_the_observer` (all of `src/`),
       `test_wp01_observer_imports_no_transport_and_nothing_forbidden` (exact import set),
       `test_wp01_runtime_intake_refuses_every_observer_line` (`parse_outbound` under both protocol
       identifiers; standard output empty) and `test_wp01_runtime_flows_carry_no_ground_truth` (both
       `FLOWS` constants; no XDL file names the observer or its schema).
   - **Mutation checks (not committed).** An injected `from xverse_compat_carla import observe` in
     `xverse_compat/live/loop.py` failed the two import tests; an injected `world.tick()` in the v2 loop
     failed 8 tests, among them the passivity and AST tests. Both files were restored.
   - **CPython 3.10.** Under `env -i ... /usr/bin/python3.10 -s -B` (3.10.12) the module imports with
     `protocol.forbidden_modules_loaded() == []` and without loading `carla`; an off-prefix `--track` is
     refused by argparse.
   - **Suite.** `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src
     /dev/shm/compat-p6-venv/bin/python -m pytest tests -q -p no:cacheprovider`: 268 passed, 39
     subtests (baseline 244 at `9d1f3f3`).
   - **Residuals.**
     - R-1. Live behaviour is unverified: the v2 role resolution, snapshot `find` and frame coverage on a
       real server belong to E8-3a. No CARLA was run.
     - R-2. The blueprint wiring of WP-01 (`run-live.sh`, `lib-live.sh`: a `--track` observer with its own
       output path beside or instead of the v1 observer) is a separate `xverse-blueprints` increment.
       Until then the harness runs v1 only.
     - R-3. The separation is enforced by process, import, flow and output-path construction, not by the
       operating system: runtime units run as the same user and could open the file if given its path.
       The V14 data-provenance audit (WP-17) and the harness's path choice cover this.
     - R-4. Ambiguity is detected only when a role is resolved. A second actor that takes a role while
       the first stays alive is not detected; WP-02 owns the spawn of a unique `xverse-lite-target`.
     - R-5. A passive client can miss frames when it is slower than the tick owner. Gaps show in `frame`
       and are never filled; the oracle (WP-17) must declare how it treats them.
     - R-6. The observer reads the same `World.get_snapshot` source as the adapter's `vehicle-motion`
       flow (C-12). AD-32 resolves this on the runtime side with the modelled motion sensor (WP-05), not
       here.
     - R-7. The package docstring of `xverse_compat_carla/__init__.py` says `carla` is imported only in
       `sources.LiveSource`; `observe.py` already imported it in v1. The docstring is left unchanged
       (pre-existing, LOW).
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 10:36:21).**
   - **Reviewer and method.** An independent reviewer who did not write the code. Read `37d3452` and
     `ff67fbc` against base `9d1f3f3`, the thesis `specs/002-assured-aeb` WP-01, K-1 to K-15, FR-021,
     FR-028, FR-029, FR-037, V14 and `decisions.md` §H, and the blueprint consumers at main `99df3a4`.
     The offline suite was run, along with a CPython 3.10 import check and one mutation probe in a scratch
     copy. The worktree was not changed except for this entry. No CARLA, no live run.
   - **Verdict: PASS WITH NOTES.** No issue blocks the merge. The engineering-increment maturity stated
     in the preamble (owned fakes only, not M1, live unverified under E8-3a) stands.
   - **Evidence.**
     - Suite: 268 passed, 39 subtests, matching finding 2.
     - CPython 3.10.12 (`env -i PATH=/usr/bin /usr/bin/python3.10 -s -B`, cwd `src`): `observe` imports
       with `protocol.forbidden_modules_loaded() == []`, and `carla` is not loaded.
     - v1 is unchanged. The base `main` body from `stop = []` to `return 0` is byte-identical to
       `_observe_v1` (observe.py 72–113), apart from the new `def` line and its docstring.
       - `report.py` `observer_metrics` (59–76) reads `ego`, `elapsedS`, `deltaS`, `ego.speedMps`,
         `ego.location`, `ego.accelForwardMps2` and `ego.cachedControl.{brake,throttle}`.
       - `soak/audit.py` `actuator_safe_stop` (111–150) reads `frame`, `monotonicNs`, `ego` and the
         footer's `stoppedBy`; its `cleanStatus` (167) needs `observer=0`.
       - `run-live.sh` 99–100, `run-baseline.sh` 78–79 and `adapter_check.py` 53–55 run
         `-m xverse_compat_carla.observe --role …` from `src`, so the new relative import `.timeconv`
         resolves.
       - The truncating open and the exit status are kept. Only argparse's wording for a missing
         `--role` changes, and it still exits 2. No consumer reads that text.
     - Clock: `simElapsedNs` is `seconds_to_ns(snapshot.timestamp.elapsed_seconds)` (observe.py 207).
       This is the rule of `items.py` 39 and of the vehicle-motion origin (`protocol.py` 130 from
       `sources.py` 223), and of the export at `protocol.py` 233. The test value 5.05 s catches the naive
       `int(s * 1e9)`.
     - Role resolution (observe.py 190–205) matches the record:
       - one live actor gives `observed`;
       - several give `ambiguous`, with sorted ids, none chosen, and the role is resolved again;
       - none gives `absent`;
       - an actor missing from the snapshot gives `not-in-snapshot`;
       - a non-float or non-finite state or control value gives `non-finite`, and no value is written.
       Each status has a test.
     - Fail-closed paths:
       - connect or map failure: exit 3, no file;
       - an existing output, including `/dev/stdout`: `O_EXCL` refuses it, the file is untouched, exit 3;
       - an error after the header: error footer, exit 3;
       - a non-finite or negative simulation clock: `seconds_to_ns` raises and `allow_nan=False` holds,
         giving an error footer and exit 3.
     - The passivity fakes are effectively an allow-list. `World` and `Actor` raise on any undefined
       attribute, and the client is a two-member `SimpleNamespace`, so any new CARLA call on a path the
       tests exercise fails them. That includes the tick-timeout branch.
     - The XDL scan is not vacuous: six JSON files under `xdl/`.
   - **Issues.**
     - **MEDIUM-1: "complete" does not bound coverage, and a lost server is not fail-closed.** Not
       blocking; it needs a recorded residual.
       - Where: observe.py 184–188 and 211–213; record finding 1, "Footer" and "Failure behaviour".
       - Every `wait_for_tick` `RuntimeError` counts as a tick timeout. A server that stops responding
         while every role is resolved therefore never reaches `get_actors()`, because `is_alive` reads
         local episode state.
       - The observer then runs to the bound or to SIGTERM. It exits 0 with `error: null` and a footer
         that meets the record's definition of complete. Only `tickTimeouts` shows the loss. Trailing
         timeouts leave no `frame` gap, so R-5 does not reveal them.
       - This is inherited from v1, and a paused tick owner (the restore guard) legitimately produces
         timeouts, so I propose no code change.
       - Proposed R-8: a v2 file is complete only as a record. Coverage, meaning frame continuity over the
         evaluation window and `tickTimeouts`, is an oracle (WP-17) acceptance criterion that must be
         declared there.
     - **MEDIUM-2: no actor extent is recorded for the FR-037 oracle, and no residual says where it will
       come from.** Not blocking.
       - Where: observe.py 141–144.
       - FR-037 needs collision or not and the minimum gap from ground truth. WP-09 consumes WP-01 labels.
         Both need the vehicles' extents (`actor.bounding_box`, which is static and passive) as well as
         their centre transforms.
       - WP-01 as planned ("full transform, velocity and acceleration") is met.
       - The gap belongs in the residuals: either v2 records each resolved actor's bounding box (for
         example in the role entry on resolution, or once in the header, which needs a schema decision),
         or WP-17 and WP-09 declare another source.
     - **LOW-1: control and liveness are not aligned with the record's frame.** Not blocking.
       - Where: observe.py 135 and 191.
       - `get_control()` and `is_alive` read the client's latest episode state, not the snapshot being
         written. When the observer lags the tick owner, `cachedControl`, and an `absent` caused by a
         death already seen, can belong to a later frame than `frame`.
       - `cachedControl` is already labelled non-actuator, but the frame skew is not stated anywhere.
         Proposed: add it to R-5, or as R-9, so that the oracle never joins control timing on `frame`
         from this stream.
     - **LOW-2: the import-isolation tests are static only.** Not blocking.
       - Where: test_observe_v2.py 339–380.
       - Mutation probe: appending `importlib.import_module("xverse_compat_carla" + ".observe")` to
         `xverse_compat/live/loop.py`. All 24 v2 tests still passed.
       - A runtime unit that launched `-m xverse_compat_carla.observe` would also pass undetected. Today
         only `adapter_check.py`, a harness, contains the string.
       - Proposed: a test that rejects `import_module`, `__import__`, `runpy` and the string
         `xverse_compat_carla.observe` in the runtime-entry closure. Otherwise, name this limit in R-3
         as a V14 import-scan scope.
     - **LOW-3: the AST mutator list is incomplete.** Not blocking.
       - Where: test_observe_v2.py 29–30 and 261–263.
       - The static check misses `apply_batch`, `apply_batch_sync`, `load_world`, `reload_world`,
         `set_weather`, `get_trafficmanager` (which would create a Traffic Manager on the observer
         client), `set_simulate_physics`, `listen` and `start_recorder`.
       - The dynamic allow-list covers the exercised paths, so the only exposure is code added on a path
         no test exercises.
     - **LOW-4: an unresolved role lists every actor on every frame.** Not blocking.
       - Where: observe.py 191–196.
       - A declared role that is permanently absent turns one `get_actors()` RPC per frame (20 Hz) into a
         steady cost. An example is `--track xverse-lite-target` before WP-02. That cost can increase
         missed frames (R-5).
       - Proposed: state it in R-5, or bound how often a role is resolved again.
     - **LOW-5: R-7 is understated.** Not blocking; documentation only.
       - `carla` is also imported lazily in `restore.py` 190 and `main.py` 88, not only in `observe.py`.
         The stale package docstring (`__init__.py` 4) is therefore wrong in more places than R-7 says.
     - **LOW-6: two paths are untested.** Not blocking.
       - The SIGINT stop path (only SIGTERM is driven) and a write or close failure on the outer
         `except` (observe.py 214–215) have no test. The code is straightforward.
   - **Residuals R-1 to R-7.** R-1 to R-6 are accurate, and R-3 honestly limits the separation to
     construction rather than OS enforcement. R-7 is accurate but incomplete (LOW-5). Missing items:
     MEDIUM-1 (proposed R-8), MEDIUM-2 and LOW-1, and the dynamic-import limit of LOW-2.
   - **Spec conformance.**
     - WP-01's scope is met: a declared role set; the full transform, velocity and acceleration; a
       separate process; its own exclusive output; and the K-5 refusal untouched (`main.py`, `sources.py`,
       `protocol.py` and `groundtruth.py` are unchanged).
     - FR-021 and V14 are met within the scope of this repository: import scan, process separation, no
       flow, and the runtime intake refuses every v2 line. The data-provenance audit remains WP-17's.
   - **Recommendation.** Merge after the author's acceptance. Record MEDIUM-1, MEDIUM-2 and LOW-1 as
     residuals, in a repair entry or in the acceptance record. LOW-2 to LOW-6 are optional before the
     blueprint wiring (R-2).
4. **Disposition of finding 3 (2026-10-24 10:38:23; decided by the coordinator under the author's delegation of
   2026-10-24, flagged for the author's review). Recorded before repair.**
   - **Repairs on this branch.**
     - MEDIUM-2: record each tracked actor's extent read-only, once per role at resolution, with a frame
       stamp: `bounding_box.extent` and its location offset. With a test.
     - LOW-2: the isolation tests also scan the runtime-entry import closure for dynamic imports and for
       subprocess or `os.exec*` launches of the observer (`importlib`, `__import__`, `subprocess`,
       `os.exec*` with `observe`). A probe must show that an injected `importlib` use is caught; the
       probe is then restored.
     - LOW-3: the forbidden-call list gains `apply_batch`, `apply_batch_sync`, `load_world`,
       `reload_world`, `set_weather`, `get_trafficmanager`, `listen`, `set_simulate_physics`,
       `set_autopilot`, `set_target_velocity`, `add_impulse` and `enable_constant_velocity`.
     - LOW-4: while a role is unresolved, actors are listed at most once per declared period, not on
       every frame. The period is recorded in the header, with a test.
     - LOW-6: tests for the SIGINT stop and for a failed write or close.
   - **Declared residuals (no code change).**
     - R-8 (MEDIUM-1): frame coverage and `tickTimeouts` are a WP-17 oracle acceptance criterion; a
       complete footer does not imply a complete run.
     - R-9 (LOW-1): the cached control and the alive check come from the observer's latest view and are
       not frame-aligned.
     - LOW-5: R-7 is corrected to name `restore.py` 190 and `main.py` 88 as well.
5. **Repair of finding 4 (2026-10-24 10:41:18).**
   - **MEDIUM-2, actor extent.** When a role is resolved, v2 writes one resolution line before that
     frame's record: `resolution: true`, `frame`, `role`, `id`, `typeId`, `boundingBox`
     (`extentM`, the half-size, and `locationM`, the offset from the actor origin, both in the actor
     frame) and `boundingBoxStatus` (`observed`, `unavailable` when the actor has no
     `bounding_box`, or `non-finite` with no value written). It is read from the static
     `actor.bounding_box` once per resolution, never per frame. The header declares it in
     `boundingBox`. Consumers tell these lines apart from frame records by `resolution`; frame records
     alone carry `roles`. Test: `test_wp01_v2_records_each_actor_extent_once_at_resolution_with_a_frame_stamp`.
   - **LOW-4, bounded listing.** An actor that dies is dropped at once (`absent`). While a role is
     unresolved, `get_actors()` runs at most once per `RESOLVE_PERIOD_FRAMES = 20` simulation frames
     (1 s at the 0.05 s fixed step, K-10; an instrument parameter, not a protocol value). It runs again at
     once when the frame number goes backwards, as in a new episode. Between listings an unresolved role
     keeps the latest listing's status (`absent` or `ambiguous`). The header records
     `resolvePeriodFrames`. Tests: `test_wp01_v2_unresolved_role_is_listed_once_per_declared_period`
     (45 frames, 3 listings, and a backward frame lists again);
     `test_wp01_v2_resolves_a_role_again_after_its_actor_dies_or_appears` updated (death inside the
     period is `absent` until frame 41); the error-after-header test moved to frame 21.
   - **LOW-3.** `MUTATORS` gains the twelve listed names and `start_recorder`. It drives both the
     raising fakes and the AST check.
   - **LOW-2.** `test_wp01_runtime_units_neither_import_dynamically_nor_launch_the_observer` scans the
     runtime-entry import closure (it includes `xverse_compat.carla_client`, which launches the adapter).
     It rejects `runpy`, `import_module`, `__import__`, `run_module`, `run_path`,
     `spec_from_file_location` and `module_from_spec`, any string constant naming
     `xverse_compat_carla.observe` or ending in `.observe` or `observe.py`, and any `subprocess.*` or
     `os.exec*`/`spawn*`/`posix_spawn*`/`system`/`popen` call with a string containing
     `observe`. Probes (restored afterwards):
     - (a) the reviewer's `importlib.import_module("xverse_compat_carla" + ".observe")` appended to
       `live/loop.py` fails this test;
     - (b) `subprocess.Popen(["python3", "-m", "xverse_compat_carla" + "." + "observe"])` fails it;
     - (c) listing on every frame fails the two LOW-4 tests.
   - **LOW-6.** `test_wp01_v2_sigint_stops_with_a_complete_footer`;
     `test_wp01_v2_failed_write_or_close_exits_3[write]` (writes after the header fail with ENOSPC,
     footer included: exit 3 with the first error) and `[close]` (the footer is written and the close
     fails: exit 3).
   - **Other test changes.** Frame-record and resolution-line filters replace positional row indexing.
     The intake test now refuses five lines, the resolution lines included.
   - **Residuals, corrected and added.**
     - R-3, addition: the LOW-2 scan is static. Code that hides the module name from string constants
       (built at runtime, read from a file) is outside it; the V14 data-provenance audit (WP-17) remains
       the backstop.
     - R-5, addition: bounded listing can delay the resolution of a newly spawned or replaced actor by up
       to 19 frames; those frames are `absent`.
     - R-7, corrected (LOW-5): the package docstring of `xverse_compat_carla/__init__.py` (line 4) says
       `carla` is imported only in `sources.LiveSource`. It is also imported lazily in `restore.py` 190,
       `main.py` 88 and `observe.py`. The docstring is left unchanged (pre-existing, LOW).
     - R-8 (MEDIUM-1): a v2 file is complete only as a record. Every `wait_for_tick` `RuntimeError`
       counts as a tick timeout, so a server lost while every role is resolved ends at the bound or at a
       signal with exit 0, `error: null` and a complete footer; trailing timeouts leave no `frame` gap.
       Frame coverage over the evaluation window and `tickTimeouts` are a WP-17 oracle acceptance
       criterion, to be declared there. A complete footer does not imply a complete run.
     - R-9 (LOW-1): `cachedControl` and the `is_alive` check read the observer client's latest episode
       state, not the snapshot being written. When the observer lags the tick owner they can belong to a
       later frame than `frame`, so the oracle must never join control timing on `frame` from this stream.
   - **CPython 3.10.12.** The module imports under `env -i ... /usr/bin/python3.10 -s -B` with
     `forbidden_modules_loaded() == []` and without loading `carla`.
   - **Suite.** 274 passed, 39 subtests (finding 2: 268). `tests/carla/test_observe_v2.py` has 30 tests.
   - **Status.** Candidate for re-review of the repair and for the author's acceptance. Not accepted,
     not merged, not pushed.
6. **Independent re-review of the repair, findings 4 and 5 (2026-10-24 10:43:31).**
   - **Reviewer and method.** The finding 3 reviewer. Read `fb3d596` and `9f57e12` against `1374570`, then
     ran the offline suite, a CPython 3.10 import check, a consumer probe and four mutation probes in
     scratch copies. The blueprint files `report.py` and `soak/audit.py` are from main `99df3a4`, used
     unchanged. The worktree was not changed except for this entry. No CARLA, no live run.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** The merge still awaits the author's
     acceptance.
   - **v1 compatibility (no regression).**
     - The v1 body is still byte-identical to base `9d1f3f3`, apart from the `def` line and its
       docstring. The source diff from `1374570` touches only module constants, `_resolution` and
       `_observe_v2`.
     - Resolution lines are written only by `_observe_v2`, which v1 and `run-live.sh` (`--role
       xverse-lite-ego`) never reach. A v1 file therefore has no line without the v1 members.
     - Consumer probe, with no change to the consumers:
       - The fake v1 run produced 29 frames, with the ego slowing and SIGTERM stopping it.
       - `report.observer_metrics` gave `framesWithEgo` 29, with the brake metrics computed.
       - `audit.actuator_safe_stop` held on the adapter-close path (29 samples,
         `observerFooterSigterm: true`) and on the guard path (29 window samples).
   - **Items of finding 3.**
     - MEDIUM-2: closed (observe.py 155–166 and 222–226).
       - The repair reads the static `actor.bounding_box` once per resolution, writes a frame-stamped
         line before that frame's record, and has `observed`, `unavailable` and `non-finite` statuses;
         no non-finite value is written.
       - The test covers all three statuses and once-per-role.
       - Probe: writing a resolution line on every frame failed 4 tests.
     - LOW-4: closed (observe.py 212–226).
       - A dead actor is dropped at once, and the next listing comes once the frame has advanced 20 or
         more, or has gone backwards.
       - The test gives 45 frames and 3 listings, plus a listing after a backward frame.
       - The 19-frame delay in R-5 is the correct bound, in simulation frames even when frames are
         missed.
       - Probe: listing on every frame failed 2 tests.
     - LOW-2: closed within its declared static scope.
       - Probe (a), the finding 3 `importlib.import_module("xverse_compat_carla" + ".observe")` appended
         to `live/loop.py`, now fails `test_wp01_runtime_units_neither_import_dynamically_nor_launch_the_observer`.
       - Probe (b) passed all 30 tests: `from subprocess import Popen as _P` with a name split into
         `"obs" + "erve"`. This is the "built at runtime" limit that the R-3 addition declares (see
         LOW-A).
     - LOW-3: closed. `MUTATORS` (test_observe_v2.py 30–34) holds all twelve names of finding 4 and
       `start_recorder`, and drives both the raising fakes and the AST check.
     - LOW-6: closed.
       - `..._sigint_stops_with_a_complete_footer` drives the SIGINT handler.
       - `..._failed_write_or_close_exits_3[write]` keeps the first error when the footer write also
         fails.
       - `[close]` reaches the outer `except` after the footer.
     - R-3, R-5 and R-7 corrections, and R-8 and R-9: present and accurate.
       - R-7 now names `restore.py` 190, `main.py` 88 and `observe.py`.
       - R-8 states that a complete footer does not imply a complete run and assigns coverage to WP-17.
       - R-9 forbids joining control timing on `frame`.
   - **Evidence.**
     - Suite: 274 passed, 39 subtests. `test_observe_v2.py` has 30 tests.
     - CPython 3.10.12 (`env -i`, `-s -B`): the import succeeds, `forbidden_modules_loaded() == []`,
       and `carla` is not loaded.
   - **New notes (all LOW, none blocking).**
     - **LOW-A: the launch check matches names only** (test_observe_v2.py `_launches`).
       - An aliased import (`from subprocess import Popen as _P`), a rebound module (`sp = subprocess`)
         or a launcher outside the list (`asyncio.create_subprocess_exec`, `multiprocessing`, `pty`) is
         not seen.
       - Combined with a split name, probe (b) shows the bypass.
       - This is inside the R-3 addition. Optional: say "aliased launchers" explicitly in R-3.
     - **LOW-B: v1-pattern consumers would misread a v2 file. This is a constraint on the wiring (R-2),
       not a regression.**
       - The probe fed a v2 file to the unchanged blueprint consumers. `report.observer_metrics` returns
         `{"framesWithEgo": 0}` without crashing.
       - `audit.actuator_safe_stop` counts the resolution line as a sample, because it selects
         `"frame" in r` (4 samples for 3 frames). On the guard path it raises `KeyError: 'monotonicNs'`,
         because v2 frame records carry `observerMonotonicNs`.
       - v2 creates its output exclusively and is not wired, so no current path is affected. The
         blueprint increment (R-2) must give v2 its own path and its own reader, selecting frame records
         by `roles` (as finding 5 states) and never `observer.jsonl`.
     - **LOW-C: one key name means two things.** The header's `boundingBox` is a descriptive string,
       while the resolution line's `boundingBox` is an object or null. Readers must branch on the line
       kind. Optional: rename the header member, for example to `boundingBoxDeclaration`, before the
       schema is consumed.
     - **LOW-D: the schema of record is now spread across findings 1 and 5.** Finding 1's schema list does
       not name the resolution line or `resolvePeriodFrames`. The acceptance record should name findings
       1 and 5 together as the v2 schema.
   - **Recommendation.** Ready for the author's acceptance. Carry LOW-B into the R-2 blueprint increment as
     an input constraint. LOW-A, LOW-C and LOW-D are optional.

## 7. Acceptance (written at 10:44:33 2026-10-24)

- **Accepted** under the author's delegation of 2026-10-24. The record is in thesis
  `specs/029-lite-stabilization/review/author-decisions-20261023.md`, "Author delegation of decisions", and
  thesis `specs/002-assured-aeb/decisions.md` §G and §H. It is flagged for the author's review.
- **Basis:** findings 3 and 6 are independent reviews, both PASS WITH NOTES with no blocker. The compat suite gives
  274 passed and 39 subtests. Verification is offline only; the live check belongs to E8-3a.
- **The v2 schema** of `xverse-compat.evaluation-observer/2` is the design of finding 1 together with the
  resolution line and `resolvePeriodFrames` of finding 5 (finding 6, LOW-D).
- **Declared:**
  - LOW-A: the launch scan recognises launchers by name only. Aliased launchers, a rebound `subprocess` module,
    `asyncio` and `multiprocessing` fall under R-3; the V14 audit remains the backstop.
  - LOW-C: the header member `boundingBox` describes the resolution-line object and is kept as named.
- **Carried to the blueprint wiring (R-2) as an input constraint (LOW-B):** v2 gets its own output path and its own
  reader, which selects frame records by `roles`. It never replaces `observer.jsonl`, which the v1 consumers
  `report.py` and `soak/audit.py` read.
- **Merged** into compat main and pushed (see the merge commit).
