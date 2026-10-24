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
