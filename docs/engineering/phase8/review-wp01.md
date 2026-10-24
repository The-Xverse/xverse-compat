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
