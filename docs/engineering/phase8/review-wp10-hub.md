# Review log: Phase 8 WP-10 increment #2, the U2 hub core without faults (xverse-compat)

Candidate `candidate/phase8-wp10-hub-core-20261024`, base main `95e9e7a` (WP-06 merged). Specification:
- thesis `specs/002-assured-aeb/design/wp10-fault-relay.md` §2 (DRAFT, PROPOSED), decided as option (A) in the
  `decisions.md` row "WP-10 fault relay" (12:11, under the author's delegation, flagged for review);
- §K (the Unix-socket star through U2; lockstep; the wait bound measured in D-4c);
- the rows "AD-30 delivery rule" and "WP-12 carry-forward" (delay points F04, F14, F15b and F17, one simulator
  step each);
- the topology form at blueprints main `5f71cde` (`automotive/assured-aeb/xdl/<arm>/topology/system.json`);
- blueprints review-wp04 (`BrakeCommandReader`: `deliver`, `bind_origin`, `mark_lost`; LOW-2, the start-up
  deadline) and review-wp05 (`bind_origin`);
- compat review-wp06 N1 (`FrameReceiver.close()` always).
Findings are recorded before repairs. The maturity is an engineering increment verified offline: not M1, no
faults, live behaviour unverified (E8-3a, D-4c).

## Findings

1. **Design record: the hub core (2026-10-24 12:13:36, before any code).**
   - **Topology contract `xverse-compat.hub-topology/1`** (`live/hub_topology.py`, standard library, no import of
     the blueprint package).
     - A plain JSON record: `schema`, `arm`, `units` (unit id to its hosted elements), `hubUnit` (the unit
       hosting `loop-gateway`), `adapterUnit` (the unit hosting `carla-client`) and `flows`.
     - Each flow has `id`, `source` and `destinations` (element and unit), `route` (`adapter-link` for flows
       touching the adapter unit, `hub` otherwise), `hubDelaySteps` (an int, 0 when the form declares none), and
       `returnFlow`.
     - `from_system_document(doc)` derives it from the generated `system.json` of an arm's topology form: the
       `flows` and the extension's `returnFlows`, endpoint owners, element `hostUnit` and unit-host
       `hostedElements`. Intra-unit messages are not hub-routed.
     - Fail-closed on an endpoint without an owner, an element without a unit, an unknown `hubDelay` unit (only
       `simulator-step`) or a duplicate flow id. A test derives the record from the checked-in copy of the
       `5f71cde` topology form (`tests/live/fixtures/wp10-topology-mloc-5f71cde.json`, the `system.json` of the
       MLOC arm) and pins the four delay points.
   - **Schedule core** (`HubSchedule`, pure and deterministic, no I/O). Step `k` is the `k`-th ticked frame,
     with boundary time `T_k`, the frame's simulation time.
     - A message produced in step `p` on flow `f` carries `originNs` and `deliverAtNs` (the producer's AD-30
       stamp; WP-05 model). It is admitted if both are ints, `originNs ≤ deliverAtNs`, and `originNs ≤ T_p`
       (no future origin; WP-04 residual 5). Otherwise it is refused and counted.
     - **Delivery step** = the first step `j ≥ p` with `T_j ≥ deliverAtNs`, plus `hubDelaySteps(f)`. The hub
       delay is additive to the rounded AD-30 delivery point; its relation to the AD-30 declaration stays
       `TODO: author decision (AD-30)`, as in the WP-12 carry-forward row. A message due in its own step
       (`hubDelaySteps 0` and `deliverAtNs ≤ T_p`) is delivered in a later **round** of the same step. The
       topology without the delay points has no cross-unit cycle (blueprints review-wp12 MEDIUM-1), so the rounds
       terminate. A round cap equal to the number of units refuses a cycle that is not declared.
     - **Determinism.** Within a round, deliveries are ordered by `(flow id, source unit, producer sequence)`,
       never by arrival order. Two runs with the same inputs give the same delivery log.
   - **Unit transport** `xverse-compat.hub-units/1`. One Unix stream socket listener at a declared path; mode
     0600 under umask 0177, as the adapter link. JSON lines with the protocol's line limit, strict UTF-8, no NaN.
     - Unit to hub: `hello` (`unit`); `outputs` (`step`, `round`, `messages`: `flowId`, `sequence`,
       `originNs`, `deliverAtNs`, `payload`).
     - Hub to unit: `origin` (`episodeOriginNs`, once, before any step); `round` (`step`, `round`, `simNs`,
       `deliveries`); `lost` (`flowId`); `end`.
     - A unit may produce only flows whose source element it hosts, and refused messages are counted.
   - **The step.**
     1. Send the F04 command from the local command source (as `LiteVehicleLoop`, ED-15) and tick the adapter
        link.
     2. Take the camera frame through the WP-06 `FrameReceiver`.
     3. At the first frame, bind the origin (point 4).
     4. Feed the adapter items to the local consumers.
     5. Run the local producers.
     6. Rounds: deliver due messages; the hub waits for an `outputs` from every recipient of the round (round 0
        goes to every live unit), up to the **consumer wait bound**.
     7. When no round is due, the step ends.
   - **Origin (late binding, no default).** At the first ticked frame, `episode_ns` is that frame's simulation
     time, as `loop.py` 114. The hub then calls `bind_origin(episode_ns)` once on every local consumer that has
     it, and sends `origin` to every unit before step 0's first round. Nothing is delivered before the origin is
     bound, and a second, different value is refused.
   - **Lost verdicts.** When a producing unit disconnects or misses the wait bound, each of its flows is lost: the
     hub calls `mark_lost()` on local consumers (for example `BrakeCommandReader` for F17) and sends `lost` to
     remote consumers, once per flow. Without faults, a missed wait bound also makes the run invalid
     (`HubInvalidRun`, FR-042), because no unit is frozen in this increment. The hook for a declared frozen set
     is kept for increment #4.
   - **Start-up deadline.** `startup_deadlines_ns` maps a flow to a deadline in **simulation time** after the
     episode origin. It is deterministic and paired, so it is keyed to simulation time, not host time. It is
     **required** for every flow the topology delivers to the hub unit from a remote producer that the caller
     declares as start-up-guarded; for F17 it is required whenever F17 is present. There is no default
     (`TODO: author decision`, AD-07 and WP-13). If no message on the flow is delivered by the first step whose
     `T_k ≥ origin + deadline`, the flow is lost once (`mark_lost`, recorded).
   - **Bounds (parameters, no defaults).** `wait_bound_s` (host time per round, D-4c) and `hold_bound_s`
     (step hold, D-4c) are required. `hold(condition)` holds the step, ticking nothing, until the condition is
     true or the bound passes; the latter raises `HubInvalidRun`. Increment #4 uses it for the handshake.
   - **Frames.** The hub owns the WP-06 `FrameReceiver` and always calls `close()` in a `finally` (WP-06 N1),
     together with the unit links and the adapter link.
   - **Evidence.** A delivery log (`step`, `round`, `flowId`, `from`, `to`, `sequence`, `deliveredAtNs`,
     `deliverAtNs`) and counters (refused, lost, start-up misses, rounds). Payload digests only; no payload in
     the log.
   - **Tests (offline).** Fake units are threads speaking the protocol over real Unix sockets; there is a fake
     adapter link, and the pinned 3.10 adapter on a fake source for one end-to-end test. They cover:
     - determinism: the same inputs give the same delivery log, with units answering in shuffled order;
     - the delay points: F14, F15b and F17 delivered one step later than an equal non-delayed flow;
     - the step rounding: a `deliverAtNs` between boundaries is delivered at the next one;
     - same-step rounds;
     - refused stamps;
     - late binding: no delivery before the first frame, `origin` before step 0, a different second origin
       refused;
     - lost verdicts on disconnect;
     - the start-up deadline with no F17, and that F17 present in time is not lost;
     - the wait bound and `HubInvalidRun`;
     - `hold`;
     - `FrameReceiver.close()` on success and on failure;
     - the contract from the `5f71cde` form.
   - **Out of scope.** Faults and the relay (increment #4, after platform option (A)); the U2 unit entry point and
     the Maestro wiring (increment #5); the role units (WP-13, WP-14).
