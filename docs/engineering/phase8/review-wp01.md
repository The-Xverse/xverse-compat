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
