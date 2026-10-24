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
