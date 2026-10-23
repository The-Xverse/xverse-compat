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
3. **Repair of finding 2.**
   - Each attempt records the mode it is applied in (`synchronous_now`) and commits with a tick when that
     mode is synchronous.
   - Suite with `/dev/shm/compat-p6-venv` (installed platform wheel = platform main `8b3d8c8e8`): 202
     passed, 39 subtests.
4. **The blueprint part of S1c-1 is on `xverse-blueprints` `candidate/lite-stabilization-s1c-20261023`, commit
   `3a3da84`, base `e7a6ebc`.**
   - **FR-014.** `require_compat` in `lib-live.sh`: `run-live.sh` and `run-baseline.sh` refuse with exit 4
     and a BLOCKED line when `XVERSE_COMPAT_SRC` is unset or is not a compat checkout. Both were checked:
     exit 4. The default path to the Phase 7 candidate worktree is removed.
   - **FR-016.** `legacy_identity` records the revision, dirty count and diff hash for the bridge
     repository and the legacy VCU in both commands. It was checked on `vcu_zenoh`: `125566e`, dirty 0.
   - **FR-015 T-2.** After a normalisation, the baseline lists the world again into
     `world-after-normalisation.json`. `world-before.json` keeps the found state. The vehicle checks and
     the leftover set use the starting world.
   - **FR-015 T-5.**
     - (a) A world with any vehicle is refused, as in the Lite preflight.
     - (b) 143 is accepted only for a process the script sent TERM to; 137 (KILL) still fails.
     - (c) Every exit writes `baseline-exit.txt` through `finish`.
     - (d) The world queries catch `RuntimeError`, print one line and fail closed.
   - **FR-017.** The harness records `persistenceFailure`, `closureDiagnostics`, `closureWriters`,
     `closureTerminalReports` and `dispatchTerminal` in `maestro-run.json`.
   - **Checks.** `bash -n` and Python AST parse pass. The live behaviour is verified in the VS-09
     confirmation and in S1d, both after ES-1.
5. **Independent implementation review 1 (2026-10-23 about 11:35): FAIL. Recorded before repair.**
   - **MEDIUM:**
     - **S1c-R1-1.** An exception from `get_actor` or `get_velocity` during the standstill wait skips the
       destroy, and the record is lost (`restore.py:53-71, 180-182`).
     - **S1c-R1-2.** The FR-017 facts are computed unguarded inside `finally`. A raising `public_data()`
       would lose `maestro-run.json` and skip `dispose()`. `str(None)` writes the string "None", and the
       dataclasses are stored as repr strings.
     - **S1c-R1-3.** `baseline-exit.txt` is not written on every exit: not on a signal after the trap
       reset, not on a `set -u` abort, and not on the pre-run `require_compat`. The log overstated this.
     - **S1c-R1-4.** FR-014's "and records it" is missing: neither command records the compat path, and a
       relative path resolves differently in different places.
   - **LOW:**
     - **S1c-R1-5.** `legacy_identity` fails open for a non-repository path.
     - **S1c-R1-6.** T-5 (d) is partial: `get_actors` sits outside the try, the leftover-destroy snippet is
       unguarded, and the heredoc parser traces back on an empty file.
     - **S1c-R1-7.** The FR-022 record is imprecise: the un-pause time is taken before the commit and is
       None when no change was needed; egos already gone are silent; the synchronous-target reason text is
       wrong.
     - **S1c-R1-8.** The test fakes decay speed per poll instead of per tick, and the patch of the timeout
       constant does nothing.
     - **S1c-R1-9.** Traceability:
       - finding 1 was recorded with its repair;
       - the blueprint findings were recorded after the blueprint commit;
       - T-5 (a) refuses vehicles only after the normalisation has changed the settings.
   - **Verified by the reviewer:**
     - the `synchronous_now` fix for both callers;
     - the bounded wait with no tick owner;
     - `START_WORLD` usage;
     - the `TERMED` bookkeeping;
     - no remaining candidate default;
     - the FR-017 attribute names, against platform `8b3d8c8e8`;
     - CARLA 0.9.15 semantics of `get_actor`, `get_velocity` and `wait_for_tick`.
