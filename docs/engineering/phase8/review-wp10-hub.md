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
3. **Independent review of findings 1 and 2 (2026-10-24 15:14:18).** Reviewer: an independent Claude agent that did
   not write the increment. Scope: `0cd7d44` and `07f8641` on `95e9e7a`. **Verdict: PASS WITH NOTES.** Nothing blocks
   the merge of increment #2. M1 must be repaired before increment #4 introduces frozen units, or before the first
   live hub run, whichever comes first. M2 needs a recorded rule before increment #4/#5 wires a real consumer.
   - **What was checked, and the result.**
     - **Suite.** The offline compat suite gave **459 passed, 39 subtests**. `test_phase8_hub.py` was run twice more:
       40 passed each time. The end-to-end test with the pinned 3.10 adapter and `--frames` passes: 4 steps, all
       frames `verified`, the origin bound once, and the receiver's socket unlinked.
     - **Topology contract.**
       - **Provenance.** The fixture is byte-identical to blueprints
         `5f71cde:automotive/assured-aeb/xdl/mloc/topology/system.json`. The SHA-256 is `f982be82…bab07af`, recomputed
         from the blueprints object, not only from the copy.
       - **No blueprint import.** `hub_topology.py` imports only `typing`, and `hub.py` only the standard library and
         `.hub_topology`.
       - **Derivation.** It matches the form: `flows` and `returnFlows`, endpoint owners, `hostedElements` against
         `hostUnit`, `intraUnit` skipped, and the adapter-link route rule.
     - **Delivery rule.** It matches `decisions.md` "AD-30 delivery rule" and the new "Hub delay semantics" row:
       - the delivery is the first boundary at or after `deliverAtNs` (`hub.py:86-87,115-116`), plus the additive
         `hubDelaySteps` (`:123`);
       - same-step messages go to a later round;
       - the deliveries are sorted by `(flow, source unit, sequence)` (`:126`), and the outputs are collected in
         unit-id order (`:353-375`), so the delivery log does not depend on the reply order. The jitter test shows
         this.
     - **Zero-delay cycle (the coordinator's question).** **No livelock.** With `f-c-a` changed to delay 0 and units
       that chain on every delivery, a scratch probe raises `HubInvalidRun` ("more than 6 delivery rounds") at step 0
       in under 10 ms (cap = units + 1, `hub.py:378-393`). With the declared delay the same units end normally (3
       steps, max 3 rounds). The suite does not test the cap itself (L1).
     - **Late origin binding.** It is bound at the first frame only. Ticks without items give no boundary (`:422-426`).
       `bind_origin` runs on local consumers, and `origin` goes to every live unit before step 0's first round. A
       second, different origin is refused (`:288-299`).
     - **Lost verdicts.** On EOF, a protocol error or a send failure, `_unit_gone` marks each produced flow lost once:
       `mark_lost` locally, `lost` to the live remote consumers (`:301-320`). A missed wait bound is
       `HubInvalidRun` (`:362-366`), as designed.
     - **The F17 start-up deadline.** It is in simulation time (`sim_ns >= origin + deadline`) and checked after the
       step's rounds (`:322-328,444`). It is required whenever F17 exists (`:267-268`).
     - **Bounds.** `wait_bound_s`, `hold_bound_s`, `connect_timeout_s` and `frame_wait_s` (with frames) are required,
       finite and positive, and booleans are excluded (`:49-52,256-260`). The hold is bounded and raises
       `HubInvalidRun`.
     - **`FrameReceiver.close()`.** It is in `run()`'s `finally` (`:448-452`), on success, on `HubInvalidRun`, on a
       protocol error and on an accept failure.
     - **Transport.**
       - The socket is created with mode **0600** (checked with `stat`: `0o600`) and unlinked by `close`.
       - The inbound line limit is 65 536 bytes, with strict UTF-8 and no NaN (`:180-189`). The hello is read
         within the connect deadline (`:163-169`).
       - No peer credentials are checked, which R-6 records honestly.
   - **Issues.**
     - **M1 (MEDIUM; does not block the merge of #2; repair before increment #4 or the first live hub run): hub
       writes to units have no time bound, so the hub can hang without bound.**
       - **The cause.** `accept_all` sets each unit socket to blocking with no timeout (`hub.py:174`). `send` writes
         and flushes through `makefile("wb")` (`:203-212`). `UnitLinks.close()` sends `end` to every unit before the
         shutdown (`:214-216`), and that close runs inside `run()`'s `finally` (`:452`).
       - **Probe.** A unit that connects and then never reads blocks `send()` after 44 rounds of about 4 KB
         (`send()` still blocked after 3 s). `UnitLinks.close()` with that unit is also still blocked after 3 s.
       - **Consequence.** No timeout fires in this state, so neither `HubInvalidRun` nor the `finally` cleanup
         (frames close, listener unlink) is reached. It is unreachable in practice today: a silent unit misses the
         wait bound after its first round, long before its socket buffer fills.
       - **When it becomes reachable.** Under increment #4, a frozen unit (SIGSTOP) keeps receiving round-0
         messages without reading.
       - **Repair.** Give sends a timeout from the round deadline, or use `MSG_DONTWAIT` with a bound that is
         treated as a lost unit, and shut down before sending `end` in `close`, or send `end` non-blocking. A test
         with a non-reading unit should show `close()` within a bound.
     - **M2 (MEDIUM; does not block the merge; a rule is needed before the consumer wiring): a flow declared lost can
       still be delivered afterwards.**
       - **The cause.** `_mark_lost` records the verdict, but `HubSchedule.due` still returns messages already
         admitted on that flow (`hub.py:123,301-313,342-344`).
       - **Probe.** `uc` produces F17 at step 0 with `deliverAtNs = T0 + 3·STEP` and disconnects. The lost verdict
         comes at step 1 (`mark_lost` once), and the F17 is then **delivered at step 4**: the reader gets `mark_lost`
         and then `deliver`. The same holds after a start-up-deadline loss, when a late F17 arrives.
       - **Why it matters.** Whether a delivery after a lost verdict is valid in-flight data or must be discarded is a
         semantic choice. It decides what `BrakeCommandReader` and the degraded path see, and it must be recorded:
         drop the pending items of a lost flow, or document that `lost` is a verdict about the producer and not a
         barrier, and test the chosen rule.
       - **Scope.** With the one-step F17 delay and `deliverAtNs` inside the step, the loss is detected after that
         step's delivery, so the common case is unaffected.
     - **L1 (LOW): the cap on same-step rounds is untested.** Every hub test emits only in round 0 (`_emit_round0`;
       `test_phase8_hub.py:149-156`), so neither chaining over three or more rounds nor the cap (`hub.py:392-393`) is
       exercised. My probe above is a ready test: an undeclared zero-delay cycle raises `HubInvalidRun`, and the
       declared delay terminates.
     - **L2 (LOW): the code closes less than the design record says.** Finding 1 says the hub closes the frame
       receiver "together with the unit links and the adapter link" (`review-wp10-hub.md:82`). The `finally` closes
       only the frames and the unit links (`hub.py:448-452`), and the end-to-end test kills the link itself
       (`test_phase8_hub.py:435`). Either close or kill the link in the `finally`, or correct the record so that the
       caller (the increment #5 entry point) owns the adapter link.
     - **L3 (LOW): a malformed `outputs` field escapes as a bare `TypeError`.** A unit `outputs` whose `messages` is
       not a list, for example `5`, raises a `TypeError` out of `run` (`hub.py:373`), not a `HubProtocolError` or a
       lost unit. It still fails closed through the `finally`. Validate `type(messages) is list` and treat a violation
       as a protocol error of that unit.
     - **L4 (LOW): outbound lines have no size limit.** A `round` line aggregates the payloads of every delivery to
       one unit (`hub.py:346-348,355`), and no limit is applied when sending. A line above 65 536 bytes would be
       refused on the unit side (R-6), not fail-closed at the hub. Check the size before sending, and raise
       `HubProtocolError` or `HubInvalidRun` above `MAX_LINE`.
     - **L5 (LOW): the step boundary falls back to another stream's time.** `frame_ns` is the `vehicle-motion`
       `originNs`, but falls back to the maximum `originNs` of the other items when motion is absent (`hub.py:421`).
       A step without motion therefore takes its boundary from another stream's time, for example a sensor origin.
       That is fail-closed only when it does not increase. Prefer the adapter's tick frame time, or refuse a
       motion-less step, and record the choice.
     - **L6 (LOW, editorial): R-1 still reads `TODO`.** R-1 (`review-wp10-hub.md:164-165`) is now settled by the
       `decisions.md` row "Hub delay semantics" (12:19, under the author's delegation), which confirms the additive
       rule. R-1 and the corresponding `TODO: author decision (AD-30)` in finding 1 (`:40`) should cite that row.
       The row is still flagged for the author's review.
     - **L7 (LOW): no cleanup if `run()` is never reached.** If `Hub.__init__` refuses its arguments, the
       caller-supplied `FrameReceiver` is never closed. If `run()` is never called, the unit listener stays bound. A
       `close()` on `Hub`, or a documented caller responsibility before `run()`, would complete WP-06 N1.
   - **Residuals R-1 to R-8.**
     - **R-1** is resolved by the "Hub delay semantics" row (L6).
     - **R-2 to R-8** are honest and correctly scoped.
     - **Proposed additions:**
       - **R-9.** Unbounded unit writes and `end` on close (M1); to repair before increment #4.
       - **R-10.** The rule for deliveries on a flow already lost (M2).
