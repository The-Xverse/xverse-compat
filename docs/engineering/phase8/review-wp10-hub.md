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
2. **Implementation of finding 1 (2026-10-24 12:19:18).**
   - **Change.**
     - `src/xverse_compat/live/hub_topology.py` (new): `SCHEMA`, `from_system_document` and `validate`.
     - `src/xverse_compat/live/hub.py` (new): `HubSchedule`, `UnitLinks`, `Hub`, `HubResult`, `HubInvalidRun`
       and `HubProtocolError`.
     - `tests/live/fixtures/wp10-topology-mloc-5f71cde.json`: a byte-identical copy of blueprints `5f71cde`
       `automotive/assured-aeb/xdl/mloc/topology/system.json`, SHA-256
       `f982be829441aab0c9f621e9119cbb4929928f3606d39850570f2eca0bab07af`.
     - No existing module changed; `live/loop.py`, `live/driver.py` and `live/frames.py` are untouched.
   - **Contract from the real form (MLOC arm).**
     - 20 hub-relevant flows (18 `flows` plus the `returnFlows` F04 and F15b; intra-unit messages excluded),
       with hub unit `vehicle-loop-unit` and adapter unit `carla-adapter-unit`.
     - Delay points `{F04, F14, F15b, F17}`, one step each, as the WP-12 carry-forward row states.
     - Adapter-link flows F01 to F04; every other flow is hub-routed.
   - **Implementation notes, refining finding 1.**
     - The start-up deadline is checked **after** a step's delivery rounds, so an F17 delivered in the deadline
       step counts.
     - A producer that **disconnects** gets its lost verdicts and an `invalid` record, and the run continues, so
       the degraded path still receives `lost`. A **missed wait bound** raises `HubInvalidRun`, as designed.
     - F04's one-step delay is the adapter link's own semantics: the command decided after step `k` is sent with
       the tick request for `k+1` (compat review-wp03 R-5). The hub therefore does not schedule F04, and its
       `hubDelaySteps` is carried in the contract for the record.
     - Determinism has two sources: the round's outputs are collected in unit-id order, and each round's
       deliveries are sorted by `(flow, source unit, sequence)`.
   - **Tests.** `tests/live/test_phase8_hub.py`: 40 tests, offline. Fake units are threads speaking
     `hub-units/1` over real Unix sockets.
     - Contract: the `5f71cde` form pins the four delay points and the adapter-link set; four inconsistent forms
       are refused.
     - Schedule:
       - rounding (`deliverAtNs` at `T_0`, `T_0+20 ms` and `T_0+60 ms` delivered at steps 0, 1 and 2 with
         a 50 ms step);
       - the delay points (a delayed flow at step 1; F17 at `T_0+20 ms` plus its delay at step 2);
       - five refused stamps (future origin, deliver before origin, wrong unit, unknown flow, bool sequence) and a
         repeated sequence.
     - Hub:
       - **determinism**: identical delivery logs with units answering in two different seeded jitter orders;
       - same-step rounds and the one-step delay points;
       - **the real topology**: with fake units for front-zone, adas-hpc, vc-functional and vc-assurance, every
         hub flow's first delivery is at step 0, except F14, F15b and F17 at step 1;
       - **late binding**: ticks without a frame give no step; the origin is the first frame's time; every unit
         receives `origin` before its first round; a different second origin is refused;
       - **lost verdicts**: after a producer disconnects, the local F17 consumer gets `mark_lost` once, the remote
         consumer receives `lost`, and the run is recorded invalid;
       - **start-up deadline**: no F17 gives one lost verdict at the deadline step, and an F17 in time is not lost;
       - required parameters: the F17 deadline (4 cases) and the three bounds (12 cases) have no default; a flow to
         the hub unit without a local consumer is refused;
       - the wait bound: a silent unit raises `HubInvalidRun`, and the frame receiver is still closed; it is also
         closed on success;
       - the bounded `hold`.
     - End to end: the pinned 3.10 adapter on the fake `nominal` source with `--frames`, through
       `SocketAdapterLink` and the WP-06 `FrameReceiver`. 4 steps, every frame `verified`, the local camera
       consumer bound once to the origin 10 000 000 000 ns, and the receiver's socket removed by `close()`.
     - The file was run 5 times with no failure.
   - **Mutation checks (not committed; restored).** Each fails tests:
     - no hub delay: 3;
     - no `deliverAtNs` rounding: 1;
     - no deadline check: 1;
     - no `FrameReceiver.close`: 3;
     - no `origin` sent to units: 1.
   - **Suite.** 459 passed, 39 subtests (base `95e9e7a`: 419).
   - **Residuals.**
     - R-1. The hub delay is **additive** to the rounded AD-30 delivery point. Its relation to the AD-30
       declaration is `TODO: author decision (AD-30)`.
     - R-2. Flow verification and evidence are not yet applied to hub flows. They have only producer-sequence
       monotonicity and the delivery log. The Phase 6 `FlowReceiver` and `FlowEvidence` (Argus) for hub flows,
       and for the adapter flows that `LiteVehicleLoop` verifies today (K-12), are for increment #5 and WP-13.
       Lost verdicts come only from a disconnect, a protocol error or the start-up deadline, not from receiver
       gap verdicts.
     - R-3. No frozen set exists in this increment, so any missed wait bound is an invalid run. Increment #4 adds
       the declared frozen units and the handshake, using `hold`.
     - R-4. Values (`TODO`):
       - the wait bound and hold bound: D-4c;
       - the F17 start-up deadline: AD-07 and WP-13, in simulation time;
       - the frame wait: D-4c.
     - R-5. U2's own elements are passed as local consumers and producers. A producer runs once per step after
       the adapter items, and U2's intra-unit messages (the driver profile, the motion-sensor model) are wired by
       the U2 entry point (increment #5).
     - R-6. The unit transport relies on mode 0600 and the expected unit list; peer credentials are not checked.
       The 65 536-byte line limit means that payloads must be digests or small records.
     - R-7. Only the MLOC form is checked in. The comparator and ablation forms use the same derivation and have
       other unit sets; their fixtures come with increment #5.
     - R-8. Live behaviour, the D-4c bounds and the integration with Maestro are unverified (increment #5,
       E8-3a).
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
