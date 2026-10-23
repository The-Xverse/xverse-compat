# Review log: Thesis Lite stabilization S1c (xverse-compat)

Candidate `candidate/lite-stabilization-s1c-20261023`, base main `39d31fa`. Specification: thesis
`specs/029-lite-stabilization` rev 4a, decisions of 2026-10-23 (ES-0). It covers S1c-1: FR-015 (T-3) and
FR-022. The blueprint part of S1c-1 (FR-014, FR-015 T-2/T-5, FR-016, FR-017) is on the
`xverse-blueprints` candidate of the same name. Findings are recorded before repairs. The maturity is an
engineering stabilization candidate: not M1, not AEB evidence.

## Findings

1. **FR-022: the guard destroyed a moving ego (planning review 2, finding N1).**
   - `restore.py` held the ego and then destroyed it straight after the settings restore. In the
     cancel-paused evidence the ego still moved at 2.82 m/s when it disappeared.
   - **Change.** With an asynchronous restore target, held egos are polled with brake until they are below
     0.05 m/s, or until 5 s, recorded as a failure (`restored: false`). The record now carries
     `standstill`, `unpauseMonotonicNs` (the first apply-and-commit) and `destroyMonotonicNs`. A
     synchronous target cannot reach standstill without a tick owner and is recorded as not applicable.
   - **Tests.**
     - `test_s1_fr022_guard_holds_a_moving_ego_until_standstill_before_destroying_it`: the ego is destroyed
       at 0.0 m/s, and the timestamps are ordered.
     - `..._standstill_timeout_is_a_recorded_failure`.
     - `..._synchronous_target_does_not_wait_for_standstill`.
     - The fake actor gains `get_velocity`.
2. **T-3: tests for the step-aware retry exposed a latent defect (2026-10-23).**
   - **Tests.** `test_s1_t3_retry_continues_until_mode_and_step_both_match` and
     `test_s1_t3_retry_stops_after_three_attempts_and_fails`.
   - **Defect.** The first test fails at this commit with `applyAttempts == 3`. The retry commits a tick
     only when the world was synchronous *before the guard started* (`before["synchronousMode"]`). If the
     first attempt switches an asynchronous world to synchronous without the step, the later attempts are
     applied to a synchronous world but never committed, so the retry cannot converge.
   - **Live reach.** The live guard restores either asynchronous mode or a recorded synchronous state, and
     CARLA normally applies mode and step together, so this has not been observed live. The test documents
     the path.
   - **Repair (next commit).** Tick whenever the world is synchronous at the time of each attempt.
