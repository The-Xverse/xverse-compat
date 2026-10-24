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