6. **Repairs for review 1 (finding 5).**
   - **Compat, this commit:**
     - **R1-1.** The standstill wait is wrapped in a handler. An error is recorded as `standstill.ok: false`
       with `error`, and the destroy always follows. Test
       `test_s1c_r1_1_a_failing_standstill_wait_still_destroys_owned_actors`.
     - **R1-7.** The record now carries `holdMonotonicNs` and `unpauseMonotonicNs` (taken after the first
       apply-and-commit). When no change was needed, `unpauseReason` says so. Egos already gone are listed
       `absent: true`. The synchronous-target reason text is corrected. Test
       `test_s1c_r1_7_absent_held_ego_and_unpause_anchor_are_recorded`.
     - **R1-8.** The fake velocity changes per tick (`_World.tick` advances the actors), as a CARLA
       snapshot does. The dead constant patch is removed. The fake client returns an error response for
       an unknown actor ID instead of raising.
     - Suite: 204 passed, 39 subtests.
   - **Blueprints, commit `3595ed0`:**
     - **R1-2.** The FR-017 facts, plus `normalUnitRecordsComplete` and `nativeUnits`, are computed by
       `_fact`, which returns JSON data (dataclasses as dicts, None as null) or `{"error": ...}`. A
       failing fact can no longer lose `maestro-run.json` or skip `dispose()`.
     - **R1-3.** The baseline sets a persistent `on_exit` EXIT trap. INT and TERM exit with 130 and 143.
       Every exit after the run directory exists writes `baseline-exit.txt`, including signals and
       `set -u` aborts. The pre-run `require_compat` refusal exits 4 before a run directory exists; that
       is documented and intended. Checked: a blocked preflight wrote `4`.
     - **R1-4.** `require_compat` resolves the path with `realpath`, and both commands record
       `compat-src <absolute path>` in `identities.txt`. Checked: a relative path was resolved and
       recorded.
     - **R1-5.** `legacy_identity` prints `unknown error=not-a-git-checkout` for a non-repository path.
     - **R1-6.** `get_actors` is inside the try in both world queries. The leftover-ID parser and the
       leftover destroy fail closed in one line.
     - **R1-9.** Vehicles are refused before the normalisation changes anything, and again after it (for
       a spawn that appears on the commit tick).
   - **Traceability (R1-9).** Finding 1 was recorded with its repair (`076b25f`), and the blueprint
     findings after the blueprint commit. Both are noted here. Review-1 findings were recorded before these
     repairs (`e77d655`).
7. **Independent implementation review 2 (2026-10-23 about 11:55): FAIL, one MEDIUM. Recorded before repair.**
   - **MEDIUM S1c-R2-1 (verified on a reduced copy).** A process-group SIGINT, such as Ctrl-C, also kills
     the `tee` of `exec > >(tee …)`.
     - In `run-baseline.sh`, `on_exit` then writes to a closed pipe, and bash dies of SIGPIPE before it
       writes `baseline-exit.txt`, before `kill -KILL` and before the observer is stopped. The legacy
       children run in the background with SIGINT ignored, so they can survive the cleanup's `kill -INT`
       and leak.
     - `trap - EXIT INT TERM` at the start of `on_exit` lets a second signal during the 3 s cleanup kill
       bash.
     - The same output-before-guard pattern exists in `run-live.sh` `cleanup()`, which predates S1c. There
       it can skip the restore guard. This is a hypothesis; it was not run.
   - **LOW S1c-R2-2.** `diagnostics`, `steps` and `workArtifacts` are still computed unguarded in the
     `finally` block. One bad receipt turns the whole `closureTerminalReports` list into one error. `_fact`
     has no unit test.
   - **LOW S1c-R2-3.** An ego already gone before the guard is still silent in the control and destroy
     results. The `absent` branch is untested. The error path records `timedOut` as bare IDs.
   - **LOW S1c-R2-4.** `unpauseMonotonicNs` is set even when the commit tick raised. The docstring omits
     `holdMonotonicNs` and `unpauseReason`.
   - **LOW S1c-R2-5.** README:
     - the trap cleanup skips TERM;
     - the standstill wait applies only to an asynchronous target;
     - a missing `XVERSE_COMPAT_SRC` exits 4 without `baseline-exit.txt`.
   - **Verified by the reviewer:**
     - R1-1, R1-2 (`_fact` on the real platform classes), R1-4, R1-5, R1-6, R1-8 and R1-9.
     - R1-3 for TERM, `finish`, `set -u` and the blocked preflight.
