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
