# Review log: Phase 8 WP-03, driver profile and arbitration (xverse-compat)

Candidate `candidate/phase8-wp03-driver-profile-20261024`, base main `372e6b7` (WP-02 merged).
Specification: thesis `specs/002-assured-aeb` rev 3g: `implementation-plan.md` WP-03 and K-3, K-12,
K-15; FR-030, FR-021, FR-024 and FR-028; AD-38 option B (decided by the author), AD-28 and AD-25; ED-15
(engineering); `decisions.md` §H, and §J with `design/wp11-unit-allocation.md` E-5 (driver profile and
ED-15 are a module of the U2 vehicle-loop, in the scenario environment, reading ego speed only from the
adapter's runtime motion item). Decided under the author's delegation of 2026-10-24, flagged for the
author's review. Findings are recorded before repairs. The maturity is an engineering increment
verified offline only: not M1, not AEB evidence, live behaviour unverified (E8-3a, D-1).

## Findings

1. **Design record: driver profile and arbitration (2026-10-24 11:00:44, before any code).**
   - **Starting point (verified at `372e6b7`).** `LiteVehicleLoop` (`live/loop.py` 54–148) calls one
     `command_source(sim_s, last_motion) -> (throttle, brake, meta)` per tick and sends one
     `carla-items/2` command to the adapter, the only actuator writer, which applies throttle and brake to
     the ego with `steer=0.0` (K-3). `sim_s` is the simulation time since the first ticked frame,
     taken from the runtime `vehicle-motion` item's `originNs`; `last_motion` is the latest runtime
     motion item. The Phase 7 sources are `VcuCommands` (`live/driver.py`, the legacy-VCU gateway) and
     `profile_source` (`live/loop.py`, open loop, used by the adapter check). `live/stimulus.py` is the
     Phase 7 pedal stimulus on the legacy zenoh topics, with `--time-base sim` (K-15).
   - **Where it lives.** A new module, `src/xverse_compat/live/driver_profile.py`, providing a command
     source for `LiteVehicleLoop`. `driver.py`, `stimulus.py` and `loop.py` are not changed, so the
     Phase 7 and S1 harness and tonight's soak keep their exact behaviour. The Phase 8 U2 unit entry point
     that uses it is later blueprint and topology wiring (WP-12).
   - **Speed-hold law (FR-030, AD-38 B).** A discrete PI controller on the ego speed error, keyed only to
     simulation time:
     - `e = targetSpeedMps − v`, with `v` = `last_motion.value.speedMps` (the adapter's runtime motion
       item; never the evaluation-only stream, FR-021, E-5);
     - `dt = sim_s − previous sim_s` (0 at the first call); a decreasing `sim_s` is refused;
     - `I ← I + ki·e·dt` only while the output is unsaturated and no brake request is active
       (conditional-integration anti-windup);
     - `throttle = clamp(kp·e + I, 0, throttleMax)`;
     - no wall clock, randomness or hidden state other than `I` and the previous `sim_s`, so a sequence
       of inputs gives a reproducible sequence of outputs.
     - With no runtime motion item yet (or a malformed one), throttle is 0 (fail-closed: the driver never
       accelerates without a speed reading) and the integrator is not updated.
   - **Parameters (protocol values, AD-27).** `targetSpeedMps` (> 0), `kp` (> 0), `ki` (≥ 0) and
     `throttleMax` (in (0, 1]), each finite and not a bool, in a record with `schema`
     `xverse-compat.driver-profile/1` and exactly these members. There are **no defaults**: a missing,
     extra or ill-typed member is refused when the profile is built, before any tick. No parameter file is
     shipped; tests use test-only values. Reading them by identifier from the signed protocol record
     (FR-024) is the WP-17 protocol-record loader.
   - **Arbitration (ED-15).** One function combines the driver's throttle with the AEB brake request of
     the tick:
     - brake request `b` in [0, 1], finite, from the AEB path (a runtime input; in Phase 8 the WP-04
       brake/ESC node through the U2 hub, WP-12);
     - `b > 0`: command `(throttle 0, brake b)` and the integrator is reset to 0, so no wound-up throttle
       surges on release;
     - `b == 0`: command `(driver throttle, brake 0)`;
     - an invalid request (absent where one is required, non-finite, outside [0, 1], or a bool): throttle 0
       and the last valid brake request held, the rule of the Phase 7 `VcuCommands` stale path;
     - the driver itself never brakes: its brake output is always 0, and the brake in a command comes only
       from the AEB request. No steering exists in the command; the adapter holds steer at 0 (AD-28, K-3).
     - The adapter stays the single actuator writer: the arbiter only chooses the one command that the
       loop sends per tick.
     - Meta per tick: driver throttle, speed error, integrator, brake request, `aebActive`, the reason for
       a zero throttle, and the parameter record digest, for the loop's `driver-ticks.jsonl`.
   - **After an AEB release.** FR-030 sets throttle to zero only "while an AEB brake request is active";
     the profile resumes the speed hold, from a reset integrator, when the request returns to 0. Whether a
     scenario should instead latch the driver at zero after an intervention is a scenario-protocol choice
     (AD-25 horizon, AD-27), recorded as a residual, not implemented.
   - **Spawn-at-speed fallback (AD-38 C, GA-33; not implemented).** It would need:
     - a schema-3 live-scenario member such as `initialSpeedMps` (a protocol value, no default);
     - the adapter, the single writer, setting the ego velocity once at spawn before the first tick (for
       example `set_target_velocity` along the spawn-point forward vector), inside the partial-spawn
       rollback, with the observer-v2 check of the reached speed;
     - the driver profile starting with an integrator preset to hold that speed;
     - a live check under E8-3a that the speed is held without a transient, and an AD-25 dry run showing
       that the approach phase does not fit the horizon (the condition of option C).
   - **Tests (offline, `tests/live/test_phase8_driver_profile.py`).**
     - Determinism: identical outputs for identical input sequences; no dependence on host time
       (`time.monotonic` patched to raise); the module imports no `time`, `random` or zenoh.
     - Law: proportional and integral terms, the throttle clamp, anti-windup, `dt` from simulation time,
       a decreasing `sim_s` refused, throttle 0 without a motion item.
     - Arbitration: a brake request forces throttle 0 and resets the integrator; release resumes; an
       invalid request zeroes throttle and holds the last valid brake.
     - Never brakes or steers: over swept inputs the brake equals the AEB request and no command has a
       steering member.
     - Parameters: each missing, extra, bool, NaN, infinite, non-positive or out-of-range member refused,
       and the wrong schema refused.
     - Closed loop: `LiteVehicleLoop` on an in-process fake link with a fake longitudinal vehicle reaches
       and holds the target speed, then zeroes throttle from the tick of a brake request.
     - Phase 7 unchanged: `driver.py`, `stimulus.py` and `loop.py` are byte-identical to the base.
2. **Implementation of finding 1 (2026-10-24 11:03:40).**
   - **Change.** One new module, `src/xverse_compat/live/driver_profile.py`:
     - `SpeedHoldParams.from_record`: the `xverse-compat.driver-profile/1` record, exactly five members,
       no defaults, with a SHA-256 digest of the canonical record carried in every tick's meta;
     - `SpeedHold.step`: the PI law on simulation time with conditional-integration anti-windup;
     - `arbitrate`: the ED-15 rule;
     - `ArbitratedDriver`: the `LiteVehicleLoop` command source.
     - One refinement of finding 1: the integrator is reset on every tick in which the arbiter forces
       throttle to 0, for an invalid request as well as an active one.
     - `live/driver.py`, `live/stimulus.py`, `live/loop.py` and `xverse_compat_carla/` are unchanged
       (`git diff --quiet 372e6b7` on them succeeds). The pytest check of finding 1, "byte-identical",
       is this recorded `git diff` instead, because the suite does not depend on the Git history.
   - **Tests.** `tests/live/test_phase8_driver_profile.py`: 29 tests, offline, with test-only parameter
     values and fake longitudinal dynamics.
     - Parameters: 18 refusals: each missing member; an extra member; a wrong schema; bool, NaN, infinite,
       string and null values; non-positive `targetSpeedMps` and `kp`; negative `ki`; `throttleMax` 0
       and 1.2; a non-object. Plus the digest test.
     - Law: P and I terms with `dt` from simulation time, the clamp, anti-windup, never a negative
       throttle, a decreasing or NaN simulation time refused; throttle 0 and no integration without a
       valid runtime motion item.
     - Arbitration: the rule table; an active request zeroes throttle and resets the integrator; release
       resumes from the reset integrator; invalid requests zero throttle and hold the last valid brake.
     - Never brakes or steers: over swept requests and speeds the brake is always the request, and no
       command or meta carries a steering member.
     - Determinism: two closed-loop runs give identical commands; driving the arbiter with every host
       clock function patched to raise gives the same outputs; the module imports only `dataclasses`,
       `hashlib`, `json`, `math` and `typing`.
     - Closed loop on `LiteVehicleLoop` with an in-process fake link: the speed is within 0.1 m/s of the
       target from 15 s to 25 s, the brake is 0 until the request, and from the first tick decided at
       25 s the command is `(0, 1)` with `aebActive`.
   - **Mutation checks (not committed; restored).** Passing the driver throttle through during braking
       fails 5 tests; a default `targetSpeedMps` fails the missing-member case; removing the lower
       throttle clamp fails 2 tests.
   - **Observation during testing.** In `driver-ticks.jsonl` a row's `simS` is the simulation time
     after its tick; the command of that row was decided at the previous row's `simS` (`loop.py` 94 and
     115), and the first two ticks are both decided at 0.0. The closed-loop test keys on the decision
     time. See R-5.
   - **Suite.** 356 passed, 39 subtests (base `372e6b7`: 327).
   - **Blueprint and topology wiring needed later (not made here).**
     - B-1. A U2 vehicle-loop unit entry point (WP-12) that builds
       `LiteVehicleLoop(link, ArbitratedDriver(params, brake_request), ...)` beside the gateway, flow
       receivers and the other U2 modules (E-3 to E-6, E-11, E-15). `live/driver.py` stays the Phase 7
       `lite-driver`.
     - B-2. In `xverse-blueprints` `automotive/assured-aeb`: the U2 unit command in its `units.py`
       (the K-11 pattern: a real ELF interpreter, `PYTHONPATH` to the pinned venv), passing the path of
       the driver-profile parameter record taken from the AD-27 protocol record.
     - B-3. The `brake_request` source: the latest brake request of the WP-04 brake/ESC node through the
       U2 hub (WP-12), keyed to simulation time, with its validity and staleness rules declared there. For
       D-1, a declared characterisation schedule (brake at a declared simulation time) may stand in, as
       engineering data only.
     - B-4. A Phase 8 run command that records `driver-ticks.jsonl`. The Phase 7 `run-live.sh`,
       `run-baseline.sh`, their `units.py` and the soak are not changed.
   - **Residuals.**
     - R-1. Live behaviour is unverified (E8-3a, D-1): convergence and overshoot on the CARLA vehicle.
       `targetSpeedMps`, `kp`, `ki` and `throttleMax` are protocol values (AD-27) chosen after D-1;
       stability depends on them. "Reaches and holds" is shown on test-only fake dynamics only.
     - R-2. Reading the parameters by identifier from the signed protocol record (FR-024) is the WP-17
       loader. No parameter file is shipped.
     - R-3. The brake request's source, validity window and staleness in simulation time belong to WP-04
       and WP-12. The invalid-request rule (throttle 0, last valid brake held) reuses the Phase 7 stale
       rule and is confirmed under the ED-15 review.
     - R-4. After an AEB release the hold resumes, from a reset integrator (FR-030 literal). A latch at
       zero after an intervention is a scenario-protocol choice (AD-25, AD-27), not implemented.
     - R-5. Decision timing: each command is decided from the previous frame's motion and simulation
       time, so the response to a brake request first takes effect one frame later in simulation time.
       This is inherent to `LiteVehicleLoop` and must be accounted for in the D-1 latency analysis and
       the AD-30 declaration.
     - R-6. The driver reads the adapter's `vehicle-motion` item, which shares the `World.get_snapshot`
       source with the ground truth (C-12). This is permitted for the scenario environment (E-5, FR-030);
       it is not an AEB runtime input (AD-32 covers those).
     - R-7. A decreasing simulation time raises in the command source and so ends the loop (fail-closed);
       in U2 that ends the run.
     - R-8. Spawn-at-speed (AD-38 C, GA-33) is not implemented; finding 1 lists its needs.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 11:05:54).**
   - **Reviewer and method.** An independent reviewer who did not write the code.
     - Read `c8c418c` and `7ab8fc4` against base `372e6b7`, and `live/loop.py` 54–148 and
       `live/driver.py` 37–58 at the base.
     - Checked them against thesis FR-030, AD-38 (decision text and `review/decision-proposals-20261024.md`
       option B), ED-15 (`decisions.md` 107), §H, §J and `design/wp11-unit-allocation.md` E-5 and U2.
     - Ran the offline suite and three behaviour probes on the module under the venv's CPython 3.13.13.
       U2 is a CPython 3.13 unit (§J).
     - The worktree was not changed except for this entry.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** The module has no caller yet: wiring is B-1
     to B-4, under WP-12. MEDIUM-1 and MEDIUM-2 should be repaired or decided before that wiring, and
     MEDIUM-3 before any run in which an AEB release can occur before the horizon ends. The merge still
     awaits the author's acceptance.
   - **Evidence.**
     - Suite: 356 passed, 39 subtests.
     - Phase 7 is unchanged: `git diff --quiet 372e6b7 -- src/xverse_compat/live/driver.py
       src/xverse_compat/live/stimulus.py src/xverse_compat/live/loop.py src/xverse_compat_carla`
       succeeds. The candidate changes only the new module, its test and this log.
     - PI law (driver_profile.py 66–88).
       - `dt` comes from successive `sim_s` only, and a decreasing or non-finite time is refused.
       - The output is clamped to `[0, throttleMax]`.
       - Conditional integration: a step is kept only if the unclamped output stays in band, and the
         integrator is reset on every forced tick.
       - This is a sound, bounded anti-windup: the integrator cannot grow while saturated, and the clamp
         bounds the output regardless.
     - Parameters (39–55). The record has exactly five members, with the schema checked. Values must be
       finite, not bools, with `targetSpeedMps > 0`, `kp > 0`, `ki ≥ 0` and `0 < throttleMax ≤ 1`, and
       there is no default. Eighteen refusal cases pass.
     - Arbitration (99–112, 128–142).
       - The command's brake is only ever the request or the held request; the driver contributes 0.
       - There is no steering member, and the adapter holds steer at 0 (K-3).
       - The module only returns the one command that `LiteVehicleLoop` sends (`loop.py` 94–96), so the
         adapter stays the single writer.
     - Determinism. The module imports only `dataclasses`, `hashlib`, `json`, `math` and `typing`. The
       state is the integrator, the previous `sim_s`, the held brake and a counter, so equal inputs give
       equal outputs, and the host-clock patch test pins this.
     - R-5 is accurate. `loop.py` 94 decides with the previous frame's `sim_s` and motion, and 115 then
       advances `sim_s`. The first two decisions are both at 0.0, with `dt` 0, and a tick with no items
       repeats the decision time.
   - **Issues (none blocks the merge).**
     - **MEDIUM-1: a stale motion item is treated as a valid speed.**
       - Where: driver_profile.py 91–96 and 132; `loop.py` 105–106, 115 and 123–124.
       - `LiteVehicleLoop` keeps the last motion item while later ticks carry none. The adapter omits
         motion on a stale snapshot (`sources.py` 222). `sim_s` still advances from the other items'
         `originNs`.
       - The driver therefore keeps integrating on a frozen speed. Probe: speed frozen at 2.0 m/s for
         5 s of simulation time gave throttle `throttleMax` (0.8) throughout, while the real vehicle
         would accelerate. A frozen speed just below the target winds the integrator up to the same
         output.
       - The "no motion means throttle 0" rule (finding 1) covers only the time before the first item.
       - An AEB request still overrides it, so this is a scenario-validity issue, not an AEB-safety one.
       - Proposed fix: give zero throttle and no integration when the item's `originNs` has not advanced
         while `sim_s` has. Equivalently, pass the loop's `vehicle-motion` receiver verdict through
         B-1. Otherwise, declare it as a residual with D-1 detection.
     - **MEDIUM-2: an out-of-range brake request gives no braking, which differs from Phase 7.**
       - Where: driver_profile.py 107–109 and 130.
       - Phase 7 `VcuCommands` (`driver.py` 56) clamps a fresh brake into [0, 1]. This module refuses any
         value outside [0, 1] and holds the last valid brake.
       - Probe: a valid 0.0 followed by 1.0000001 (a float-rounding overshoot) and then 1.2 commanded
         `(0, 0)` both times. The AEB asked for full braking, and the vehicle coasted.
       - Throttle 0 is safe, but a request above 1 is still an unambiguous request to brake. Refusing it
         is not the safe direction for the brake channel, and it is not "the rule of the Phase 7 stale
         path" (R-3), which concerns staleness, not range.
       - Proposed fix: treat finite values above 1 as 1.0 with a recorded `requestClamped`, as Phase 7
         does, and keep NaN, infinities, bools and negatives invalid. Otherwise, declare in R-3 that
         WP-04's contract guarantees [0, 1] and that a violation fails D-1, not just a counter.
     - **MEDIUM-3: R-4 is honest but understates the release behaviour.**
       - Where: driver_profile.py 78–79 and 87; finding 2, R-4.
       - Because the integrator is reset at release, the first tick after release is the P term alone.
         After an AEB stop the error equals the target speed.
       - Probe: release from standstill gave throttle `throttleMax` (0.8) on the next tick. The driver
         re-accelerates at full authority toward the stationary target (WP-02).
       - FR-030 and AD-38 B ("inattentive driver") permit this, but the paired outcome (FR-037: collision
         or not, minimum gap) then depends on behaviour after the release.
       - R-4 should state the immediate `throttleMax` re-acceleration, and it should gate the latch or
         end-at-standstill decision (AD-25 horizon, AD-14 outcome window, AD-27) before any evaluation
         run in which a release can precede the horizon end. That decision cannot wait until after the
         runs.
     - **LOW-1: the meta does not show that an invalid request is holding a brake.**
       - Where: driver_profile.py 133 and 138–141.
       - An invalid request that holds a non-zero brake records `aebActive: false` with `brake > 0`.
         The reason `invalid-request` explains it, but D-1 latency tooling that keys on `aebActive` would
         miss held braking.
       - Optional: add `brakeHeld: true`.
     - **LOW-2: the digest depends on how numbers are written in the record.**
       - Where: driver_profile.py 54.
       - `8` and `8.0` give different digests for the same parameters. That is acceptable for
         identifying a record, but it needs stating once WP-17 binds the digest to the AD-27 record.
     - **LOW-3: B-3 does not say what the request source returns with no AEB output.**
       - A source that returns `None` before the WP-04 node's first message makes every tick invalid, so
         the throttle stays 0 and the approach never starts. That is fail-closed, but it would read as a
         driver failure.
       - Add to B-3 that the source returns 0.0 when no request is active and `None` only for a stale or
         lost source. B-1 should also carry the motion freshness of MEDIUM-1.
   - **Wiring B-1 to B-4.** Complete for the module, with the LOW-3 and MEDIUM-1 additions. B-4 correctly
     leaves the Phase 7 harness, its `units.py` and the soak untouched.
   - **Residuals R-1 to R-8.** R-1, R-2, R-5, R-6, R-7 and R-8 are accurate. R-3 needs MEDIUM-2's range
     point, and R-4 needs MEDIUM-3. Missing: the stale-motion behaviour of MEDIUM-1.
   - **Recommendation.**
     - Merge after the author's acceptance, recording MEDIUM-1 to MEDIUM-3 in a disposition.
     - MEDIUM-1 and MEDIUM-2 are small code repairs on this branch and are best done before B-1.
     - MEDIUM-3 is a thesis-side decision (AD-25, AD-14, AD-27) before evaluation runs.
     - LOW-1 to LOW-3 are optional.