8. **Repairs for review 2 (finding 7).**
   - **R2-1 (MEDIUM, blueprints `a4aa67d`).** Both commands start the log as
     `exec > >(trap '' INT TERM; exec tee …)`, so the `tee` survives a Ctrl-C of the process group.
     `run-live.sh` `cleanup()` and the baseline `on_exit()` now begin with
     `trap - EXIT; trap '' INT TERM PIPE`. The baseline writes `baseline-exit.txt` before any output.
     - **Check (reduced copy, the same pattern):** a background child that ignores INT was started, and
       SIGINT was sent to the whole process group. Result: exit file `130`, the child killed by the
       cleanup, the complete log written.
     - This also covers the pre-existing `run-live.sh` case, where the guard could be skipped.
   - **R2-2 (LOW, blueprints `a4aa67d`).** `executionSucceeded`, `cleanupComplete`, `diagnostics`,
     `dispatchDiagnostic`, `steps` and `workArtifacts` also go through `_fact`. Each terminal report
     is guarded on its own. `_fact` has no blueprint unit test, because the blueprint suite is the live
     test. Review 2 verified it against the real platform classes.
   - **R2-3 (LOW, compat).** The guard records `holdFailed` and `destroyFailed` IDs, typically egos
     that the adapter's close had already destroyed. `timedOut` entries are always dicts. Tests:
     `test_s1c_r2_3_an_ego_gone_before_the_guard_is_recorded` and
     `test_s1c_r2_3_absent_branch_of_the_standstill_wait`.
   - **R2-4 (LOW, compat).** The record carries `commitTickRaised`, and the docstring lists every
     field.
   - **R2-5 (LOW, blueprints).** The README states the interrupt-cleanup sequence (INT, then KILL after
     3 s), the asynchronous-only standstill wait, and that a missing `XVERSE_COMPAT_SRC` exits 4
     before any run directory exists.
   - Compat suite: 206 passed, 39 subtests.
9. **Independent implementation review 3 (2026-10-23 about 12:05): FAIL, one MEDIUM. Recorded before repair.**
   - **Resolved:** R2-1 to R2-5. The reviewer checked, on reduced copies under a process-group SIGINT plus a
     second INT and a TERM during the cleanup, that the baseline wrote `130` and left no children, and that
     the Lite guard step completed.
   - **MEDIUM S1c-R3-1 (verified on a reduced copy).**
     - **Cause.** `run-live.sh:40` is `trap cleanup EXIT INT TERM`, and `cleanup` never exits.
     - **Effect.** An INT or TERM before the Maestro run cleans up, and then the script *continues* into the
       run. With S1c's `trap '' INT TERM` that run is unprotected: no further signal stops it, and no guard
       or residue check follows. This breaks FR-021 "on every stop and cancel path".
   - **LOW:**
     - **S1c-R3-2.** The interrupted log shows `maestro-harness exit=1`, the initial value of `$PYTEST`.
     - **S1c-R3-3.** `commitTickRaised` is set by any attempt, but the un-pause time belongs to the first.
     - **S1c-R3-4 (pre-existing).** The marker loop catches only `ValueError`. An `OSError`, or a non-object
       marker, could lose the record.
     - **S1c-R3-5.** A signal between the baseline's `mkdir` and the EXIT trap leaves no exit file, which
       contradicts the README.
10. **Repairs for review 3 (finding 9).**
    - **R3-1 (MEDIUM, blueprints `14ebce9`).** `run-live.sh` uses `trap cleanup EXIT` with
      `trap 'exit 130' INT` and `trap 'exit 143' TERM`, as the baseline does. A signal at any point now
      ends the script through `cleanup` and never resumes the run.
      - **Check (reduced copy with the same trap lines):** SIGINT to the process group during a preflight
        step without `|| exit`, then a second SIGINT during the cleanup. The log shows the guard start and
        `guard-done`, no `AFTER-PREFLIGHT` line, and `script exit=130`.
    - **R3-2.** `cleanup` records `local rc=$?`, and the last line now reads
      `maestro-harness exit=$PYTEST script exit=$rc`.
    - **R3-3 (compat).** `commitTickRaisedAttempts` lists the attempt numbers whose commit tick raised;
      the un-pause time belongs to attempt 1. Documented in the docstring.
    - **R3-4 (blueprints).** The marker loop catches `(OSError, ValueError)`, and a non-object marker is
      recorded as unreadable.
    - **R3-5 (blueprints).** The baseline installs its traps before `mkdir` and the log, and `on_exit`
      writes the exit file only when the run directory exists.
    - Compat suite: 206 passed, 39 subtests.
