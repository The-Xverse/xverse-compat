# Review log: Phase 8 WP-02, stationary target spawn (xverse-compat)

Candidate `candidate/phase8-wp02-stationary-target-20261024`, base main `d5d7be8` (WP-01 merged).
Specification: thesis `specs/002-assured-aeb` rev 3g, `implementation-plan.md` §2 and the WP-02 row,
code facts K-1, K-2, K-3, K-7 and K-9; FR-029 and AD-04 option A (one family: a straight road on one map,
a stationary target vehicle in the ego lane, fixed daylight and dry conditions; parameters ego speed and
initial gap); AD-28 (steering held at zero by the single writer); [A7] 36–38 and DLG-9 (one tick owner
and one actuator writer, the adapter; adapter-owned actors). Decided under the author's delegation of
2026-10-24 (`decisions.md` §H), flagged for the author's review. Findings are recorded before repairs.
The maturity is an engineering increment verified on owned fakes only: not M1, not AEB evidence, live
behaviour unverified (E8-3a).

## Findings

1. **Design record: stationary target spawn (2026-10-24 10:47:19, before any code).**
   - **Starting point (verified at `d5d7be8`).** `scenario.spawn` spawns exactly `[ego, camera, radar]`
     and reads only `egoBlueprint` and `spawnPointIndex`; the `schema` member of
     `xdl/descriptors/aeb-sim/live-scenario.json` (`xverse-compat.carla-live-scenario/1`) is not read.
     `LiveSource` unpacks exactly three spawned ids (`sources.py` 175), writes every spawned actor to the
     owned-actor registry (168–173), applies control to the ego only (198–199, K-3) and destroys
     `reversed(_spawned)` at close (243).
   - **Scenario schema `xverse-compat.carla-live-scenario/2` (validated fail-closed, before anything is
     spawned).**
     - Schema 1, or no `schema` member (the Phase 7 test dicts), keeps today's behaviour, and a `target`
       member there is refused. Any other `schema` value is refused.
     - Schema 2 admits exactly the members `schema`, `egoBlueprint`, `spawnPointIndex`, `map`,
       `note` and, optionally, `target`. An absent `target` means no target; `target: null` or any
       non-object is refused.
     - `target` has exactly four members, all required:
       - `blueprint`: a string beginning with `vehicle.`;
       - `roleName`: exactly `xverse-lite-target` (owned prefix K-7; the WP-01 observer's `--track` role);
       - `distanceAheadM`: an int or float, not a bool, finite and > 0. It has **no default**: a missing
         distance is refused. No distance value is shipped in this increment;
       - `hold`: the declared hold, exactly `"brake-and-hand-brake"` (see below).
     - `distanceAheadM` is the along-lane distance between the ego spawn waypoint and the target
       waypoint, that is between actor origins. The AD-04 parameter "initial gap" is a bumper-to-bumper
       quantity: it equals `distanceAheadM` minus the ego's and the target's front and rear half-lengths,
       which WP-01 records (`boundingBox`). The conversion, and the protocol values, belong to the freeze
       (AD-27); the shipped `live-scenario.json` stays schema 1 with no target, so the Phase 7 and S1
       harness and tonight's soak are unchanged.
   - **Placement (in the ego lane, fail-closed).** From the map's spawn point `spawnPointIndex`:
     `start = map.get_waypoint(point.location)` (projected onto the driving lane), then
     `ahead = start.next(distanceAheadM)`. Refused unless exactly one waypoint comes back (no lane end,
     no branch) and it is not in a junction. The target transform is that waypoint's location and
     rotation (lane heading), lifted by the map's own spawn-point lift (`point.location.z -
     start.transform.location.z`, required finite), so no lift value is invented. Straightness of the
     segment stays a scenario-validity check (FR-029; spawn point 1, K-9).
   - **Spawning and ownership.** The placement is computed before the first spawn. The target is spawned
     last, after the ego and both sensors, so `spawn` returns `[ego, camera, radar, target]` and indices
     0–2 keep their meaning. Any failure destroys every partial spawn in reverse order (existing rule).
     `LiveSource` takes the first three ids for ego, camera and radar, registers all spawned actors
     (target included: id, `typeId`, `roleName`) and destroys them at close, target first.
   - **Single actuator writer.** The target is a scenario actor, not a runtime writer or a runtime-
     controlled actor. Its hold control is written exactly once, at spawn, by the scenario code inside
     the adapter process. Runtime commands (`LiveSource.apply`) still reach the ego only, steering 0
     (K-3, AD-28). The restore guard's post-run hold is the existing owned-actor rule and is not a
     runtime path.
   - **Holding it still: options.**
     - (A) `apply_control(VehicleControl(throttle=0, brake=1, steer=0, hand_brake=True))` once at
       spawn, physics on. CARLA keeps the last applied control. The target settles onto the road from the
       spawn lift, keeps its collision response, and its velocity and acceleration remain physical
       ground truth for the oracle (FR-037: collision, minimum gap).
     - (B) `set_simulate_physics(False)`. The actor becomes kinematic: it stays at the lifted spawn height
       instead of settling, and a collision meets an immovable body. Whether collision events and the
       radar return behave as for a physical vehicle is unverified, and the oracle's collision criterion
       would then rest on an unphysical contact.
     - **Recommendation: (A).** It needs no new CARLA call class, keeps the target a physical vehicle, and
       is the hold the adapter and the guard already use for an owned ego. (B) is a fallback only if the
       live check fails, and needs its own design entry.
     - **Live check needed (E8-3a, with D-2).** With `observe --track xverse-lite-ego --track
       xverse-lite-target`: after spawn and settling, the target's displacement and speed over the
       declared horizon, with the ego held and with the ego approaching, stay within a declared tolerance
       (`TODO: measurement`; no tolerance is invented here); and the guard's standstill record covers
       the target.
   - **Restore guard (no change).** `restore._owned` (39–40) selects every `xverse-lite-*` role, so the
     target is held (it is a `vehicle.*`), awaited to standstill and destroyed. The registry path holds
     and destroys it by id (`restore.py` 96–102, 143–148). Tests cover both paths.
   - **Observer.** WP-01's `TRACK_ROLE` accepts `xverse-lite-target`; a test pins that the scenario's
     target role is trackable.
   - **P8 single-owner audit (blueprints, read-only at main `99df3a4`).**
     - `soak/audit.py` `OWNED_ROLES` (21) is `{ego, camera, radar}` and P3 checks the guard destroyed a
       superset of it (192), so an added target passes; a missing target would not be detected.
     - P8 `actuator_safe_stop` (111–150) classifies the path by `held` being empty, and then judges the
       ego from the v1 observer. A run in which the guard holds only the target (for example the adapter
       destroyed the ego but not the target) would be classified as the guard path and judged on the ego
       window, and the target's own stillness is not checked.
     - P7 and `run-live.sh` 91–92 require a world without vehicles before the run; the target is spawned
       by the adapter after that check, so they are unaffected.
     - The target is therefore not a competing writer for P7 or P8. The audit changes (target role in the
       owned set when the scenario declares one, path classification by held ego, target stillness from
       observer v2) are a separate `xverse-blueprints` increment and are not made here.
   - **Tests (offline, in `tests/live/test_phase8_target.py`, reusing the Phase 7 fake world).**
     - Schema: schema 1 and no schema unchanged; target under schema 1 refused; unknown schema refused;
       unknown top-level or target members refused; `target: null`; a missing, zero, negative, bool,
       NaN, infinite or string distance; a non-vehicle blueprint; a wrong role; an unknown hold.
     - Placement: transform from the single waypoint ahead with the lane rotation and the map's lift;
       no waypoint, two waypoints and a junction refused before anything is spawned.
     - Spawn: four actors in order; one hold control on the target at spawn; partial-spawn rollback when
       the target spawn or its hold fails.
     - LiveSource: ego, camera and radar bound as before; the registry lists the target; commands reach the
       ego only; close destroys the target.
     - Restore guard: listed and registry paths hold, await and destroy the target.
     - Observer: the target role is accepted by `TRACK_ROLE`.
2. **Implementation of finding 1 (2026-10-24 10:49:53).**
   - **Change.**
     - `src/xverse_compat_carla/scenario.py`: `SCHEMA_1`, `SCHEMA_2`, `TARGET_ROLE`, `TARGET_HOLD`;
       `target_of` (schema and target validation); `target_transform` (in-lane placement); `spawn`
       validates and places before the first spawn, spawns the target last and applies its one hold
       control (throttle 0, brake 1, steer 0, hand brake) inside the existing partial-spawn rollback.
     - `src/xverse_compat_carla/sources.py`: `LiveSource` binds ego, camera and radar from the first
       three spawned actors; two comments updated. Registry, actuation and close are unchanged code and
       now cover the target because it is in `_spawned`.
     - `restore.py`, `observe.py`, `main.py`, `protocol.py` and the shipped
       `xdl/descriptors/aeb-sim/live-scenario.json` (schema 1, no target) are unchanged.
   - **Tests.** `tests/live/test_phase8_target.py`: 34 tests (parametrized cases included), offline,
     reusing the Phase 7 fake world with a lane map.
     - Schema: schema 1, no schema, the shipped descriptor and schema 2 without a target give no target; 21
       invalid scenarios (target under schema 1 or without schema, unknown schema, unknown top-level or
       target member, `target: null` or a list, a missing, zero, negative, bool, NaN, infinite, string or
       null distance, a non-vehicle or non-string blueprint, two wrong roles, the `physics-off` hold, a
       non-object scenario) are refused, and in each case nothing is spawned and no waypoint is queried.
     - Placement: one waypoint 40 m ahead along the lane, lane heading, the map's 0.6 m spawn-point lift
       (fake values); no waypoint, two waypoints, a junction and an off-lane spawn point are refused with
       nothing spawned.
     - Spawn: `[ego, camera, radar, target]`; exactly one hold control on the target; none on the ego;
       a failed target spawn or a failed hold destroys every partial spawn.
     - LiveSource: the ego is bound; the registry lists four actors including the target's id, `typeId`
       and `roleName`; runtime commands reach the ego only; close destroys the target first and the ego
       last, and writes no further control to the target.
     - Restore guard after a simulated SIGKILL: listing path and registry path both hold the target, await
       its standstill (listing path) and destroy it; `remaining == []`, `restored: true`.
     - Observer: `TARGET_ROLE` matches the WP-01 `TRACK_ROLE`.
   - **Mutation checks (not committed; restored).** Removing the spawn hold fails 3 tests; a default
     `distanceAheadM` of 30 fails the missing-distance case; unpacking every spawned id fails 3 tests.
   - **CPython 3.10.12.** `scenario`, `sources` and `main` import under `env -i ... /usr/bin/python3.10
     -s -B` with `forbidden_modules_loaded() == []`, without loading `carla`; `target_of` of the shipped
     descriptor is `None`.
   - **Suite.** 308 passed, 39 subtests (base `d5d7be8`: 274).
   - **Hold-still recommendation.** Option (A), brake and hand brake once at spawn with physics on, is
     implemented and is the only accepted `hold`. (B) `set_simulate_physics(False)` is not implemented.
     The live check under E8-3a (with D-2): with observer v2 tracking ego and target, the target's
     displacement and speed after settling stay within a declared tolerance (`TODO: measurement`) with
     the ego held and while it approaches; the guard's standstill record lists the target.
   - **Residuals.**
     - R-1. Live behaviour is unverified: whether hold (A) keeps a CARLA 0.9.15 vehicle still, how it
       settles from the spawn-point lift, and the radar return from it (E8-3a, D-2). No CARLA was run.
     - R-2. No scenario with a target is shipped. `distanceAheadM` and its conversion to the AD-04
       bumper-to-bumper initial gap (with the WP-01 extents) are protocol values for the freeze (AD-27);
       characterisation scenarios declare their distances before the runs (P-3).
     - R-3. Blueprint increment (separate, not made here):
       - `units.py` 60 hard-codes the compat `live-scenario.json`, so selecting a target scenario needs a
         blueprint change;
       - `soak/audit.py`: add the target role to `OWNED_ROLES` when the scenario declares one; classify
         the P8 path by held ego, not by any held vehicle; judge the target's stillness from observer v2;
       - the observer v2 wiring (WP-01 R-2).
     - R-4. Placement checks one continuation and no junction only. The segment's straightness and the
       target's lateral position are not checked in code (FR-029 offline validity check; spawn point 1,
       K-9). The ego spawn-point lift is reused for the target; a spawn collision is refused with
       rollback.
     - R-5. The `map` member is not checked against the loaded world, under either schema (pre-existing).
     - R-6. Schema-2 strictness (unknown members refused) does not apply to schema 1, which keeps its
       Phase 7 leniency for compatibility.
     - R-7. Once hit, a physical target moves; that is the intended physics, and the oracle reads it from
       observer v2.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 10:52:35).**
   - **Reviewer and method.** An independent reviewer who did not write the code. I read `764f38d` and
     `2e3dbb8` against base `d5d7be8` and checked them against thesis `specs/002-assured-aeb` (FR-029,
     AD-04 option A, AD-28) and `decisions.md` §H. Blueprints were read only, at main `99df3a4`
     (`units.py`, `run-live.sh`, `soak/audit.py`).
     - Run: the offline suite, a CPython 3.10 import check, and three probes in a scratch copy.
     - The worktree was not changed except for this entry. No CARLA, no live run.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** The merge still awaits the author's
     acceptance. The maturity in the preamble stands: owned fakes only, not M1, not AEB evidence, live
     behaviour unverified (E8-3a).
   - **Evidence.**
     - Suite: 308 passed, 39 subtests. CPython 3.10.12 (`env -i`, `-s -B`): `scenario`, `sources`, `main`
       import with `forbidden_modules_loaded() == []`, `carla` not loaded; `target_of(shipped) is None`.
     - Fail-closed schema (scenario.py 36–72).
       - `schema: null` or any other value is refused, as is a `target` under schema 1 or without a
         schema. Unknown schema-2 members are refused.
       - `target: null` and non-objects are refused, and the target members must match exactly, so a
         missing distance is refused (there is no default).
       - The distance must be a finite int or float that is not a bool and is > 0. The blueprint must be
         a `vehicle.*` string, `roleName` exactly `xverse-lite-target`, and `hold` exactly
         `brake-and-hand-brake`.
       - Every refusal happens before any spawn or waypoint query (test_phase8_target.py 91–120). A JSON
         `NaN` literal, which `main.py` 98 admits through `json.loads`, is refused by `_finite`.
     - Placement (scenario.py 75–96, 114). The target transform is computed before the first spawn, with
       exactly one continuation, a non-junction end point and finite values. The map's own lift is
       reused. A spawn collision raises inside the rollback.
     - Single writer.
       - The target receives exactly one control, the hold at spawn (scenario.py 134), inside the
         partial-spawn rollback.
       - `LiveSource.apply` (sources.py 195–199) and the close hold write only `self._vehicle`, which is
         the ego from `_spawned[:3]`. The tests pin `len(target.controls) == 1` through `apply` and
         `close` (test_phase8_target.py 183–191).
       - The guard's post-run hold is the existing owned-actor rule, as declared.
     - Restore guard. `_owned` (restore.py 39–40) selects by prefix, and the registry holds every spawned
       actor. Both paths hold, destroy and leave `remaining == []`, and the listing path awaits standstill
       (test_phase8_target.py 208–245).
     - Schema-1 compatibility and tonight's soak.
       - `xdl/descriptors/aeb-sim/live-scenario.json` is unchanged (`git diff d5d7be8..HEAD -- xdl` is
         empty), and it is the only scenario the blueprints use: `units.py` 60 hard-codes it, and
         `egoBlueprint` occurs nowhere else in the blueprints at `99df3a4`.
       - For schema 1, `spawn` makes the same CARLA calls as before, apart from one reused `get_map()`
         result. `target_of` returns `None` and makes no CARLA call.
       - The Phase 7 scenario dicts without `schema` (test_phase7_live.py 199, 213, 216) still pass.
       - Observer v1 (`vehicle.*`, role `xverse-lite-ego`) and the P7 empty-world check (`run-live.sh`
         91–92) are unaffected.
   - **Issues (none blocks the merge).**
     - **MEDIUM-1: the live check is not yet defined well enough to give a pass or fail.**
       - Where: finding 1, "Live check needed", and finding 2, "Hold-still recommendation".
       - Hold (A) itself is the right recommendation. It keeps a physical vehicle for the FR-037 collision
         and gap criteria, needs no new call class, and matches the guard's hold. (B) is correctly
         limited to a fallback with its own design entry.
       - Missing, before E8-3a runs it:
         - (a) a settling criterion: for example a speed below a threshold for N consecutive frames,
           with the first such frame as the reference;
         - (b) the horizon, in simulation frames or seconds;
         - (c) the measured quantities, in the lane frame: along-lane and lateral displacement from the
           settled reference, yaw change, and peak speed;
         - (d) the lateral placement against the ego lane centre (FR-029 "in the ego lane"; see LOW-2);
         - (e) that the target is resolved by observer v2, together with its `boundingBox`;
         - (f) the D-2 radar return from the target;
         - (g) the phases: the ego held, the ego approaching and braking, and the guard.
       - The tolerances may stay `TODO: measurement`, but each needs a named owner, for example the D-2
         design record, so that no value is invented later.
       - This belongs to E8-3a and D-2, not to this increment, so it does not block the merge.
     - **LOW-1: a junction between the ego and the target is not detected.**
       - Where: scenario.py 85–90.
       - Only the end waypoint is tested with `is_junction`. CARLA's `next(d)` follows the lane through a
         junction, and a single connection gives one result.
       - A scratch probe with a junction at x 20–30 and the target at x 50 was accepted.
       - R-4 says "no junction only" and should state that only the target waypoint is checked.
         Optional: also check intermediate waypoints, for example by stepping `next` along the lane.
     - **LOW-2: "in the ego lane" is not established in code, and the off-lane refusal is fake-only.**
       - Where: scenario.py 82–84.
       - CARLA's `Map.get_waypoint(location)` projects onto the nearest driving lane by default and
         returns `None` only with `project_to_road=False`. On a real map the "not on a driving lane"
         branch, and its test (test_phase8_target.py 143), cannot fire.
       - A spawn point near a lane boundary would be projected onto the nearest lane centre without a
         refusal.
       - Optional: refuse when the spawn point's lateral distance from `start` exceeds half
         `start.lane_width`, or when its yaw disagrees with the lane heading.
       - Otherwise, add to R-4 that the lane is the projected nearest driving lane.
     - **LOW-3: the base members of schema 2 are neither required nor typed.**
       - Where: scenario.py 53–56.
       - A schema-2 scenario without `egoBlueprint` fails with a `KeyError`, with nothing spawned (probe),
         not with a schema refusal.
       - `map: 42` and `note: {...}` are accepted (probe).
       - This is fail-closed in effect but not as a validation. Optional: require `egoBlueprint` (a
         string) and `spawnPointIndex` (an int), and type `map` and `note`; otherwise, extend R-5 and R-6.
     - **LOW-4: the gap conversion omits the bounding-box offset.**
       - Where: finding 1, "distanceAheadM", and R-2.
       - The AD-04 bumper-to-bumper gap is
         `distanceAheadM − (ego.locationM.x + ego.extentM.x) − (target.extentM.x − target.locationM.x)`,
         using the WP-01 `locationM` offset, not half-lengths alone.
       - The ego is spawned at the spawn point, not at the projected `start` waypoint, so their
         along-lane offset is also part of the conversion.
       - R-2 should name both offsets, and the freeze (AD-27) owns the formula.
     - **LOW-5: a failed target destroy at close now skips the sensors and the ego.**
       - Where: sources.py 243–244.
       - The pre-existing loop has no per-actor `try`, and the target is now destroyed first. If its
         `destroy()` raises, the sensors and the ego are left to the restore guard, which covers them.
       - Optional: a per-actor `try` that collects errors; otherwise, a sentence in R-3 or R-4.
   - **Residuals R-1 to R-7.** R-1, R-3 and R-7 are accurate and complete, and R-3 correctly records the
     two P8 audit gaps: misclassification by any held vehicle, and target stillness not judged. R-2, R-4
     and R-5/R-6 are accurate but incomplete (LOW-4; LOW-1 and LOW-2; LOW-3). Missing: the
     live-check criteria of MEDIUM-1 and the close-order exposure of LOW-5.
   - **Recommendation.**
     - Merge after the author's acceptance.
     - Record MEDIUM-1 as an E8-3a and D-2 input: criteria (a) to (g), each tolerance a TODO with a named
       owner.
     - Amend R-2 and R-4 for LOW-1, LOW-2 and LOW-4.
     - LOW-3 and LOW-5 are optional code repairs on this branch, or residual sentences.
4. **Disposition of finding 3 (2026-10-24 10:54:09; decided by the coordinator under the author's delegation of
   2026-10-24, flagged for the author's review). Recorded before repair.**
   - **Repairs in code, with tests.**
     - LOW-1: walk the lane from the ego spawn waypoint to the target in bounded steps (the step is
       recorded in the design) and refuse when any intermediate waypoint is in a junction or the lane
       branches.
     - LOW-3: schema 2 requires and type-checks every base member (`egoBlueprint`, `spawnPointIndex`,
       `map` and any other base field), refused before any spawn.
     - LOW-5: at close, destroy each actor in its own `try`, record failures and continue.
   - **Records without code change.**
     - MEDIUM-1: the live-check criteria (a) to (g) become an E8-3a and D-2 input: the settle criterion,
       the horizon, lane-frame quantities, lateral placement, observer-v2 resolution with the bounding
       box, the D-2 radar return, and the phases. Each tolerance stays TODO, owned by WP-17 (oracle and
       characterisation harness).
     - LOW-2: R-4 is amended. The real `get_waypoint` snaps any point onto the nearest driving lane, so
       lateral placement is verified live.
     - LOW-4: R-2 is amended. The gap conversion needs the bounding-box offsets and the ego's offset from
       the projected waypoint.
5. **Repair of finding 4 (2026-10-24 10:56:09).**
   - **LOW-1, bounded lane walk.** `target_transform` walks from the projected ego spawn waypoint in
     `ceil(distanceAheadM / WALK_STEP_M)` steps, with `WALK_STEP_M = 1.0` m (the last step is the
     remainder, so the walk ends exactly at the declared distance). Every step must return exactly one
     continuation (a lane end or a branch is refused), and neither the spawn waypoint nor any waypoint on
     the way may be in a junction. The target transform is the walk's last waypoint. An instrument guard
     `MAX_DISTANCE_M = 1000.0` bounds the walk to 1000 steps; it is not a protocol value (far beyond the
     120 m lane, K-9, and the 100 m radar range, K-10), and a larger distance is refused at validation.
   - **LOW-3, schema-2 base members.** Required: `schema`, `egoBlueprint` (a `vehicle.*` string),
     `spawnPointIndex` (an int, not a bool, ≥ 0) and `map` (a non-empty string). Optional: `note` (a
     string) and `target`. Each is checked in `target_of`, before any spawn or waypoint query. Schema 1
     is unchanged (R-6).
   - **LOW-5, close.** `LiveSource.close` destroys each owned actor in its own `try`, records failures in
     `destroy_failed`, continues with the next actor, restores the settings, and then raises one
     `RuntimeError` naming each failure, so `main._close` still exits 3. An error already in flight from
     the sensor stop takes precedence.
   - **Tests.** `tests/live/test_phase8_target.py` now has 53 tests (19 new). The lane fake gains a junction
     span, a branch point and a lane end.
     - Walk: 40 steps of 1 m; a 40.5 m walk ends with a 0.5 m step at x 50.5; refused for a lane end at
       step 21, a branch at step 15 and at the target, a junction at step 10 (between ego and target) and
       at step 38, and a spawn waypoint in a junction; `distanceAheadM` above the guard refused.
     - Base members: missing `egoBlueprint`, `spawnPointIndex` or `map`; a non-vehicle or null
       `egoBlueprint`; a bool, string, negative or float `spawnPointIndex`; `map: 42` and an empty
       `map`; a non-string `note`. Each is refused with nothing spawned and no waypoint queried.
     - Close: a failing target destroy leaves only the target, destroys camera, radar and ego, records
       one failure, restores the settings, and raises.
   - **Mutation checks (not committed; restored).** Checking the junction at the last step only fails the
     intermediate-junction case; dropping the required-member check fails 4 tests; catching only
     `ZeroDivisionError` at close fails the close test.
   - **CPython 3.10.12.** `scenario`, `sources` and `main` import with `forbidden_modules_loaded() == []`,
     without loading `carla`; `target_of` of the shipped descriptor is `None`.
   - **Suite.** 327 passed, 39 subtests (finding 2: 308).
   - **E8-3a and D-2 input: hold-still live-check criteria (MEDIUM-1; no code change).** Each tolerance and
     count is `TODO: measurement`, and its owner is WP-17 (oracle and characterisation harness), which
     declares it before the run. No value is set here.
     - (a) Settle criterion: the target's speed below a declared threshold for a declared number of
       consecutive frames; the first such frame is the reference.
     - (b) Horizon: a declared span in simulation frames from the reference.
     - (c) Quantities in the lane frame of the target waypoint: along-lane and lateral displacement from
       the reference, yaw change, and peak speed over the horizon.
     - (d) Lateral placement: the target's lateral offset from the ego lane centre, and the ego's, at the
       reference (FR-029 "in the ego lane"; see R-4).
     - (e) Resolution: observer v2 (`--track xverse-lite-ego --track xverse-lite-target`) resolves both
       roles, with a `boundingBoxStatus: observed` resolution line for each.
     - (f) Radar: the D-2 radar return from the target (detection, range and range rate) at the declared
       distances (GA-38).
     - (g) Phases: ego held; ego approaching and braking; the restore guard (the target listed in
       `held` and in the standstill record).
   - **Residuals, amended.**
     - R-2, amended (LOW-4): the AD-04 bumper-to-bumper initial gap is
       `distanceAheadM − (ego.locationM.x + ego.extentM.x) − (target.extentM.x − target.locationM.x)`,
       corrected for the ego's along-lane offset between its spawn point and the projected spawn waypoint
       from which the walk starts. Both offsets come from the map and the WP-01 resolution lines; the
       freeze (AD-27) owns the formula and the values.
     - R-4, amended (LOW-1, LOW-2): the walk now refuses junctions and branches anywhere between ego and
       target. The real `Map.get_waypoint` projects any point onto the nearest driving lane, so the
       off-lane refusal fires only on fakes; "in the ego lane" means the projected nearest driving lane,
       and the lateral placement is verified live (criterion (d)). Straightness of the segment stays the
       FR-029 offline validity check.
     - R-5, unchanged: `map` is now required and typed under schema 2, but it is still not compared with
       the loaded world.
     - R-8 (LOW-5, repaired): a failed destroy at close no longer skips the remaining actors; the restore
       guard still covers any that remain.
   - **Status.** Candidate for re-review of the repair and for the author's acceptance. Not accepted,
     not merged, not pushed.