4. **Disposition of finding 3 (2026-10-24 11:07:48; decided by the coordinator under the author's delegation of
   2026-10-24, flagged for the author's review). Recorded before repair.**
   - **Thesis input.** `decisions.md` now holds the AD-38 amendment (11:07, under the delegation, flagged
     for review; basis this review's MEDIUM-3). After the first AEB intervention, meaning the first tick
     with a brake request above 0, the driver's throttle latches at 0 for the rest of the run. This
     replaces FR-030's "resumes" wording; option C is unchanged.
   - **Repairs, with tests.**
     - MEDIUM-1, stale motion: when the motion item's `originNs` does not advance, zero throttle and no
       integration, with `motionStale` in the meta.
     - MEDIUM-2, brake range: a finite request above 1 is clamped to 1.0, with `brakeClamped` recorded,
       as Phase 7 does (`driver.py` 56). NaN, infinities, bools and negatives stay invalid.
     - MEDIUM-3, the AD-38 amendment: the throttle latch, with `latched: true` in the meta; the design and
       the FR-030 note in this log are updated.
     - LOW-1: `aebActive` is true whenever the commanded brake is above 0, including a held brake under an
       invalid request.
     - LOW-2: numbers are canonicalized in the parameter digest, so that 8 and 8.0 give the same digest;
       the rule is recorded.
   - **Documentation.** LOW-3 goes into B-3: the request source returns 0.0 while no AEB request is active,
     including before the first message.