11. **Independent implementation review 4 (2026-10-23 about 12:50): PASS, no HIGH or MEDIUM. Recorded before
    the LOW repairs.**
    - **R3-1 to R3-5 verified.** The reviewer ran reduced copies under four signal cases (INT during the
      preflight and during the pytest step, TERM to the group, TERM to the PID only). The script never
      resumes, the guard completes, and the exit is 130 or 143.
    - **LOW S1c-R4-1.** After a signal, the log still reads `maestro-harness exit=1`, the placeholder value.
    - **LOW S1c-R4-2 (pre-existing).** A TERM sent only to the script PID during the pytest step is
      deferred until pytest returns.
    - **LOW S1c-R4-3 (pre-existing).** A process-group signal also stops the observer before the guard. P8
      then fails (`stoppedBy` SIGINT), which is safe but means the guard path goes unmeasured. The same
      applies to the baseline.
    - **LOW S1c-R4-4.** No test covers `commitTickRaisedAttempts`.
    - **LOW S1c-R4-5.** A reused run directory keeps a stale `baseline-exit.txt`.
12. **LOW repairs for review 4 (finding 11).**
    - **R4-1 (blueprints `f450d97`).** `PYTEST=not-run` until the harness returns, so an interrupted run logs
      `maestro-harness exit=not-run script exit=130`.
    - **R4-3 (blueprints `f450d97`).** Both observers start through `/usr/bin/setsid`, inside the existing
      `exec` subshell. Because the subshell is not a group leader, `setsid` does not fork, so `$OBS`
      stays the observer's PID for `kill -TERM` and `wait`.
      - **Check (reduced copy):** after a process-group SIGINT, the observer is alive when the guard step
        runs, the cleanup's TERM stops it (exit 0), and the script exits 130.
    - **R4-5 (blueprints `f450d97`).** The baseline removes a stale `baseline-exit.txt` straight after
      `mkdir`.
    - **R4-4 (compat, this commit).** `test_s1c_r4_4_commit_tick_raised_attempts_are_recorded`: a flaky
      first commit tick gives `commitTickRaisedAttempts == [1]`. Suite: 207 passed, 39 subtests.
    - **R4-2 (carried, LOW, pre-existing).** A TERM sent only to the script PID during the pytest step is
      handled when the harness returns. The run never resumes after it. A process-group signal, as from
      Ctrl-C or `timeout` sent to the group, interrupts the harness at once. Forwarding signals to a
      background harness is left for a later successor.
13. **Independent review 5 of the finding-12 repairs (2026-10-23 about 13:05): PASS, no HIGH or MEDIUM.**
    - **Verified on reduced copies.**
      - `setsid` does not fork: the observer's PID is `$OBS` and its parent is the script. The script runs
        without job control, which is the default.
      - After a process-group INT or TERM, the observer is alive at the guard step, the cleanup stops it,
        and the script exits 130 or 143.
      - `PYTEST=not-run` is only echoed.
      - The new compat test would fail without the per-attempt record.
    - **LOW residuals, accepted and documented:**
      - (1) After a SIGKILL to the whole group, or a hangup, the observer is orphaned until its own time
        limit: 120 s for the Lite run, 60 s for the baseline. This fails closed, because a remaining CARLA
        client makes the next run's preflight BLOCK.
      - (2) A one-command window before `OBS=$!`, and one before the baseline's `rm` of a stale exit file.
      - R4-2 stays carried.
    - **Verdict.** S1c-1 is complete for review. The live behaviour (FR-021, FR-022 timestamps, the
      baseline T-5 paths) is verified in VS-09 and S1d after the author's acceptance (ES-1 approved).
