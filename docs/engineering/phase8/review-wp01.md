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
