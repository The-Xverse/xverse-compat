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
18. **Development run 5 (`dev-s1c2a-20261023T165012-freeze-vcu`, blueprints `093eada`, load 6.9): still
    `ML-SCHEDULE-SERVICE-DEADLINE` at the thaw tick 100. This corrects the finding-17 analysis (recorded before
    the repair).**
    - **Mechanism (platform code, as designed).**
      - The freeze suspends the unit's probing. `ProbeFacade.resume_health` restores it at the thaw, and
        `next_health_deadline` is the unit's last observation plus its 5 s cadence.
      - The dispatcher's `_end()` window closes `health_scan_seconds` earlier: 4 units × 0.38 s = 1.52 s
        (`schedule_plan.py`).
      - The fault-clear statement is therefore refused unless the thaw comes ≤ 3.48 s after the frozen unit's
        last health success.
    - **Measured** (thaw minus the VCU's last health success):

      | Run | Interval | Result |
      | --- | --- | --- |
      | Phase 7 `lite-20261023T075151` | 2.84 s | passed |
      | development run 2 | 5.65 s | failed |
      | development run 5 | 3.62 s | failed |

      Health scans run about every 1.6 s, so the last success can come up to about 1.6 s before the freeze.
    - **Repair.** `FREEZE_TICKS = 20`, as in Phase 7. That is about 1.2 s at the measured mean and about 1.6 s
      at a 0.08 s cycle, so the worst case is ≤ about 3.2 s. The freeze stays at tick 60, about 3.6 s after
      tick 0, which is where Phase 7's freeze fell (7.46 s after start).
    - **Observation for the S1b and Phase 8 fault planning (not repaired here).** The admissible freeze length
      is bounded by about `cadence − health_scan_seconds −` (the time since the last success). A longer freeze
      fails the run as a service deadline, not as a unit health failure.
19. **Independent review 6, of S1c-2a at blueprints `0d69bd7` (2026-10-23 about 17:15): PASS with 3 MEDIUM and
    6 LOW. Recorded before any repair.**
    - **Verified evidence on `0d69bd7`** (all dirty=0, `SHA256SUMS` verifies):
      - freeze-vcu `165447` and nominal `165835`: P1, writer closed and complete;
      - cancel-paused `170215`: P3 (with DR-2);
      - no-carla `170253`: P4.
    - **Verified root causes.** The review confirmed findings 16–18 against the code: the cycle floor, the
      thaw bound of cadence − `health_scan_seconds` = 3.48 s, and the 1.58 s scan spacing. The measured
      retained sizes are ≤ 0.96 MB against the 4 MiB declaration.
    - **MEDIUM-1.** freeze-vcu and no-carla still pass silently: only nominal and cancel-paused are asserted.
      Development runs `164220` and `165012` exited 0 with `ML-SCHEDULE-SERVICE-DEADLINE`. This is the class of
      finding 15(b), left unrepaired for those two cases.
    - **MEDIUM-2.** The freeze margin is thin.
      - The worst-case thaw interval is about 1.58 s + one cycle + 20 cycles, which must stay ≤ 3.48 s minus a
        round trip. It fails at a mean cycle above about 0.09 s, and there is no post-S1a cycle data above
        load 7.9.
      - At about 0.078 s per cycle, tick 60 falls after the throttle segment ends (about 8.7 s after start).
      - The host load is not in the run evidence.
      - The horizon's upper bound is about 0.12 s per cycle, not 0.13 s.
    - **MEDIUM-3.** The observe step at tick 200 falls inside the cancel window (about 14.0–14.4 s after start
      at the floor). The two S1c-2a cancel runs cancelled observe; Phase 7 completed it. The case's path is
      therefore not deterministic.
    - **LOW-1 (erratum to finding 15 and `VS09-RESULT.md`).**
      - The 13.22 s is `monotonicEndNs`, which includes the old canceller's 5 s join. The 80-tick schedule's
        last tick was at 7.44 s, 0.25 s after the pause (7.20 s), not 6.02 s after it.
      - In Phase 7 `075253` the cancel came at tick 59 of 80: that race was won by 2 s or more, not about
        60 ms.
    - **LOW-2 (errata to findings 16–18, the comments and the README).**
      - Tick 80 of the nominal run on the mains was at 8.58 s; 9.15 s is its last event.
      - Cycle spikes reach 0.57 s.
      - Tick 0 comes 1.49–2.69 s after start.
      - The freeze lands 4.4–4.7 s after tick 0 (the tick-0 start cycle is 1.3–1.7 s).
      - The README states the 3.48 s thaw bound as a fact rather than as a bound.
    - **LOW-3.** The cancel assertion compares against `monotonicEndNs`, which is taken after the join, not when
      `entry.start` returned. `cancelNotIssued` is set by the join timeout even when the cancel was issued.
      Thread writes made after `maestro-run.json` is written are lost from the file.
    - **LOW-4.** `tickTiming` includes the tick-0 start cycle in `maxCycleS` and `meanCycleS`.
    - **LOW-5.** This log does not record the verifying runs on `0d69bd7`, and no `xverse-argus verify` output
      is recorded for P1.
    - **LOW-6.** Findings 17 and 18 were committed only 27 ms and 115 ms before their repairs. The commit order
      is met, but the repairs were already written. From this finding on, the finding is committed before
      the repair is written.
    - **Repair plan (S1c-2a, blueprints only).**
      - MEDIUM-1: assert freeze-vcu as nominal, and no-carla as `ML-RUN-CHILD-EXIT` with cleanup complete.
      - MEDIUM-2: a freeze of 10 ticks at tick 40, giving a worst-case thaw interval ≤ 3.48 s up to a mean
        cycle of about 0.17 s, with the freeze start inside the throttle segment up to about 0.1 s per cycle.
        The 1/5/15-minute load at start and end is recorded in `maestro-run.json`, and the horizon comment
        is corrected.
      - MEDIUM-3: observe at tick 60, before the cancel up to about 0.15 s per cycle. cancel-paused asserts that
        every observe step completed.
      - LOW-3: record `startReturnedMonotonicNs` before `run_ended` is set. Assert the cancel against it. Set
        `cancelNotIssued` only when no cancel was requested.
      - LOW-4: report the start cycle separately from the steady-state mean and maximum.
      - LOW-1, LOW-2 and LOW-5: errata in this log, the comments and the README. The re-verification
        runs and `xverse-argus verify` output are recorded in the next finding.
20. **Re-verification on blueprints `f19ae58` (2026-10-23 17:17–17:22, CARLA instance 11; recorded before any
    repair).** Compat main `25e4e1f`, platform main `b28a2aacf`. The load average at run start and end is in
    each `maestro-run.json`.
    - **freeze-vcu `171706`** (load 4.9): P1. All markers present. `xverse-argus verify` reports both the
      Maestro and the flow root closed and complete, with 571 events. Observe completed. Steady mean cycle
      0.055 s.
    - **nominal `…-nominal`** (load 5.2): P1, with both roots closed and complete.
    - **cancel-paused `172145`** (load 7.3): **P3 not met, while the harness exited 0.**
      - The outcome is `ML-SCHEDULE-CANCELLED` and every observe step completed.
      - But `persistenceFailure` is `ML-PERSIST-CHILD` (kind `schedule`, stage `receive`, sequence 452). That
        request started 0.4 ms after `entry.stop` returned (13.713 s), and the worker child had exited 2.6 ms
        later.
      - `cleanupComplete` false, with `ML-CLOSURE-WORKLOAD-WAIT-UNKNOWN`. The 4 native units have no retired or
        reaped facts. The writer is `rpc-unresolved`. `dispatchTerminal` is null.
      - The Maestro Argus root keeps its initial open manifest (0 events) beside a 269-line stream. `verify`
        reports CORRUPT, MUTATED and WRITER-STATE.
      - The host is clean: no residue processes or sockets. The guard held the ego to standstill and destroyed
        the 3 owned actors.
      - Cancel run `170215`, on `0d69bd7`, had closed consistently: writer failed, 297 events, and `verify`
        gives only the WRITER-STATE reason, as DR-2 allows.
    - **Defects.**
      - (a) The cancel-paused assertions check the path, but not the P3 closure facts.
      - (b) A platform cancel race after S1a. It is recorded in the platform log (S1a successor, finding 18)
        and is not repaired here.
    - **Repair plan (blueprints).** cancel-paused also asserts:
      - `persistenceFailure` is null;
      - `cleanupComplete` is true;
      - every native unit is issued, retired and reaped;
      - every closure writer ends `failed` or `closed` (DR-2).

      The run still records everything before any assertion.
21. **Finding-20 repair and remaining verification (2026-10-23 17:26–17:40).**
    - **Repair: blueprints `fed431e`.** cancel-paused asserts the P3 closure facts:
      - `persistenceFailure` is null;
      - `cleanupComplete` is true;
      - all 4 native units are issued, retired and reaped;
      - every closure writer ends `failed` or `closed` (DR-2).

      Replayed offline over the 7 recorded S1c-2a cancel runs, this predicate rejects only `172145`.
    - **Rate.** Four more cancel-paused runs on `f19ae58` (load 6.3–7.6) all closed consistently. So far 1 of 7
      post-S1a cancel runs showed the platform race. It is recorded in the platform log as the S1a successor
      finding 18 (`candidate/lite-stabilization-s1a2-20261023`, record only).
    - **no-carla `…-no-carla` on `fed431e`** (load 6.3): P4.
      - `ML-RUN-CHILD-EXIT`, with cleanup complete and no residue.
      - The Maestro writer is `failed`.
      - The flow root stays `open` because the driver is killed. That is outside P4.
    - **Consequence.** With `fed431e`, a recurrence of the race makes cancel-paused fail visibly. VS-09 and
      the S1d P3 criterion therefore depend on the platform diagnosis.
22. **Independent review 7, of S1c-2a at blueprints `fed431e` (2026-10-23 about 18:00): PASS, no HIGH, with 2 MEDIUM
    and 6 LOW. Recorded before any repair.**
    - **MEDIUM-1.** The freeze's lower margin is not analysed.
      - In freeze-vcu `171706` the freeze applied at 4.893 s, and the throttle segment started at 4.81 s
        (`stimulus.jsonl`): an 83 ms margin.
      - Across the other CARLA runs, tick 40 minus the throttle start is +0.70 to +0.89 s. A fast start, like
        no-carla `173434` (first tick 1.54 s, start cycle 1.0 s), would put the freeze in the idle second.
      - The case would still pass, because freeze-vcu asserts only success and markers.
    - **MEDIUM-2.** The P3 Argus conditions are evaluated under an interpretation that is not recorded.
      - In every cancel run the flow root (`driver/argus-flows`) is open, with 0 events and CORRUPT and
        MUTATED reasons: the driver unit is SIGKILLed.
      - DR-2 forbids the WRITER-STATE reason, but a `failed` writer always produces it. Findings 20 and 21
        call it "as DR-2 allows".
      - Read literally, every passing cancel run fails P3. An explicit reading needs an author decision.
    - **LOW-1.** `cancellerAliveAfterJoin` is recorded but not asserted. A late `cancelReturnedMonotonicNs`
      can then exist only in memory.
    - **LOW-2.** The harness encodes only part of P3 and P4. It does not assert:
      - Maestro-root CORRUPT or MUTATED reasons;
      - the guard;
      - residue;
      - that the no-carla writer is `failed`.

      `README.md` overstates this as "as P3 requires". No cancel, nominal or freeze run was made at
      `fed431e`, and the finding-21 replay is not recorded as evidence.
    - **LOW-3.** The new runs fall outside the comment's ranges: the first tick came at 1.54–2.82 s and the
      start cycle took 0.995–2.14 s.
    - **LOW-4.** `SHA256SUMS` excludes `maestro-tmp/`, which holds the raw Maestro Argus roots, `m3.jsonl` and
      the markers.
    - **LOW-5.** Some claims are stronger than the evidence supports.
      - "Host clean" for `172145` covers only the 4 unit command lines, not the Maestro helpers or the
        persistence worker.
      - The 1-in-7 rate pools 3 revisions and 2 paths. On `f19ae58` alone it is 1 in 5.
      - Platform finding 18 cites `xverse-argus verify` output for runs `164544` and `170215`, which have
        only manifests.
      - "S1a acceptance evidence is unaffected" is not supported.
    - **LOW-6.** Timestamps.
      - Finding 20 (17:23:48) refers to platform finding 18, which was committed at 17:35:04.
      - Platform finding 18 is headed 17:22, but it holds analysis and runs from 17:26–17:33.
      - The erratum file says 17:20; its mtime is 17:15.
    - **Platform (review analysis, recorded as platform finding 19).** The code supports a native kill chain:
      a cancel that collides with a health QUERY on the authority connection is revoked (SIGKILL of the
      authority), and the bootstrap root then kills the persistence worker. Only `172145`'s cancel fell
      inside a health scan. This is a hypothesis, not proven.
    - **Repair plan (blueprints).**
      - MEDIUM-1: move the freeze to tick 60, about +1.1 to +1.9 s into the throttle at the floor. freeze-vcu
        records the overlap of the freeze with the throttle (from the Argus fault events and
        `stimulus.jsonl`) and fails unless it is positive.
      - MEDIUM-2: propose DR-6 to the author (see the thesis record). The harness checks the Maestro root
        with `xverse-argus verify` for every case:
        - nominal and freeze-vcu: closed and complete;
        - cancel-paused and no-carla: writer `failed` or `closed`, and no reason other than WRITER-STATE.
      - LOW-1: assert that `cancellerAliveAfterJoin` is absent.
      - LOW-2: narrow the README wording to what the harness asserts. The guard, residue and full P1–P8
        audit stay with S1-T15a. Verification runs of every case on the repaired head follow.
      - LOW-3: correct the comment ranges.
      - LOW-4: include `maestro-tmp/` in `SHA256SUMS`.
      - LOW-5 and LOW-6: these items are the errata. The scope of "host clean" is the 4 unit command lines.
        The rate is 1 of 5 on `f19ae58` and 1 of 7 pooled. Runs `164544` and `170215` are manifest-only.
        The S1a statement is withdrawn. The timestamps are as listed above.
23. **Verification of the finding-22 repairs on blueprints `588f84a` (2026-10-23 17:51–18:01, CARLA instance 12).**
    Compat main `25e4e1f`, platform main `b28a2aacf`. Every run has dirty=0, residue 0 (the 4 unit command
    lines and the run's sockets) and a successful guard.

    | Run | Load | Result |
    | --- | --- | --- |
    | freeze-vcu `175156` | 4.7 | succeeded with all markers; Maestro root closed and complete; freeze overlaps the stimulus throttle by 0.72 s |
    | nominal `175232` | 5.3 | succeeded; Maestro root closed and complete |
    | cancel-paused `175513` | 6.7 | `ML-SCHEDULE-CANCELLED` |
    | cancel-paused `175740` | 6.6 | `ML-SCHEDULE-CANCELLED` |
    | cancel-paused `180007` | 7.3 | `ML-SCHEDULE-CANCELLED` |
    | no-carla `180049` | — | `ML-RUN-CHILD-EXIT`, cleanup complete; Maestro writer failed, WRITER-STATE only |

    - **All three cancel runs passed every assertion:**
      - observe completed;
      - the cancel came during the run;
      - no persistence failure;
      - cleanup complete;
      - native units retired and reaped;
      - Maestro writer `failed` with WRITER-STATE only.

      The platform race did not recur. Its rate on `f19ae58` and `588f84a` together is 1 of 8.
    - **Offline replay.** The new checks were replayed over every earlier `dev-s1c2a-*` run
      (`REPLAY-S1c-finding22.md` in the evidence directory). They reject `164220`, `165012` and `172145` and
      accept the others.
    - **Checksums.** `SHA256SUMS` now covers `maestro-tmp/` too: 1400 files.
    - **Open, for the author.** DR-6, the P3 and P4 Argus reading, is proposed in the thesis record. The
      platform race is in platform findings 18–19.
24. **Independent review 8, of S1c-2a at blueprints `588f84a` (review returned before 18:09:26; this entry was written at 18:09:26
    2026-10-23): PASS, no HIGH, 1 MEDIUM and 4 LOW. Recorded before any repair.**
    - **Confirmed.** Each review-7 repair resolves its item, and the evidence supports finding 23.
      - The freeze start falls 1.08–1.98 s into the throttle across 19 runs. Tick 70 falls ≥ 0.65 s before
        the throttle ends.
      - The projected thaw interval is ≤ 2.50 s, against the 3.48 s limit.
      - `SHA256SUMS` verifies all 1400 files.
    - **MEDIUM-1.** `FREEZE_AT` = `OBSERVE_TICK` = 60.
      - In `175156`, `observe-legacy-vcu` ran right after the freeze applied. It returned the cached
        pre-freeze observation (`check_unit_health` returns the cached value for a suspended unit), so the
        record shows "probe succeeded" for a frozen unit.
      - Run outcomes are still protected by the post-thaw health scan. The evidence is misleading.
    - **LOW-1.** `overlapS > 0` accepts any overlap, not containment. `s1` is the last throttle sample, about
      50 ms short of the segment end.
    - **LOW-2.** DR-6's stated basis is inaccurate.
      - `172145` had an `open` Maestro root with CORRUPT, MUTATED and WRITER-STATE reasons.
      - The no-carla flow root is open with WRITER-STATE only.
      - DR-6 does not say whether a `closed` writer satisfies P4. P4 says `failed`, while the harness accepts
        either.
    - **LOW-3.** Header times are later than the files' own times: finding 22, the replay record and DR-6.
      From this finding on, the headers carry the shell time at which the entry was written.
    - **LOW-4.** The bound comment understates its inputs. Gaps between VCU health successes reach 1.70 s,
      not 1.58 s. Ticks 60–70 measured 0.72–1.00 s. The no-carla `180049` start (1.461 s, cycle 0.929 s) falls
      just outside the stated ranges. The bound still holds: worst case 2.70 s ≤ 3.48 s.
    - **Repair plan (blueprints).**
      - MEDIUM-1: `FREEZE_AT = 61`, so the observe at tick 60 really probes the VCU just before the freeze.
      - LOW-1: freeze-vcu asserts containment, apply ≥ the throttle start and clear ≤ the last throttle sample
        + 0.05 s, and records both margins.
      - LOW-4: correct the comment inputs.
      - LOW-2 (thesis): correct DR-6's basis. State that P4 requires `failed`, and make the no-carla assertion
        `failed` only.
      - Then one verifying freeze-vcu run, and one no-carla run.
25. **Verification of the finding-24 repairs on blueprints `8aa57ca` (runs 18:11–18:17, CARLA instance 13; written
    at 18:17:43 2026-10-23).** Compat main `25e4e1f`, platform main `b28a2aacf`. Every run has dirty=0, residue 0
    and the world restored.

    | Run | Load | Result |
    | --- | --- | --- |
    | freeze-vcu `181112` | 4.3 | succeeded; Maestro root closed and complete; freeze inside the throttle segment |
    | nominal `181350` | 8.0 | succeeded; Maestro root closed and complete |
    | cancel-paused `181632` | 6.7 | `ML-SCHEDULE-CANCELLED`, every assertion met |
    | no-carla `181700` | — | `ML-RUN-CHILD-EXIT`, cleanup complete, writer `failed` with WRITER-STATE only |

    - **freeze-vcu detail.**
      - The freeze lies inside the throttle segment, with a start margin of 1.271 s and an end margin of 1.73 s.
      - At tick 60, `observe-legacy-vcu` made a real health query (host 725.313) before its probe (725.338). The
        freeze applied at tick 61 (725.420) and cleared at tick 71 (725.919).
      - The thaw came 0.61 s after that health success.
    - **cancel-paused.** It met every assertion, with no persistence failure. The platform race rate is now 1 of
      9 on the last three heads.
    - **Checksums.** `SHA256SUMS` was refreshed: 1627 files.
    - **DR-6.** Its basis is corrected in the thesis record (review 8, LOW-2).
26. **Independent review 9, of the finding-24 repairs at blueprints `8aa57ca` (written at 18:21:09 2026-10-23): PASS,
    no HIGH or MEDIUM, 2 LOW. Recorded before the documentation repair.**
    - **Confirmed.**
      - The margins handle None correctly and accept a margin of exactly 0.
      - The +0.05 s end convention matches the stimulus samples.
      - The observe at tick 60 makes a real VCU health query (725.313) before the freeze at tick 61. The probe's
        `causationId` is that health event.
      - The thaw came 0.61 s after the VCU's last health success.
      - no-carla requires `failed`.
      - Finding 25's evidence holds, the rate of 1 in 9 holds, and the corrected DR-6 basis is accurate.
      - Finding 24 preceded the repair.
    - **LOW-A (erratum to findings 23 and 25).** The no-carla runs (`170253`, `173434`, `180049`, `181700`) have
      no restore guard. For them "guard successful" and "world restored" should read "n/a (no CARLA)".
    - **LOW-B.** The comment's measured ranges are exceeded again.
      - Nominal `181350` has `firstTickS` 2.830, above the stated 1.5–2.8 s.
      - Ticks 61–71 lasted 0.50 s in `181112`, outside the stated 0.72–1.00 s.
      - Repair (comment only, after the evidence): tick 0 came 1.5–2.9 s after start, and 10 ticks measured
        0.50–1.00 s.
27. **Author acceptance (written at 18:42:10 2026-10-23).** The author wrote "I accept all" in reply to the three
    decisions in the thesis record `specs/029-lite-stabilization/review/acceptance-package-s1c2a-20261023.md`:
    - S1c-2a is accepted as presented. The code is blueprints `8aa57ca`; `c5950f6` corrects comments only. The
      compat change is this log only.
    - DR-6 (the P3 and P4 Argus reading) is approved as proposed.
    - The platform cancel race is sequenced as S1a-2, before S1b.
    - **Merge.** `--no-ff` into each main, from bases `25e4e1f` and `126a80b`, which equal the mains. The tree
      identity is checked before the push.
    - **Next.** VS-09 is repeated on the merged revisions. It can still fail through the platform race (platform
      findings 18–19).
28. **S1c-2 planning (written at 19:37:43 2026-10-23, before any S1c-2 code).**
    - **Branches.** `candidate/lite-stabilization-s1c2-20261023` in `xverse-blueprints`, from main `6ac7703`, and
      in `xverse-compat`, from main `bb07492`. Part 1 covers what does not depend on S1b (ES-3). Part 2 adopts
      the S1b graceful stop, stderr capture and marker probe after S1b is merged.
    - **Part 1, S1-T15a: the soak tooling**, in `automotive/thesis-lite-carla-closed-loop/soak/`:
      - **`health_check.py`.** A read-only, independent CARLA check: a fresh client, `get_world()` within 15 s,
        then a passive `wait_for_tick(5 s)` on the asynchronous world. It never ticks. Its output is JSON.
      - **`audit.py`.** The per-run criteria P1 and P3–P8 from `plan.md` §Soak, with DR-2 and DR-6 applied, read
        from the recorded run evidence only. P2 is reported as dispersion.
      - **`run_soak.py`.** The predeclared runner (FR-019, FR-020):
        - interleaved rounds; a round starts only at a 1-minute load ≤ 5;
        - per-run load samples every 5 s;
        - a CARLA server block every 10 rounds, restarted with the author's recipe;
        - the health check before the preflight and after the cleanup;
        - the INVALID and observation rules;
        - stop at the first failure;
        - pinned, clean, detached revisions, refused on any change;
        - a soak manifest and a report.
    - **Part 1, the FR-018 horizon part not tied to S1b.**
      - A `long-run` case at the S-D1 horizon (600 ticks, 4 units), with the driver episode and the stimulus
        profile extended to cover it.
      - A 5 s start-up scope margin (S1b finding 2, GA-10).
      - `maestro-run.json` also records the broker's cancel result (confirmed or revoked) for every cancel run
        (S1a-2 finding 24).
    - **Order.** Each part is reviewed independently before any soak run. The soak itself (S1-T16) waits for
      the accepted mains of S1a-2, S1b and S1c-2.
29. **The platform content lock drifted after the S1a merge (written at 19:43:16 2026-10-23, before the re-pin).**
    - `platform-api.lock.json` pins platform `8b3d8c8e8` (surface `2696645d…`, 26 files). Its roots are
      `pyproject.toml`, `src/xverse_xdl`, `xdl/profiles` and `xdl/schemas`.
    - S1a changed `src/xverse_xdl/lifecycle.py` (`FileEvidenceJournal._reload`, the verified-prefix cache). So
      `test_provider_conformance.py::test_platform_dependency_source_matches_content_lock` fails against platform
      main `b28a2aacf`. That is true for compat main `bb07492` too, since the S1a merge.
    - The S1c-1 and S1c-2a suites passed because they ran before platform main moved.
    - Log a: `verification-20261023-s1c2-a.log` (1 failed, 208 passed) is the state before the re-pin. It also
      includes the new long-run stimulus test.
    - **Repair, as in Phase 6 (`c2557ed`).** Re-pin the lock to `b28a2aacf` and rebuild the admission record
      with `scripts/admit_phase4.py`, against a suite log taken after the re-pin. The review fields stay pending
      until S1c-2's own review and acceptance.
30. **Re-pin to platform main `b28a2aacf` (written at 19:44:51 2026-10-23).**
    - **Erratum to finding 29.** Log a shows 1 failed and 207 passed, not 208 passed.
    - **The test venv** `/dev/shm/compat-p6-venv` now has the `b28a2aacf` platform wheel
      (`.x-verse-build/cache/xverse-lite-live-20261022/wheels`). Its installed `xverse_xdl/lifecycle.py` equals the
      platform main source.
    - **The lock** `platform-api.lock.json` was re-pinned with `scripts/admit_phase4.py`: platform `b28a2aacf`,
      surface `4586c2ed…`, 26 files.
    - **The admission record** `xdl/selection/aeb-sim-admission.json` was rebuilt against log b
      (`verification-20261023-s1c2-b.log`: 208 passed, 39 subtests). Its review and acceptance fields are empty
      until S1c-2's review and acceptance.
    - **A rerun on the final record** gave 208 passed.
31. **S1c-2 part 1 development runs, and an audit metric defect (runs 20:27–20:33, CARLA instance 15; written at
    20:33:32 2026-10-23, before the repair).**
    - **Revisions.** Blueprints `5c7bfad`, compat `02474ba`, platform main `b28a2aacf`.

      | Case | Result | Ticks (mean cycle) | Persistence round trip (p99 / max / last-decile increase, s) | Load |
      | --- | --- | --- | --- | --- |
      | long-run | succeeded | 601 (0.056 s) | 0.046 / 0.105 / 0.005 (1401 calls) | 6.3 |
      | nominal | succeeded | 401 | 0.073 / 0.132 / 0.019 | 8.5 |
      | cancel-paused | `ML-SCHEDULE-CANCELLED` | — | — | 8.0 |

    - **Long-run.** Its start-up scope was 4.75 s. The persistence round trips meet the FR-002 metric.
    - **Broker cancel result.** `native_epoch_confirmed: true` in all three runs. In nominal and long-run this is the
      terminal fence's cancel.
    - **Audit.** nominal and cancel-paused PASS. long-run FAILs only `P6.closureWithin2s`.
    - **Defect.** `audit.py` measures "closure" as the start-return time minus the last tick: 2.05 s for long-run,
      2.59 s for nominal and 1.56 s for cancel. That span includes the reverse teardown of all four units, the
      collection and the terminal reports. The P6 criterion (plan.md; FR-002 "closure and abort must fit the
      terminal budget (≤ 2 s; `run_closure.py:126`)") means the terminal persistence calls. The longest of those
      was `terminal-report` at 0.80 s in long-run. The criterion was applied to the wrong span.
    - **Repair.**
      - The harness records every terminal persistence call (kind, duration).
      - P6 requires each `terminal-report`, `closure` and `abort` call to be ≤ 2 s.
      - The span after the last tick stays reported as an observation.
32. **The long-run terminal report exceeds its 2 s budget under load (run dev-s1c2p1-20261023T203658-long-run; written at 20:38:41
    2026-10-23, before any repair or decision).**
    - **Revisions.** Blueprints `b1c43b0`; load 8.4 at the start.
    - **Result.**
      - 601 ticks, and the units succeeded with every marker.
      - `persistenceFailure: ML-PERSIST-TIMEOUT`, kind `terminal-report`, stage `receive`: the call ran 1.981 s
        against its 2 s deadline.
      - `dispatchDiagnostic: ML-SCHEDULE-EVIDENCE-INCOMPLETE`, closure `ML-CLOSURE-REPORT-INCOMPLETE`.
      - The Maestro root stayed `open` with CORRUPT and MUTATED reasons. The harness failed visibly.
    - **The first long-run at load 6.3** took 0.80 s for the same call.
    - **Cause, from the code.** The terminal publish (`persistence_worker` → `terminal_runtime.WorkerTerminal.publish`)
      builds the lifecycle coverage report and the `retained-inputs.json` snapshot over every event. At long-run
      size that snapshot is about 2 MB, about 2.2 KB per event. So its cost grows with the run, unlike the
      incremental per-event path that S1a repaired.
    - **Measurements.** The S1a bench measured 0.71–0.99 s at 800 ticks, at low load. Live, at load 8.4, it is 1.98 s.
    - **Effect.** P6 ("closure ≤ 2 s at the S-D1 long-run size") and P1 for long-run fail at loads around 8 or
      above. The soak admits loads up to 10.
    - **FR-002 sets the rule.** "If closure or abort does not fit, abort must use the verified-prefix path, or an
      author decision is raised."
    - **Options.** Recorded for the thesis decision record, not chosen here:
      - (a) a platform repair that makes the terminal snapshot and coverage incremental, a verified-prefix path
        (platform successor work);
      - (b) a shorter S-D1 long-run horizon (an author decision);
      - (c) a larger terminal budget (a frozen 2 s bound; an author decision).
33. **S1c-2 part 1 verification on blueprints `b1c43b0` (runs 20:51–21:00, CARLA instance 15 stopped before
    no-carla; written at 20:44:19 2026-10-23).**
    - **Revisions.** Compat `c4b747f`, platform main `b28a2aacf`.
    - **freeze-vcu.** Audit PASS. The freeze lay inside the throttle; the persistence p99 was 0.048 s and the maximum
      0.235 s; load 8.3.
    - **no-carla** (server stopped). Audit PASS: `ML-RUN-CHILD-EXIT`, writer `failed` with WRITER-STATE only.
    - **Long-run.** It passed at load 6.3 (finding 31). At load 8.4 it failed through the terminal budget
      (finding 32), which goes to the author as S-D9. Long-run P6 is therefore open.
    - **Start-up scope.** It is 4.75 s in every run, and the broker cancel was confirmed in every run.
    - **Evidence.** `runs/lite-stabilization-s1/s1c2-part1-dev-20261023` (`SHA256SUMS`).
    - **Next.** An independent review of S1c-2 part 1 (findings 28–33).
34. **Independent review of S1c-2 part 1 (blueprints `b1c43b0`, compat `d7d5afa`; written at 20:55:05 2026-10-23):
    FAIL, 2 HIGH, 4 MEDIUM, several LOW. Recorded before any repair. The harness changes and the compat re-pin
    are correct.**
    - **H1. P8 guard path.**
      - `audit.py` windows the observer samples by the time each was received. The guard destroys the ego about
        18 µs after its standstill reading, so the last ego frame arrives just after the destroy time.
      - Example: `dev-s1c2a-…173336-cancel-paused` is a false reject. Frame 138252 shows 0.016 m/s and arrived
        3.3 µs after the destroy.
      - Repair: window by frame, up to the last frame that still shows the ego.
    - **H2. P6 is blind to a timeout.**
      - `noPersistTimeout` ignores `persistenceFailure.diagnostic` and `closureDiagnostics`.
      - A terminal call is cut off at its own deadline (≤ 2 s), so `closureCallsWithin2s` cannot fail. The
        finding-32 run passes P6 today.
      - Repair: check `persistenceFailure` and `closureDiagnostics`, and fail a terminal call that reached its
        deadline (at least 0.98 of 2 s, or any terminal persistence failure).
    - **M1.** Repeats do not count server failures, do not restart the server, and do not queue a repeat that
      passes at load above 10.
    - **M2.** The result of a restart after an INVALID run is ignored and not recorded.
    - **M3.** A health-check failure with the world left synchronous or paused is a P1 restore failure. It must
      count as FAIL, not INVALID.
    - **M4.** `scriptExit` is unused. The harness's own assertions are therefore not part of the verdict (for
      example the freeze-in-throttle check, and cleanup).
    - **LOW items.**
      - P8 path counts, the flow roots and P2 are missing from the report.
      - `--dispersion` includes failing runs. The long-run "throttle duration" is the first-to-last span.
      - The no-carla gap realization and the "server failed to start twice" stop exist only in code. That stop
        also lacks a `stop_server`.
      - The pins are weak: the platform is identified only by an `.export-revision` file, and `audit` is loaded
        from the runner's directory.
      - The health check's subprocess timeout is not caught.
      - A comment says "~1.8 MB".
    - **Errata.**
      - Finding 31: the runs were 20:21:46–20:33.
      - Finding 32: the snapshot is 1,295,710 bytes (about 1.6 KB per event over 797 events), not "about 2 MB, 2.2
        KB per event". The call's deadline was 1.980 s after it started.
      - Finding 33: the runs were 20:42:41–20:44:07. "Passed at load 6.3" is not supported by the audit: no
        long-run has an audit PASS under the final tooling.
      - The thesis S-D9 record: the bench measured 445 and 507 ms at 600 ticks.
35. **The finding-34 repairs (blueprints commit after `b1c43b0`; written at 20:57:17 2026-10-23).**
    - **H1.** The P8 guard window is taken by frame: from the first frame after the un-pause to the last frame that
      still shows the ego. Replay: `173336` now passes.
    - **H2.** P6 adds `noPersistenceFailure` and reads `persistenceFailure` and `closureDiagnostics`. A terminal
      call at 0.98 × 2 s or more fails. Replay: the finding-32 run `203658` now fails P6 on the timeout.
    - **M1 and M2.** `Soak._restart` and `_carla_run` handle every INVALID run, including those in repeats.
      - Each one counts as a server failure and restarts the server.
      - A failed restart counts again and is retried. More than 3 server failures stop the soak.
      - Every server event is recorded in the manifest.
      - A repeat at the end of a block that passes at a load above 10 is queued as an observation.
    - **M3.** A failed after-cleanup health check with `synchronousMode: true` is a restore failure: FAIL, not
      INVALID.
    - **M4.** A run passes only if the audit passes and the harness also exited 0.
    - **LOW items.**
      - The report gives the P8 path counts per case, the flow-root states (DR-6 c) and the server events.
      - `--dispersion` uses passing runs only, with the throttle time summed from the driver ticks.
      - The realizations are written in the runner's docstring and proposed as thesis DR-11 and DR-12.
      - `audit.py` runs from the pinned blueprints checkout. The runner must equal the pinned copy, and the
        driver-venv wheels are hashed into the pins.
      - `XVERSE_PLATFORM_SRC` is removed from the child environment.
      - The health check's timeout is caught.
      - The comment now reads 1.3 MB.
    - **New `soak/test_run_soak_logic.py`** (offline fakes, no CARLA): 5 passed. It covers the predeclared counts,
      a stop on the first failure, an INVALID repeat at the end of its block, a stop after more than 3 server
      failures, and a failed restart counted as a server failure.
    - **Replay of `audit.py`** over the 31 recorded runs: the only rejections are the known failures and the runs
      without `argus-verify.txt`.
    - **Errata of finding 34** apply to findings 31–33 as listed there.
36. **Independent re-review of the finding-34 repairs at blueprints `ca0ea5a` (written at 21:12:22 2026-10-23): FAIL, 2
    MEDIUM and several LOW. H1, H2, M3 and M4 are resolved. Recorded before any repair.**
    - **MEDIUM-1.** The DR-11 rule "a server that fails to start twice in a row stops the soak" is not implemented.
      `_restart` retries until there are more than 3 failures; the condition at `run_soak.py:279` is always true.
    - **MEDIUM-2.** The end-of-soak phase crashes (`FileNotFoundError` in `stop_server`) when every queued repeat
      is a no-carla run. No report is written, and the manifest stays `running`.
    - **LOW items.**
      - `audit.py:138`: a `TypeError` when there are no ego frames after the un-pause but an ego sample's frame
        is at or after the first post-un-pause frame.
      - The P8 guard window is no longer bounded by the destroy time.
      - The P6 threshold of 0.98 × 2 s tightens "within 2 s". A timed-out call is caught by
        `persistenceFailure` anyway.
      - The pins are only partly hashed: the platform source, the venv's `xverse` package and `health_check.py`
        are not.
      - A pin mismatch at start-up gives code 2, not a code-4 refusal.
      - An `_audit` timeout, and the `_check_pins` `SystemExit`, leave the server running.
      - The end-phase server start is not recorded as a server event.
      - P2 is absent from `soak-report.json`.
      - `--dispersion` ignores the harness exit.
      - `p8Paths` counts non-PASS runs without saying so.
      - Untested: the status classification (M3, M4), two failed starts in a row, a FAIL or INVALID in a repeat,
        the end-of-soak repeats with no-carla only, and the stop codes.
37. **The finding-36 repairs (blueprints `44fca14`; written at 21:15:21 2026-10-23).**
    - **MEDIUM-1.** `_restart(reason, failed_starts)` stops the soak after two failed starts in a row (DR-11), or after
      more than 3 server failures. A block start that fails enters with `failed_starts=1`.
    - **MEDIUM-2.** `stop_server` creates the slot directory. The end phase starts and records a server only when a
      CARLA repeat is queued.
    - **LOW items.**
      - `audit.py` has no `TypeError` when there are no ego frames.
      - The P8 guard window also requires the last ego frame to be received within 0.1 s of the destroy.
      - The P6 duration check is back to the plan's ≤ 2 s. Timeouts are caught through `persistenceFailure`.
      - The pins add tree digests of the platform source export and of the driver venv's `xverse` package. The
        runner, `health_check.py` and `audit.py` must equal the pinned blueprints copies, and the soak refuses
        with code 4 at start-up otherwise.
      - Any exit, including a pin change or a crash, stops a running server.
      - The `_audit` timeout is caught.
      - The report gives P2 (passing runs) and `p8PathsOfPassingRuns`. The standalone `--dispersion` is
        documented as audit-only.
    - **Classification.** The status logic is the pure `classify()` (DR-12).
    - **`test_run_soak_logic.py`: 15 passed.** New cases cover two failed starts in a row, a FAIL in an INVALID
      repeat, end-of-soak repeats with no-carla only (using the real `stop_server`), and seven `classify`
      cases.
    - **Audit replay over 31 recorded runs:** the verdicts are unchanged apart from the intended P6 change.
      `203658` still fails through the timeout.
38. **Independent re-review 2 of S1c-2 part 1 at blueprints `44fca14` (written at 21:19:54 2026-10-23): PASS, LOW only.
    Recorded before the repairs.**
    - **Resolved.** Both finding-36 MEDIUM items and the LOW items are resolved; 15 passed. The audit replay over 36
      runs matches finding 37. The P8 destroy margin is −0.17 to +0.38 ms against the 100 ms bound.
    - **LOW-1.** The stop reason is wrong after an INVALID run followed by two failed restarts: it reads "more than 3
      server failures" instead of DR-11's two failed starts.
    - **LOW-2.** The end phase stops the last block's slot again and overwrites its `stopped-at.txt`.
    - **LOW-3.** P2 in the report is unguarded when a passing guard-path run lacks `driver/driver-ticks.jsonl`.
    - **LOW-4.** `platformSourceTree` hashes `platform-src/src`, but the harness also imports `platform-src/tests`
      (`conftest.py`).
    - **LOW-5.** Untested: an INVALID run followed by two failed restarts, the code-4 refusals, the `finally`
      cleanup, and a restart in the end phase.
    - **Repairs follow** in the next blueprints commit.
39. **The finding-38 LOW repairs (blueprints `6651971`; written at 21:21:15 2026-10-23).**
    - LOW-1: `_restart` records the exact stop cause, either "server failed to start twice in a row (DR-11)" or
      "more than 3 server failures", and every stop uses it.
    - LOW-2: the end phase stops a server only if one is running (`_stop_running`).
    - LOW-3: P2 tolerates missing driver ticks, recording the throttle time as null.
    - LOW-4: the pins add `platformTestsTree`, a tree digest of `platform-src/tests`.
    - LOW-5: three new tests: an INVALID run followed by two failed restarts names DR-11; a runner that differs from
      the pinned copy is refused with code 4 before any run; a crash with a server up stops it.
      `test_run_soak_logic.py`: 18 passed.
    - **Status.** S1c-2 part 1 tooling is ready. Part 2 (adopting S1b, re-pinning the authority digest, scheduled
      `stop` steps per DR-7, asserting `stop_mode`) waits for the S1b acceptance. The soak waits for S-D9.
40. **S1c-2 part 2 plan (S1-T15: adopt S1b; written at 23:06:22 2026-10-23, before any part 2 code).**
    - **Stacking.** Part 2 is developed against the unaccepted platform stack S1a-2 → S1b → S1a-3 (head
      `d747f1e0c`), using a separate development driver venv. It is not accepted before ES-3.
    - **compat.**
      - A helper `xverse_compat/live/readiness.py`. If `.xverse-ready/challenge` exists in the unit's cwd, it writes
        exactly that nonce to `.xverse-ready/ready` atomically (a temporary file in the same directory, then
        `rename`). Without a challenge it does nothing.
      - Each owned unit calls it once it is ready: the driver when it has connected to the adapter; the adapter
        (py3.10) when CARLA and the owned scenario are set up; the stimulus when its zenoh session is open.
      - SIGTERM handling is kept as it is.
      - Tests for the helper.
    - **blueprints.**
      - Each owned unit gets its own cwd, `work/<unit>/`, inside the collection source root; the adapter gains
        `PYTHONPATH=src`.
      - Owned units declare the `nonce-marker` observe condition. The legacy VCU stays `running`.
      - Every unit declares `process.stop.graceSeconds` 0.6 (inside `ML-SCHEDULE-STOP-GRACE` at
        `per_unit_seconds` 2) and `process.stderr` (private, at most 256 KiB), with private directories
        `<run>/stderr-private/<unit>/` outside the work root. The legacy VCU's TERM behaviour is measured and
        recorded, not assumed.
      - The owned units' own `--stderr` files are dropped in favour of the platform capture.
      - The harness asserts `nativeUnits[].stop_mode == exited-on-term` for the owned units in nominal, freeze-vcu
        and long-run, records the VCU's `stop_mode`, and asserts the probe identity in the evidence.
      - `lib-live.sh` accepts `XVERSE_LIVE_DRIVER_VENV`; the default is unchanged.
    - **Re-pins after the merges.** The compat platform lock (S1b changed the v0.2 schema and `catalog.py`).
    - **Verification.** Development live runs on the stack. Then reviews, and the S1c-2 acceptance after ES-3.
41. **S1c-2 part 2 implemented (compat `b0f9796`, blueprints `c53dbc9`; written at 23:23:38 2026-10-23). Nothing was run
    live: no CARLA, no zenohd, no `run-live.sh`. The development live runs on the stack are the owner's.**
    - **compat.**
      - `xverse_compat/live/readiness.py`, `announce_ready(cwd=None)`. It opens `.xverse-ready` and `challenge` without
        following links. The challenge must be a regular file of exactly 64 lowercase hex bytes. The helper writes
        those bytes to `.xverse-ready/ready`: a temporary file in the same directory, `fsync`, `os.replace`, then an
        `fsync` of the directory. Without a challenge it returns False. A malformed or linked challenge or directory
        raises `ReadinessError`.
      - `xverse_compat_carla/readiness.py` is the same code for the 3.10 adapter, which must not import
        `xverse_compat` (`protocol.FORBIDDEN`; the driver fails a run whose adapter loaded it). A test checks that
        both files are identical after their docstrings.
      - Call sites:
        - the driver, once its listener, zenoh session and evidence run are up, before it accepts the adapter;
        - the adapter, once CARLA, the owned scenario and the link are set up; a readiness error closes the source
          (the owned actors are destroyed) and exits 3;
        - the stimulus, once its zenoh session, publishers and subscribers are open.
      - SIGTERM handling is unchanged.
    - **blueprints.**
      - `units.py`: each owned unit runs in `work/<unit>/`, inside the collection source root. The adapter has
        `PYTHONPATH` set to compat `src`. The owned units' `--stderr` arguments are dropped. The legacy VCU is unchanged.
      - `build_documents`:
        - every unit declares `process.stop {graceSeconds: 0.6}` and `process.stderr {capture: run-scoped-private,
          maximumBytes: 262144}`;
        - the owned units declare the observe condition `nonce-marker`, and the VCU keeps `running`.
      - Each `UnitAdmission` gets `stderr_directory` `<run>/stderr-private/<unit>/`: mode 0700, empty, distinct,
        outside the work root, with the path resolved.
      - `maestro-run.json` adds:
        - `declaredControls`;
        - `stopModes` from `nativeUnits`;
        - `stderrPrivateBytes`, with file names and sizes only;
        - `readinessProbes`, the unit-scope probe, ready and health identities from the Maestro Argus stream.
      - Assertions:
        - every native unit has the field `stop_mode`;
        - in nominal, freeze-vcu and long-run the owned units are `exited-on-term`; the VCU is recorded only;
        - in those three cases and in cancel-paused, the owned units' probe and ready events carry `nonce-marker` and
          the VCU's carry `running`, and health stays `running`.
      - `lib-live.sh`: `VENV=${XVERSE_LIVE_DRIVER_VENV:-<unchanged default>}`. `run-live.sh` exports it and records it
        in `identities.txt`. `run_soak.py` pops it, as it pops `XVERSE_PLATFORM_SRC`.
      - `audit.py`: P1 reports the stop modes as an observation.
    - **Deviations from finding 40 and additions.**
      - **D1. The driver's readiness point.** Finding 40 says "when it has connected to the adapter". Maestro starts
        the adapter only after the driver is ready (`start-carla-adapter` depends on `start-lite-driver`), so that
        point would deadlock until `ML-PROBE-NOT-READY`. The driver therefore announces when it is ready to accept
        the adapter.
      - **D2. Profile v0.2.** `process.stop` and `process.stderr` exist only in `runtime-compatibility-v0.2`, and the
        fixture documents are v0.1. The offline check caught this: `XDL-SEMANTIC-EXTENSION-SCHEMA`, "Additional
        properties are not allowed ('stderr', 'stop' were unexpected)". `build_documents` now moves the profile
        document (`metadata.version`, `schemaRef`) and every payload (`schemaVersion`) to v0.2, as the platform's
        own S1b `declare()` helper does. The only other v0.2 difference is the optional `planningBlockers`.
      - **D3. Owned readiness timeout 2 s.**
        - The readiness window is `W = min(policy timeout, observe timeout)`. With the harness's 1 s policy
          timeout, the last marker attempt comes 0.75 s after release.
        - In the part 1 runs (load 6.3–8.5), the adapter's owned-actor registry was written 0.24–1.26 s after its
          ready event. That is earlier than the point at which the adapter becomes ready.
        - The owned units' policy timeout is therefore 2 s, the declared observe budget, with attempts at 0, 0.875
          and 1.75 s. The VCU keeps 1 s.
      - **D4. Other additions.**
        - The probe identities are also asserted in cancel-paused.
        - The presence of `stop_mode` is asserted, so that a platform without S1b fails visibly.
        - `units.py` builds the owned units' `PYTHONPATH` from `XVERSE_LIVE_DRIVER_VENV`, so that the units and the
          harness use one venv.
    - **SIGTERM per unit.** These figures were measured offline at load 4.8, with a test-only zenoh stand-in and the
      fake adapter source, in 3 runs.
      - The driver, the stimulus and the adapter linger in 0.2 s sleeps and exit 0 on TERM: driver 0.214–0.215 s,
        stimulus 0.114–0.164 s, adapter 0.032–0.214 s.
      - The real zenoh `session.close()` is not measured offline.
      - The adapter installs its TERM handler only in the linger, after the protocol has ended and its source has
        been closed. That close destroys the owned actors and restores the settings. A TERM while it serves would
        end it by the default action (`SIG_DFL` per S1b `child_exec`), with no destroy; the restore guard then
        destroys the registered actors. In the scheduled cases the driver episode ends before the adapter's stop at
        tick `horizon − 1`, so the TERM reaches a lingering adapter.
      - The legacy VCU installs no TERM handler (code read), so TERM ends it by the default action. Its `stop_mode`
        is recorded, not assumed.
    - **Verified offline** with the S1a-3 stack venv (`lite-stabilization-s1a3/venv`, whose `xverse` and
      `xverse_xdl` sources equal `d747f1e0c`) and the platform tests from the S1a-3 worktree, for nominal, long-run
      and freeze-vcu:
      - schema validation and plan compilation;
      - `prepare_lifecycle`: each unit's `process_controls` is (0.6, 262144), and the observe conditions are
        `nonce-marker` ×3 and `running`;
      - `admit_schedule` passes with grace 0.6 and `per_unit_seconds` 2, and gives `ML-SCHEDULE-STOP-GRACE` at
        1.8 s;
      - the coverage rows: `readinessProbe` is `nonce-marker` for the owned units only;
      - the broker's `_controls` for each unit on the harness's real directories gives (600, 262144, probe 1 or 0,
        stderr fd), and `_admit_distinct` passes, which covers the shared, cwd, probe-cwd and budget checks.
    - **Tests.**
      - The compat suite: 244 passed, 39 subtests. The 36 new tests are in `tests/live/test_readiness.py`.
      - `soak/test_run_soak_logic.py`: 19 passed, one of them new (the child environment drops both overrides).
      - An `audit.py` replay over 37 recorded runs gives verdicts identical to `HEAD~1`.
    - **Open issues.**
      - **O1. no-carla (P4).**
        - Without CARLA, the adapter waits 5 s for the simulator (`set_timeout(5.0)`; it exited about 5.1 s after its
          ready event in `dev-s1c2p1-20261023T204355-no-carla`). With the marker probe it can no longer be ready
          within its 2 s window.
        - The run is therefore expected to fail at the adapter's start with `ML-PROBE-NOT-READY`, not through
          `ML-RUN-CHILD-EXIT`. The exact diagnostic is not known offline.
        - The harness assertion and audit P4 keep `ML-RUN-CHILD-EXIT`, the thesis plan text. The first no-carla
          development run decides, and P4 then needs an author decision.
      - **O2. The readiness window under load.** A unit's start deadline is also clipped by the next health scan
        (`dispatcher._end`). The 2 s window is a measured choice, not a proof.
      - **O3.** The re-pins (the compat platform lock and the authority digest) wait for the merges, as finding 40 says.
42. **S1c-2 part 2 development runs on the platform stack `d747f1e0c` (runs 23:25–23:33, CARLA instance 16, dev driver
    venv `.x-verse-build/cache/xverse-lite-live-s1stack`; written at 23:33:52 2026-10-23, before any repair).**
    - **Revisions.** Blueprints `c53dbc9`, compat `b8403a3`. Evidence: `runs/lite-stabilization-s1/s1c2-part2-dev-20261023`
      (`SHA256SUMS`).

      | Run | Audit | Result | Load |
      | --- | --- | --- | --- |
      | nominal `232543` | see below | succeeded | 4.5 |
      | freeze-vcu | PASS | succeeded | 6.1 |
      | cancel-paused | PASS | `ML-SCHEDULE-CANCELLED` | 5.8 |
      | long-run (two runs) | PASS | succeeded | 5.8–6.1 |
      | no-carla `233239` | FAIL | `ML-PROBE-NOT-READY` | 6.0 |

    - **Graceful stop.** All four units, including the legacy VCU, stopped `exited-on-term` in nominal, freeze-vcu and
      both long runs. Every unit was `forced` in cancel-paused, as designed: CANCEL freezes first (DR-7).
    - **Readiness.** The owned units became ready through `nonce-marker`. The adapter needed its 2nd or 3rd and last
      attempt, so the margin is thin (finding 41, O2).
    - **stderr.** The VCU's stderr was captured privately (37,892 bytes).
    - **Long-run terminal report on S1a-3:** publish 0.415 s and close 0.81 s. Before S1a-3 it was 0.80 s, and 1.98 s
      with a timeout (S-D9).
    - **nominal `232543`.** The audit flagged P1 residue: five sockets in `/run/user/1000/xverse-lite/`
      (`test-ready-*`, `measure-*`) created at 23:15–23:16, before the run.
      - The `test-ready-*` socket comes from `tests/live/test_readiness.py:193`, which does not remove its socket.
        That is a defect. The `measure-*` sockets came from the implementing agent's ad-hoc timing script.
      - The five named files were removed. All later runs had no residue.
    - **no-carla `233239`: a new failure mode.** This is the open issue O1, but the outcome is worse than expected.
      - The adapter never became ready, after 3 failed marker attempts (no simulator), giving
        `ML-PROBE-NOT-READY`.
      - The closure is `ML-CLOSURE-WORKLOAD-WAIT-UNKNOWN`, `cleanupComplete` false and `persistenceFailure`
        `ML-PERSIST-CHILD`.
      - The broker cancel result is `issuer_dead: true` with no native confirmation: a revoke.
      - The Maestro root stays `open`, with CORRUPT and MUTATED reasons.
      - The units were stopped and there was no unit residue. The host is clean (no processes, no sockets).
      - Before S1b (findings 21, 23, 35) no-carla ended in `ML-RUN-CHILD-EXIT` with a clean closure.
      - **The cause is not established.** The failure path calls `owner.cancel("dispatcher-failed")` with no caller
        deadline, so an expired deadline does not explain the revoke. It is handed to a platform diagnosis, recorded
        in the platform log on `candidate/lite-stabilization-s1a3-20261023`.
    - **Consequences.**
      - P4 (no-carla) cannot pass on the stack until the platform diagnosis is done.
      - P4's expected diagnostic changes from `ML-RUN-CHILD-EXIT` to `ML-PROBE-NOT-READY` once owned units declare
        readiness. That is an author decision, to be raised with the diagnosis.
      - The readiness test leaks sockets; it is repaired after this record.
43. **no-carla on the repaired platform stack `b049585bf` (platform S1b findings 15–16, ADR S1a-5), with dev driver venv
    `xverse-lite-live-s1stack-b`; two runs, load 4.1–4.2. Written at 23:50:34 2026-10-23, before any change to the P4 check.**
    - **The repair holds live, in both runs:**
      - `ML-PROBE-NOT-READY`;
      - the broker cancel confirmed natively (`native_epoch_confirmed: true`, `issuer_dead: false`);
      - no persistence failure;
      - `cleanupComplete` true;
      - the Maestro writer `failed`, with WRITER-STATE only;
      - no residue.
    - **The only remaining check failure** is `P4.childExit`: the harness and `audit.py` expect `ML-RUN-CHILD-EXIT`.
      Now that the owned adapter declares `nonce-marker`, a missing simulator is detected as a readiness failure
      within its 2 s window, before the adapter's own 5 s connection timeout ends it. `ML-PROBE-NOT-READY` is
      therefore the correct and earlier diagnostic.
    - **Proposed (thesis DR-14, flagged for the author).** P4 accepts `ML-PROBE-NOT-READY` or `ML-RUN-CHILD-EXIT` as
      the start-failure diagnostic. Everything else in P4 is unchanged: cleanup complete, the writer `failed` with
      WRITER-STATE only, and no residue. The harness assertion and `audit.py` follow.
44. **Independent review of S1c-2 part 2 (compat `b6ffa93`..`1354d4c`, blueprints `c53dbc9` and `eb64781`; written at
    23:58:59 2026-10-23): PASS, 3 MEDIUM and 5 LOW. Recorded before the repairs.**
    - **M1.** `run-live.sh` hashes the pinned wheels even when `XVERSE_LIVE_DRIVER_VENV` names a dev venv. The
      finding 42 and 43 `identities.txt` therefore name the right venv path but the wrong wheel hashes: `6ff39689`
      was recorded, while `d0fed3d1` (s1stack) and `2efbd893` (s1stack-b) ran. The soak is unaffected.
    - **M2.** The evidence seal of `s1c2-part2-dev-20261023` is broken. `runs.txt` was appended (runs `234951` and
      `234959`) after `SHA256SUMS` was written, and finding 43 names no evidence manifest.
    - **M3 (O2).** The 2 s owned readiness window is thin, and the variance is not explained by load. The adapter
      needed its last attempt only in the lowest-load run.
    - **LOW items, accepted with notes.**
      - **L1.** `exited-on-term` also counts a default-action death after TERM, so a clean handler exit is shown only
        offline. Accepted: the markers catch a protocol-time death.
      - **L2.** The driver ignores TERM during `accept` (up to 12 s). No scheduled path reaches this, since failure
        stops are forced (DR-7). Accepted.
      - **L3.** The adapter has no TERM handler before its protocol ends. The guard cleans up, and FR-021 holds.
        Accepted.
      - **L4.** Nothing is asserted on the private stderr records. Repaired.
      - **L5.** The DR-13 and DR-14 headings carry impossible times. Corrected.
    - **Repair plan.**
      - M1: hash the wheels next to the venv in use.
      - M2: `runs.txt` grew only by appending, so its sealed prefix is checked. A second manifest,
        `SHA256SUMS-finding43`, covers the two later runs and the current `runs.txt`, and is referenced here.
      - M3: owned readiness window 3.5 s (attempts at 0, 1.625 and 3.25 s), within the 5 s cap. Record each owned
        unit's ready latency (ready-file mtime minus challenge mtime) in `maestro-run.json`. Re-measure before the
        soak.
      - L4: assert that each started unit has `stderr-g1` of at most its declared maximum.
45. **Part 2 re-verification on blueprints `66e745b`, platform stack `b049585bf` (dev venv s1stack-b; runs 00:41–00:52,
    CARLA instance 17; written at 00:53:35 2026-10-24, before any repair).**
    - **Evidence.** `runs/lite-stabilization-s1/s1c2-part2-dev2-20261024` (`SHA256SUMS`). The identities now record
      the dev venv's wheel, `2efbd893` (M1 repaired).

      | Run | Result | Load |
      | --- | --- | --- |
      | nominal | PASS; ready latency 0.29–1.31 s (adapter 1.311 s); all units `exited-on-term` | 6.5 |
      | long-run | PASS; latency 0.35–0.42 s | 7.9 |
      | freeze-vcu | **FAIL** | 8.4 |
      | cancel-paused | **FAIL** | 8.7 |

    - **freeze-vcu: lite-driver readiness failed at start-up.**
      - Probe attempts came at 3.41 s and 5.04 s. The third attempt (planned at about 6.66 s) was dropped because the
        outer start deadline cut the window. No ready file was written, giving `ML-PROBE-NOT-READY`.
      - Then `persistenceFailure: ML-PERSIST-CHILD` (validation, at 5.92 s), with the broker cancel revoked
        (`issuer_dead`) and the closure `ML-CLOSURE-WORKLOAD-WAIT-UNKNOWN`.
      - The 3.5 s window of finding 44 appears to push the start step past the authority's lease. That is the
        expired-lease residual declared in S1a-5 (platform S1b finding 18, LOW-2), which is now reachable.
      - The driver's readiness at load 8.4 took more than 1.6 s, against 0.3–0.5 s at load 6.
    - **cancel-paused: closure lost at the cancel.**
      - `persistenceFailure: ML-PERSIST-CLOSED`, kind `schedule`, stage `validation` (before any send), at the exact
        cancel time (15.484 s).
      - The broker cancel was confirmed natively, but no terminal events follow tick 116.
      - `cleanupComplete` false, native facts unattested, closure `ML-CLOSURE-WORKLOAD-WAIT-UNKNOWN`.
      - Earlier cancel runs (load 5.8–7.3) closed cleanly. A plain `PersistenceError` refusal at validation means
        the client was already `_failed`, so a before-send cancel race (S1a-1 territory) may still fail storage under
        load.
    - **Host clean.** No residue, no vehicles, the world restored.
    - **Both failures go to a platform diagnosis before any repair:** (A) readiness against the start deadline and
      the lease under load; (B) the persistence state at a cancel.
46. **Harness repairs from the platform diagnosis (platform S1b-stack finding 22; thesis DR-15; written at 01:10:16
    2026-10-24, before any change).**
    - **Diagnosis taken over.** (B), the cancel-paused failure, is a platform race in `PersistenceClient._live`;
      it is repaired by RB1 on the platform branch, and the harness needs no change. (A), the freeze-vcu failure,
      came in part from the harness: the 3.5 s owned window of finding 44, M3, plus a start-up scope at lease − 0.05 s,
      lets the start step run to the bootstrap lease, so the cancel then has no native close time left. RA1 now
      caps a declared window at run time and rejects at admission a window that cannot fit a fresh lease.
    - **H1.** The owned readiness window goes back to the largest value that the RA1 admission bound accepts. The
      value is set from the bound that the platform records, not guessed. A slow adapter is still covered by the
      three attempts, and readyLatencyS keeps measuring it.
    - **H3.** `maestro-run.json` records the lease facts: the bootstrap lease relative to the run start, and the
      start-up scope end. It also records the reap facts of the bootstrap drain (supervisor reaped, returncode,
      diagnostic, unacknowledged births) and of the storage drain (worker returncode, diagnostic). Each fact is
      read through `_fact`, so a missing fact never loses the record.
    - **H2** (run directory on tmpfs) is deferred to the S1d soak environment decision; it is not applied here.
    - **Re-run plan.** Rebuild the dev venv from the repaired platform head, then run part 2 live: nominal,
      long-run, freeze-vcu, cancel-paused and no-carla, recording the load. Independent review follows.
    - **Revision (02:03:50).** Platform finding 25 (DR-16) adds RA2 (renewal before a marker start step) and
      RA5. RA5 is a reserve that also covers the failure-statement RPC. The final live admission bound is W ≤ 2.75 − 2 × 0.38 = 1.99 s. H1 is therefore
      1.95 s (attempts at 0, 0.85 and 1.70 s), above the slowest measured adapter latency of 1.31 s. A cut window ends
      as `ML-PROBE-WINDOW-CUT`, and the harness records `readinessWindows` (W, W′, L, t0) from the dispatch result.
      Blueprints commits `4aa6d55` (H1 at 2.25 s, H3) and its successor (H1 at 1.95 s, readinessWindows).
    - **Revision 2 (02:16:40).** Platform finding 26 (LOW-4) and thesis DR-17: H1 is 1.7 s (attempts at 0,
      0.725 and 1.45 s), with 0.29 s headroom below the 1.99 s bound for the RA2 renewal and pre-release work. No harness
      file imports the removed `CANCEL_CLOSE_RESERVE_SECONDS` (checked by grep over both S1c-2 worktrees).
47. **Part 2 re-verification on the repaired platform stack (platform `a16fd1b78`, wheel `a54844d3`; blueprints
    `24dae38`, H1 = 1.7 s; dev venv `xverse-lite-live-s1stack-e`; CARLA instances 18 and 19; runs 03:56–04:5x;
    written at 04:08:12 2026-10-24, before any change).**
    - **Evidence.** `runs/lite-stabilization-s1/s1c2-part2-dev3-20261024`.
    - **Repaired failures.** freeze-vcu and cancel-paused PASS (load 5.4 and 5.9). The cancel was confirmed
      natively, cleanup was complete, and there was no persistence failure. The bootstrap and storage reap facts
      are clean (returncode 0), and the readiness windows were uncut (W′ = W = 1.7 s).
    - **Other cases.** long-run PASS (601 ticks, load 5.7). Warm nominal PASS twice (adapter 0.293 and 0.329 s).
      no-carla fails closed as designed (`ML-PROBE-NOT-READY`, cleanup complete, audit PASS under DR-14).
    - **New observation: readiness after a cold CARLA start.**
      - The first nominal run after CARLA instance 18 started failed `ML-PROBE-NOT-READY`: the carla-adapter
        failed all three attempts (last at 1.45 s). The failure was fail-closed and clean (`cleanupComplete`
        true, reap codes 0, window not cut).
      - The first nominal run after instance 19 passed, with the adapter ready at 1.36 s on its third attempt.
        Finding 45's first run had 1.311 s.
      - Warm adapter latency is 0.29–0.36 s. The cold-start effect is CARLA's first owned-scenario setup after a
        server start, not the stack.
    - **Disposition (thesis DR-18).** H1 = 1.95 s, inside the 1.99 s bound. The S1d soak declares one warm-up run
      per CARLA start, recorded and excluded from the statistics. Re-verification from a fresh cold start follows.
48. **Cold-start confirmation on the final harness and the freeze placement (blueprints `c60fe14`, H1 = 1.95 s;
    platform `a16fd1b78`, now merged as platform main `ee91697a4`; CARLA instance 20; runs 04:12–04:31; written
    at 04:33:08 2026-10-24, before any change).**
    - **Evidence.** `runs/lite-stabilization-s1/s1c2-part2-dev4-20261024`.
    - **Results.**
      - Cold nominal PASS: the adapter was ready at 1.74 s, on its third attempt (1.70 s). This is the slowest
        cold value yet, and it confirms the DR-18 warm-up.
      - cancel-paused PASS (load 8.9) and long-run PASS. Warm nominal PASS, with the adapter at 0.349 s.
      - no-carla fails closed as designed.
      - Every run shows cleanup complete, no persistence failure, an uncut window (W′ = 1.95 s) and clean reap facts.
    - **freeze-vcu: the harness exited 1 at load 9.2,** although Maestro succeeded and the audit passed. The finding
      24 LOW-1 assertion failed: the freeze ended 0.185 s after the stimulus throttle segment (`endMarginS`
      −0.185).
      - The freeze is tick-placed (tick 61, after the observe at 60). The throttle segment (3.5 s) is host-timed
        from the stimulus start.
      - Across the ten 3.5 s-window runs since the S1b adoption, tick 61 lies 2.79–3.84 s into the segment. The
        end margins were 0.064, 0.133 and −0.185 s.
      - This is a harness margin defect of finding 24's placement, made visible by load. It is not the stack.
    - **Proposed repair (computed from the recorded Argus tick clocks and stimulus samples).**
      - Freeze at tick 25 and observe at tick 24 (one tick before, as finding 24 MEDIUM-1 requires).
      - Ticks 1 and later begin about 4.4 s after tick 0, after start-up, so every unit is running. The observe
        step's own cost (0.17–0.39 s) is added before the freeze.
      - Over the ten runs, the worst-case margins become 0.94 s at the start and 0.96 s at the end, instead of
        −0.84 s.
      - The VCU health-thaw bound (finding 18) does not depend on the placement.
      - Cancel-paused's observe now comes earlier, about 5.6 s after start, which only widens its margin before
        the cancel (finding 19).
    - **Re-pin to platform main `ee91697a4` (04:35:36).** The platform stack S1a-2, S1b and S1a-3 was
      accepted by the author and merged, and platform main `ee91697a4` was pushed (its tree equals the decisive
      run's `a16fd1b78`).
      - The test venv `/dev/shm/compat-p6-venv` now has the wheel `a54844d3…`, and its installed
        `xverse_xdl/lifecycle.py` equals the platform main source.
      - Log c (`verification-20261024-s1c2-c.log`): 1 failed, the content lock, as expected before the re-pin,
        and 243 passed.
      - `scripts/admit_phase4.py` re-pinned `platform-api.lock.json` to `ee91697a4` (surface `ce779e57…`,
        26 files). Log d: 244 passed. The admission record was rebuilt against log d, and a rerun gave 244 passed.
      - The soak's pinned environment `xverse-lite-live-20261022` was rebuilt from `ee91697a4` (wheel
        `a54844d3…`). The `b28a2aacf` copies are kept as `*-b28a2aacf`; nothing was deleted.
49. **Freeze placement confirmed; a unit stalled in an fsync on loop10 (blueprints `5f3e3ba`, the pinned environment
    rebuilt from platform main `ee91697a4`, no overrides; CARLA instance 21; runs 04:33–05:0x; written at
    04:51:11 2026-10-24, before any change).**
    - **Evidence.** `runs/lite-stabilization-s1/s1c2-part2-dev5-20261024`.
    - **Results.**
      - freeze-vcu PASS three times. The freeze lies inside the throttle segment, with start margins of 0.95–1.22 s
        and end margins of 1.78–2.05 s (finding 48's prediction: at least 0.94 and 0.96 s).
      - Cold nominal PASS, with the adapter ready at 1.681 s on its third attempt. Warm nominal PASS, and long-run
        PASS.
    - **cancel-paused FAIL at start-up: `ML-PROBE-NOT-READY` for lite-driver,** the first unit, over an uncut
      1.95 s window. The failure was fail-closed and clean: `cleanupComplete` true and reap codes 0.
      - The broker cancel reported `ML-RUN-FREEZE-UNRESOLVED` (14 of 15 frozen). The driver was forced to stop.
      - **Cause.** The driver's challenge was created at 04:42:53.699 and its Argus run at
        `<run>/driver/argus-flows` at 04:42:54.119. There it left `manifest.json.tmp-1` and never renamed it.
        The driver was stalled in the manifest write and `fsync` on the loop10 disk (97% full, a loop-mounted
        image), before `announce_ready`.
      - A task in an uninterruptible fsync cannot be frozen, so the platform correctly reported the freeze as
        unresolved and then forced the cleanup.
      - This is the H2 stall named in platform finding 22. Maestro's own tree is already on tmpfs
        (`--basetemp`), but the units' run directory (`XVERSE_LIVE_RUN_DIR`) is on loop10. The rate is 1 in 7
        runs here, and a 140-run soak would stop on it.
    - **Proposed repair (H2).** `run-live.sh` stages the units' run directory on tmpfs
      (`/dev/shm/xverse-lite-run-<run>`). `cleanup()` copies it into the loop10 evidence directory (`cp -a`, the
      stage removed only after a successful copy). The copy comes after the residue listing and before the restore
      guard, which reads the copied owned-actor registry. The evidence still ends on loop10.