14. **Author acceptance (2026-10-23 about 16:15 WEST).** The author wrote "i accept" in reply to the S1a
    and S1c-1 acceptance request. S1c-1 is accepted as presented in the thesis record
    `specs/029-lite-stabilization/review/acceptance-package-s1c1-20261023.md`.
    - **Accepted content.** The compat code is this candidate at `bac0e8d`; the commits after it change only
      this log. The blueprints code is `xverse-blueprints` `candidate/lite-stabilization-s1c-20261023` at
      `f450d97`.
    - **Pre-merge check (about 16:20, load about 3.2).** The compat suite on this candidate gave 207 passed and
      39 subtests (`/dev/shm/compat-p6-venv`, `PYTHONPATH=src`).
    - **Merge.** `--no-ff` into each main from bases `39d31fa` and `e7a6ebc`, which equal the mains, so each
      merged tree equals its candidate's tree. The tree identity is checked before the push.
    - **Carried, not repaired.** R4-2 and the review-5 LOW residuals (1) and (2). The live behaviour (FR-021,
      the FR-022 timestamps, the baseline T-5 paths) is verified in VS-09 and the S1d soak.
    - **Unchanged.** Execution remains non-M1 (DLG-7). Command echo is not evidence of braking, and
      `brakeStatus` and `wheelSpeedEscStatus` stay blocked. Lane activation, M1 admission, factory runs and
      scientific claims stay closed.
15. **VS-09 attempt 1 on the merged mains: the cancel was never issued (2026-10-23 16:25; recorded before any
    repair).**
    - **Run.** `runs/lite-stabilization-s1/vs09-20261023/lite-20261023T162536-cancel-paused` on loop10, from
      clean worktrees of platform main `b28a2aacf`, compat main `25e4e1f` and blueprints main `126a80b`
      (`VS09-RESULT.md`, `SHA256SUMS`).
    - **Observed.** The harness exits 0, because the test asserts only the nominal case. Maestro reports
      `ML-SCHEDULE-COLLECTION-INCOMPLETE`, not `ML-SCHEDULE-CANCELLED`, and `maestro-run.json` has no
      `cancelEpoch`. The cleanup is complete and the guard is clean (held to standstill, 3 actors destroyed, no
      residue).
    - **Cause.** The canceller fires at the driver's pause plus 6.0 s, and its 0.2 s poll can add more. The
      80-tick schedule's wall duration is not fixed: it ended 6.02 s after the pause, before the stop. The
      Phase 7 verification run won the same race by about 60 ms. S1a made each tick cheaper, so the race is now
      lost.
    - **Defects.**
      - (a) The cancel-paused case depends on the schedule outliving the cancel point. Nothing guarantees it.
      - (b) The harness does not fail when the cancel is not issued, or when the outcome is not a cancel. The
        miss was silent.
    - **Related risk (observation, not a defect here).** The nominal case needs the 9.5 s episode plus about
      2 s of start-up inside the 80 ticks. At the measured 0.165 s per tick its margin is about 1.7 s. FR-018
      (S1c-2) re-derives the horizons; this item does not change the nominal or freeze-vcu horizon.
    - **Repair plan (S1c-1a; blueprints only).**
      - Give the cancel-paused case its own horizon of 160 ticks. At the fastest measured cycle that is about
        26 s, more than 10 s past the cancel point. Under load the cycle is slower, which only adds margin.
        The cancel still ends the schedule at about 13 s, so the event count does not grow.
      - Record `cancelNotIssued` with the reason when the schedule ends first.
      - Make the harness fail for cancel-paused unless the cancel was issued and returned, and the outcome is
        `ML-SCHEDULE-CANCELLED`.
