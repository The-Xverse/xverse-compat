# Review log: Phase 8 WP-02b, out-of-corridor target placement (xverse-compat)

Candidate `candidate/phase8-wp02b-lateral-target-20261024`, base main `95e9e7a` (WP-02, WP-03, WP-06 and WP-08
merged). Specification: thesis `specs/002-assured-aeb` rev 3g:
- `decisions.md`, row "WP-09 training pipeline" (15:15): out-of-corridor negatives through a lateral-offset
  target placement (WP-02b, a WP-02 successor), built before training, so that the network learns "in the
  corridor" rather than "present";
- `design/wp09-training-pipeline.md` §2 ("Negative examples", option (a)) and recommendation 6;
- AD-04 option A and FR-029 (one family: a straight road segment on one map, a stationary target in the ego
  lane, fixed daylight and dry conditions); AD-28 (steering held at zero by the single writer, lateral
  deviation checked offline); `decisions.md` §H P-2 (evaluation uses only spawn point 1 and the frozen
  evaluation seeds; training and calibration use other segments and disjoint seeds);
- compat `docs/engineering/phase8/review-wp02.md` findings 1–7 and residuals R-1 to R-8.

Decided under the author's delegation of 2026-10-24 (`decisions.md` §H), flagged for the author's review.
Findings are recorded before repairs. The maturity is an engineering increment verified on owned fakes only:
not M1, not AEB evidence, live behaviour unverified (E8-3a).

## Findings