16. **After S1a, the blueprint's tick horizons are too short (2026-10-23 16:30–16:34; recorded before any
    repair). This supersedes the finding-15 repair plan.**
    - **Development run 1.** `dev-s1c1a-20261023T163017-cancel-paused` on blueprints candidate `8743f91`
      (finding-15 plan, 160 ticks) failed in the new assertion with `cancelNotIssued: run ended first`.
    - **Tick timing, from the Argus host clock of each tick's events.**
      - The cycle now runs at the 0.05 s `poll_seconds` floor. The mean is 0.057 s, with single cycles of
        0.1–0.3 s at about every 30th tick.
      - Tick 0 comes about 1.5–2 s after the run starts.
      - So 80 ticks end about 7.4 s after start (VS-09 attempt 1), and 160 ticks about 12.1 s after start.
      - Phase 7 measured 0.17–0.7 s per tick. Most of that was the growing persistence cost that S1a
        removed.
      - `poll_seconds` is capped at 0.05 s (`schedule_plan.py`, `POLL`), so a cycle cannot be lengthened.
    - **Nominal on the merged mains.** `lite-20261023T163334-nominal` (load 6.7) fails with
      `ML-SCHEDULE-COLLECTION-INCOMPLETE`. The schedule's last tick was at 9.15 s. The adapter was stopped
      before the driver's 9.5 s episode completed (`adapter closed stdout without done`, driver marker code 3).
      The Phase 7 scenario therefore no longer passes on the accepted mains. It is a defect of the blueprint's
      tick-count assumptions, made visible by S1a; the platform behaves as designed.
    - **Also affected.** freeze-vcu uses `at=16`, `duration=20` ticks to span the throttle phase. That is
      now about 1 s, starting before the throttle. No run of it has been made.
    - **Not affected.** no-carla ends at the adapter's child exit. The baseline does not use Maestro.
    - **Repair plan (S1c-2a, the FR-018 horizon part; unblocked by ES-2).** Each tick value is derived from
      the 0.05 s floor, and the upper bound is checked against the 55 s active window:
      - one horizon of 400 ticks for nominal, freeze-vcu and cancel-paused. That is ≥ 20 s after tick 0 at the
        floor, and about 23 s at the measured mean. It covers the driver episode end (about 11.5 s after tick
        0) and the cancel (about 12.3 s after tick 0) with ≥ 7 s margin. The run fits the active window while
        the mean cycle is ≤ 0.13 s.
      - observe at tick 200;
      - the freeze at tick 60 (about 3.4 s) for 80 ticks (about 4.6 s), inside the throttle phase;
      - `retained-inputs.json` declared at 4 MiB: about 2.2 KB per event, and about 560 events at 400 ticks;
      - the finding-15 assertions kept;
      - the per-tick timing recorded in `maestro-run.json`.
      - FR-018's long-run case (S-D1, 600 ticks) and its episode and stimulus extension stay in S1c-2.
17. **Development runs 2–4 on blueprints `1de5dc2` (2026-10-23 16:39–16:46, load 5.8–7.9, CARLA instance 10;
    recorded before any repair).** All runs use compat main `25e4e1f` and platform main `b28a2aacf`.
    - **nominal** (`dev-s1c2a-…-nominal`): succeeded with all markers. 401 ticks, mean cycle 0.061 s, last
      tick at 26.8 s.
    - **cancel-paused** (`dev-s1c2a-…-cancel-paused`): meets P3 as revised by DR-2.
      - `ML-SCHEDULE-CANCELLED`, with the cancel 6.0 s after the pause seen and the run ending 1.4 s later.
      - Writer open → failed (abort completed), reader `ARGUS2-MISSING-ARTIFACT` only (the uncollected
        markers), no CORRUPT, MUTATED or WRITER-STATE reason, persistence failure null.
      - `cleanupComplete` true. The 4 native units are issued, retired and reaped, so DR-3 needs no
        RunClosure STOP/RETIRE.
      - The guard held the ego to standstill and destroyed the 3 owned actors, with none remaining. No
        residue.
    - **freeze-vcu** (`dev-s1c2a-…-freeze-vcu`): failed with `ML-SCHEDULE-SERVICE-DEADLINE` at the thaw tick
      140.
      - The VCU's last health success was at 5.20 s and the freeze applied at 6.64 s. Health scans ran about
        every 1.6 s; the frozen VCU is not probed.
      - The thaw came at 10.85 s, after the VCU's 5 s freshness had lapsed (10.20 s). The tick-140 step was
        refused before dispatch.
      - Phase 7's 20-tick freeze stayed inside that window. The 80-tick (4.2 s) freeze of finding 16 does not.
    - **Defect.** The finding-16 freeze length ignores the constraint that a freeze plus the time since the
      unit's last health success must stay under its 5 s freshness. The scan interval is up to about 1.6 s, so
      a freeze must last ≤ about 3 s.
    - **Repair.** `FREEZE_TICKS = 40`: about 2.4 s at the measured mean, and about 3.2 s at a 0.08 s cycle.
      The freeze stays at tick 60.
    - **Observation for the platform (not repaired here).** A thaw after the frozen unit's freshness has
      lapsed ends the run as a service deadline, not as a health failure of that unit. This is recorded for
      the S1b and Phase 8 fault planning.