1. **Design record: out-of-corridor target placement (2026-10-24 15:19:59, before any code).**
   - **Starting point (verified at `95e9e7a`).**
     - `scenario.target_of` (43–90) admits, under schema `xverse-compat.carla-live-scenario/2`, a `target`
       with exactly the four required members `blueprint`, `roleName` (`xverse-lite-target`),
       `distanceAheadM` and `hold`.
     - `scenario.target_transform` (93–123) projects the ego spawn point onto its driving lane
       (`Map.get_waypoint`, default `project_to_road=True`, `lane_type=Driving`), walks that lane in steps of
       at most `WALK_STEP_M = 1.0` m with exactly one continuation and no junction at any step, and places the
       target at the walk's last waypoint with the lane heading and the map's spawn-point lift.
     - The target is therefore always on the ego lane centre line. WP-09 §2 names the consequence: without an
       out-of-corridor vehicle, a detector could learn "a vehicle is present" instead of "a vehicle is in the
       corridor".
   - **CARLA 0.9.15 waypoint API (introspected offline from the pinned client
     `.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310`, no server, 2026-10-24).**
     - `carla.Waypoint` exposes `get_left_lane()`, `get_right_lane()`, `lane_id`, `road_id`, `section_id`,
       `lane_type`, `lane_change`, `lane_width`, `is_junction`, `s` and `transform`. `get_left_lane` and
       `get_right_lane` return a `Waypoint` pointer (`None` when there is no lane on that side).
     - `carla.LaneType` includes `Driving` (value 2), `Shoulder`, `Sidewalk`, `Parking`, `Median`, `Border`,
       `Bidirectional` and others; `carla.LaneChange` is `NONE`, `Left`, `Right` or `Both`.
     - Per the CARLA Python API reference, left and right are taken relative to the direction of the current
       waypoint, and the neighbour is returned whatever its lane type. Whether these calls consult
       `lane_change` is not relied upon here: the code checks the properties it needs itself (below). The
       behaviour on the installed maps is a live check (E8-3a).
     - OpenDRIVE lane ids are signed relative to the road reference line: on one road, lanes whose ids have the
       same sign lie on the same side of the reference line and carry the same direction of travel; lane id 0
       is the reference line and is never a driving lane.
   - **Options for the schema extension.**
     - (A) `lateralOffsetM`: a signed metric offset from the ego lane centre, perpendicular to the lane
       heading at the target waypoint, with no default.
       - It is a new metric protocol value with no map grounding. The corridor half-width is
         `TODO: author decision` (WP-09 §3), so an offset cannot be shown in code to put the target outside the
         corridor: a small offset puts a partly in-lane target on the ego's path, which is a hazard and not a
         negative example (AD-28, below).
       - The offset point has to be validated against the road surface separately
         (`get_waypoint(location, project_to_road=False, lane_type=Driving)`), and the answer is ambiguous for
         a footprint that straddles a lane marking. Any offset that reaches a shoulder, sidewalk or parking lane
         changes the scene beyond the AD-04 family.
     - (B) An adjacent lane, declared relative to the ego lane and checked against the map's lane ids.
       - The target stays on a map-defined driving lane of the same road, at the same along-lane position. Its
         lateral offset is the map's own lane geometry, which observer v2 records, not a declared number. No
         lateral value is invented.
       - Every refusal maps to one waypoint property: no neighbour (`None`), `lane_type`, `road_id`, the sign of
         `lane_id`, `is_junction`.
       - An absolute lane id is not used as the declaration: it is specific to each road of each map and its
         sign depends on the road's reference line, so the same id means different lanes on different
         segments. A relative declaration is portable across the P-2 training segments, and the map's lane ids
         are used to check it.
     - **Choice: (B).** It is fail-closed against the CARLA waypoint graph, keeps the scene one straight road on
       one map (AD-04), and leaves the lateral position to the map. Its cost is that it produces only
       whole-lane offsets, not near-boundary examples (R-2 below). This reads the decision row's
       "lateral-offset target placement" as a placement offset laterally by one lane. The WP-09 record's
       option (a) wording "a schema-3 target placement" is answered by an optional member of schema 2 (next
       item). Both readings are flagged for the author's review.
   - **Schema: an optional `target.adjacentLane` member under schema 2 (no new schema id).**
     - `target` keeps its four required members. It may carry one further member, `adjacentLane`. An absent
       `adjacentLane` means the WP-02 in-lane placement, with exactly the same validation, CARLA calls and
       transform as at `95e9e7a`. `adjacentLane: null` or a non-object is refused.
     - `adjacentLane` has exactly two members, both required, with no default:
       - `side`: `"left"` or `"right"`, relative to the ego lane's direction of travel at the target position
         (`get_left_lane` or `get_right_lane` of the walk's last waypoint);
       - `direction`: `"same"` or `"opposite"`, the declared direction of travel of that lane relative to the
         ego lane, checked against the signs of the two lane ids.
     - The schema id stays `xverse-compat.carla-live-scenario/2`. Every scenario that compat main `95e9e7a`
       accepts is accepted with the same meaning, and a scenario with `adjacentLane` is refused there
       (`target` members must be exactly the four). So any file is either refused by a version or means the
       same thing in it, and no accepted file changes meaning. The shipped
       `xdl/descriptors/aeb-sim/live-scenario.json` stays schema 1 with no target.
   - **Placement (fail-closed, computed before anything is spawned).**
     - The along-lane walk of WP-02 is unchanged: from the projected ego spawn waypoint, `distanceAheadM` in
       steps of at most 1 m, exactly one continuation per step, no junction at the spawn waypoint or at any
       step. `distanceAheadM` keeps its WP-02 meaning, the along-lane distance in the ego lane, now to the
       point beside which the target is placed.
     - From the walk's last waypoint `w`, the neighbour `n = w.get_left_lane()` or `w.get_right_lane()` is
       taken. Refused when:
       - `n` is `None` (no lane on that side);
       - `n.lane_type != carla.LaneType.Driving` (a shoulder, sidewalk, parking, median, border,
         bidirectional or any other lane type; the immediate neighbour must itself be a driving lane, so the
         placement never skips over a non-driving lane);
       - `n.road_id != w.road_id` (the target leaves the ego's road);
       - `n.lane_id` or `w.lane_id` is not a non-zero int, or the sign relation of the two ids disagrees with
         the declared `direction` (same sign for `"same"`, opposite signs for `"opposite"`);
       - `n.is_junction`;
       - any coordinate or the lift is non-finite.
     - The target transform is `n`'s location and rotation (that lane's own heading; an `"opposite"` lane
       faces the ego's direction of travel), lifted by the map's own spawn-point lift, as in WP-02. No lateral
       or height value is invented.
     - `lane_change` is not a refusal criterion. It governs whether a vehicle may change lanes; the ego never
       steers (AD-28), and a vehicle beside a solid marking is a valid, and common, out-of-corridor case.
     - Only one lane over is supported. A target two or more lanes away, and a lane that exists only beside
       part of the walk, are not checked or offered (R-3).
   - **AD-28 and AD-04: why this is a negative example and not a hazard.**
     - The ego's steering is held at zero by the single actuator writer (`LiveSource.apply`, steer 0.0; K-3),
       so the ego stays in its lane, and FR-029's offline lateral-deviation check invalidates any run in which
       it does not. A target on the centre of an adjacent driving lane is then off the ego's path: the oracle's
       braking-needed label is expected to be false, and any braking by the function under test is a false
       intervention (AD-14 counts these separately).
     - The placement does not assert the label. Whether the target's footprint intersects the declared
       corridor is computed by the WP-09 label code from observer v2 records (centre, yaw and the WP-01
       bounding box) against the corridor half-width, which is `TODO: author decision`. A wide target in a
       narrow lane can still intersect a wide corridor; the label then says so.
     - **Scope.** AD-04 option A and FR-029 declare the principal and evaluation family as "a stationary target
       vehicle in the ego lane". An adjacent-lane target is outside that family. It serves the D-3 training,
       calibration and characterisation data of the WP-09 row (P-2: other segments, disjoint seeds), not the
       evaluation runs. The adapter does not know the run kind, so it cannot enforce this; the D-3 harness and
       the dataset-manifest check (WP-09 increment #1) must. Using such targets in evaluation would extend
       AD-04 and needs the author's decision (R-4).
   - **Single actuator writer (unchanged).** The target is still a scenario actor: spawned last, one hold
     control at spawn, never commanded at runtime. `LiveSource` binds the first three actors only.
   - **Restore guard (no code change).** The target's role is still `xverse-lite-target`, so `restore._owned`
     (prefix `xverse-lite-`) lists it and the owned-actor registry written by `LiveSource` holds its id,
     `typeId` and `roleName`. Both guard paths hold, await and destroy it whatever lane it is on. Tests pin both
     paths for an adjacent-lane target.
   - **Observer v2 (no code change).** `observe --track xverse-lite-target` resolves the target by role and
     records its world `location`, `rotationDeg`, velocity and acceleration per frame and its bounding box at
     resolution. The lateral offset from the ego lane centre is derived offline from the ego and target records
     (WP-09 labels); the observer does not need lane information. A test pins that the role of an
     adjacent-lane target is the trackable `TARGET_ROLE`.
   - **CPython 3.10.** `scenario.py` keeps importing only the standard library; `carla` is passed in
     (duck-typed), and `carla.LaneType.Driving` is read from the passed module only when `adjacentLane` is
     present. No `xverse_compat` import is added (`protocol.FORBIDDEN`).
   - **Tests (offline, in `tests/live/test_phase8_target.py`, extending the WP-02 lane fake).** The fake lane map
     gains lanes beside the ego lane with declared lane ids, road ids, lane types and junction flags; the fake
     `carla` gains `LaneType.Driving`. All lateral and lane values in the tests are labelled test values.
     - Schema: `adjacentLane` absent gives exactly the WP-02 transform and no neighbour query; `null`, a
       non-object, a missing or unknown member, and an unknown `side` or `direction` are refused, each before
       any spawn or waypoint query; any other fifth `target` member is still refused.
     - Placement: left and right, same and opposite direction, on the adjacent lane's centre and heading with
       the map's lift; the walk is unchanged.
     - Refusals: no neighbour; a non-driving neighbour (shoulder, sidewalk, parking); another road; a direction
       mismatch either way; a zero or non-int lane id; a neighbour in a junction; a junction, branch or lane end
       on the walk still refused with `adjacentLane` present. Nothing is spawned in any case.
     - Spawn and ownership: `[ego, camera, radar, target]` with the target at the adjacent placement and one hold;
       the registry lists it; runtime commands reach the ego only.
     - Restore guard: listing and registry paths hold and destroy an adjacent-lane target.
     - Observer: the role is trackable.
   - **Residuals expected (stated before code; confirmed or amended in finding 2).**
     - R-1. Live behaviour is unverified: the installed maps' neighbour lanes, their types and ids, the
       `get_left_lane`/`get_right_lane` semantics there, and the hold of a target in an adjacent lane (with
       WP-02 R-1). No CARLA was run.
     - R-2. Only whole-lane offsets: near-corridor-boundary examples are not produced. If WP-09 needs them, a
       metric offset (option A) is a separate successor with its own design entry and a corridor-width
       decision.
     - R-3. One lane over only, and only the target position is checked on the neighbour lane.
     - R-4. Adjacent-lane targets are outside the AD-04/FR-029 evaluation family; keeping them to D-3 data is
       the blueprints' job (harness, manifest), not enforced in compat.
     - R-5. WP-02 residuals R-1 to R-8 still apply, and R-3 of WP-02 (blueprint selection of a target
       scenario, the audit's owned set and target stillness) is unchanged.
