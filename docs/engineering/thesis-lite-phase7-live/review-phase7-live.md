# Review log: Thesis Lite Phase 7 live integration (carla-items/2 successor and live units)

Candidate `candidate/phase7-live-integration-20261022` from `xverse-compat` main `6271ac2`.

Authority: the author's message of 2026-10-22 (about 23:40 WEST), which authorizes bounded local integration and
live testing, but no acceptance, merge or push, and no change to legacy source. The author's 8-hour delegation
followed at about 23:55. Both are recorded in thesis
`specs/001-thesis-lite-compatibility-smoke/review/author-authorization-20261022-live-integration.md` (DLG-7 to
DLG-10).

The work is an engineering integration only: not AEB validation, not a scientific result, and not M1 evidence.

1. **Opening (2026-10-22).** The successor scope comes from the Maestro survey. Maestro units have
   `/dev/null` standard streams and are stopped by SIGKILL. Only a sealed ELF executable can be launched, so a
   symlinked venv interpreter cannot be used. Changes:
   - `carla-items/2` over a Unix socket (DLG-8), with a required `throttle` command member. Protocol 1 over
     stdio is unchanged.
   - An owned live scenario: the adapter spawns, owns and destroys `xverse-lite-*` actors (DLG-9).
   - A restore guard, run after every live run (DLG-10).
   - A passive evaluation observer.
   - Owned live units in `xverse_compat.live`: the loop, the VCU gateway (`driver`), the declared `stimulus`,
     and the non-Maestro `adapter_check`.
   - Unit options: `--carla-site`, `--linger`, `--marker`, `--stderr`.
2. **Live finding 01, before repair.** The CARLA client caches map data under `$HOME/carlaCache`, so
   `HOME=/nonexistent-carla-home` breaks `get_map()` live. Repair: live units get a run-scoped writable HOME.
3. **Live finding 02, before repair.** A synchronous world applies new settings only on the next tick, so the
   guard's first restore silently left the world synchronous. Repair: one bounded commit tick in the guard and
   in `LiveSource.close()`, followed by a re-read. The freshly started server also reported `synchronous_mode`
   True with frame 0 until a tick; the origin of that setting was not determined.
4. **Adapter live check, not Lite integration (2026-10-23 about 00:05).** Run `adapter-check-1` against
   CARLA 0.9.15 (Town10HD_Opt), with the adapter as the only tick owner and actuator writer:
   - 245 ticks, 469 flow items delivered;
   - peak speed 42.8 km/h at throttle 0.6, full brake to 0 in about 1.2 s, minimum forward acceleration
     −25.3 m/s²;
   - the passive observer agrees: peak 42.8 km/h, 48.5 m, final 0;
   - all 245 acks `echoed`; the echo is cached control and is not used as braking evidence;
   - exit 0, settings restored.
5. **Closed-loop dry run outside Maestro.** Run `dryrun-2`: the stimulus drives the legacy VCU, which drives the
   driver, the adapter and CARLA, and the runtime motion feeds back as `velocity_status` and `clock_status`. Peak
   43.0 km/h, then a stop. The author's `zenohd` had gone; it was restarted as the author ran it.
6. **Live finding 03, a platform scaling limit, not repaired here.** Maestro's persistence and Argus append
   interval grows with stream length: 0.066 s, then 0.20 s, then 0.52 s by about 290 events. It exceeds the
   0.38 s operation budget that the health-capacity rule forces with 4 units. Mitigation: a short schedule of 60
   ticks.
7. **Defect (development slip).** An unterminated string in `driver.py` killed the driver at import. Its
   failure was invisible because unit streams go to `/dev/null`. Runs `...003206` and `...003230` (freeze-vcu)
   are invalid as a result. Repair applied, and the run command now compiles every unit module first.
8. **Design defect, repaired.** `--linger` kept failed units alive, so Maestro's probe would have seen them as
   healthy. Linger now happens only after success, in the adapter, the driver and the stimulus.
9. **Live finding 04, before repair.** After a cancel while the world was paused, the guard listed actors
   before the commit tick, saw a stale list, and left `xverse-lite-ego`, `-camera` and `-radar`. The driver's
   socket file was also left. Repair: commit first, then destroy and verify that none remain (exit 3
   otherwise). The run command removes the run's socket. The leftovers were removed by the repaired guard,
   which reported none remaining.
10. **Owner tests.** `tests/live/test_phase7_live.py` (11 tests on owned fakes and the pinned 3.10 interpreter).
    Full suite: 192 passed, 39 subtests.
11. **Final live settings (2026-10-23, about 00:41).** Owned units fail fast when a dependency is missing:
    - the adapter's CARLA client timeout is 5 s, so a missing simulator ends the unit before Maestro's observe
      step and Maestro sees `ML-RUN-CHILD-EXIT`;
    - the driver's accept timeout is 12 s.

    The stimulus profile is 1 s idle, throttle 0.6 until 4.5 s, then brake 0.8 until 7 s. The driver episode
    is 9.5 s. The blueprint schedule has 80 ticks, because measured Maestro cycles span 0.17–0.7 s per tick
    with host load (live finding 03). Suite: 192 passed, 39 subtests.
12. **Live finding 05.** Two fresh server starts reported synchronous mode with 0.05 s until a client set
    the world asynchronous. The origin was not determined. The guard always leaves the world asynchronous and
    records the before and after state.
13. **Independent review 1 (2026-10-23 about 00:58, on compat `43abc9a` and blueprints `af43b3b`): NOT READY.**
    The findings are recorded before any repair. The full table is in the reviewer report, summarized here:
    - **R-1 HIGH.** The final runs (00:41–00:45) recorded dirty trees: compat `bb577a1` with 3 dirty files and
      blueprints `288c800` with 1. The commits came afterwards, so the evidence is not bound to the reviewed
      code.
    - **R-2 HIGH.** Flow receivers were activated with the clock at 0. All 224 of the 224 Argus flow events are
      spurious deadline misses stamped at tick 0. Freshness is circular, because the receiver clock is the
      item's own origin, so the age is always 0.
    - **R-3 HIGH.** The baseline input is not comparable:
      - legacy `virtual_vehicle.py` divides throttle by 1.2, so 0.6 is applied as 0.5;
      - the legacy `clock_status` lags world time, so the stimulus held throttle for 6.06 s of simulation time,
        against 3.50 s in Lite;
      - the legacy `velocity_status` lags as well.

      None of this was declared.
    - **R-4 MED.** The bridge reconciliation claims the driver reproduces the b10e6d8 semantics. It does not
      reproduce the throttle damping, and the file is not referenced from the log or the README.
    - **R-5 MED.** The XDL is the platform sample fixture with names changed. The runtime flows and the
      `carla-simulation` domain are not planned, and the flow bindings are hard-coded.
    - **R-6 MED.** After the cancel, Maestro's closure is incomplete: `cleanupComplete` and
      `normalUnitRecordsComplete` are false, and the Argus manifest shows 0 events, unassessed. A health
      deadline during the pause was not exercised, because the pause was 2.08 s against a 5 s cadence.
    - **R-7 MED.** Control release in cleanup:
      - the guard un-pauses with the last throttle still applied (0.6 at 14.9 km/h);
      - the observer is stopped before the guard runs;
      - in bound mode, `close()` leaves the last throttle on a vehicle the adapter does not own;
      - there is no trap, and the residue check runs after the guard.
    - **R-8 MED.** The guard always forces asynchronous mode, against the author's "restore original world
      settings". The conflict was not raised.
    - **R-9 MED.** The stop at ticks 77–80 is not wall-paced, so the margin is about 2 s at 0.17 s per tick.
    - **R-10 MED.** The tick-owner check is a process-name grep only; established connections to :2000 and
      :2001 are not recorded.
    - **R-11 MED.** Finding 11's claim "fails before Maestro's observe step" is contradicted: the observe probe
      passed, and the failure surfaced as a child exit at tick 53.
    - **R-12 to R-17 LOW:**
      - R-12: brake onset is defined from the cached control, and the −25 m/s² peak is not annotated;
      - R-13: the freeze timing relative to the profile is not stated;
      - R-14: there is no carla-items/2 contract note;
      - R-15: the numbers in the documents disagree, the guard record has no timestamp, the placeholders are
        unlabelled, and there is no run index;
      - R-16: the driver's link and session sit outside its error handling, and the socket permission is set
        after bind;
      - R-17: the observer and the runtime read the same snapshot velocity.

    Confirmed by the reviewer:
    - nothing constructs `RuntimeReadiness` or `execution_approved`;
    - oracle separation holds;
    - the nominal, baseline, freeze, cancel and no-carla numbers were recomputed from the raw files;
    - the suite: 192 passed.
14. **Repairs for review 1 (2026-10-23 about 01:10), with decisions DLG-11 to DLG-13 recorded in the thesis
    authorization record before the repairs:**
    - **R-1.** `run-live.sh` and `run-baseline.sh` refuse dirty candidate trees unless
      `XVERSE_LIVE_ALLOW_DIRTY=1`, and record the HEAD revision and a diff SHA-256. Every case is re-run from
      clean commits.
    - **R-2.**
      - The receivers activate at the first frame, after the clock is seeded.
      - `FlowEvidence` gets the Lite loop's tick index.
      - The simulation-domain age is 0 by construction, because the adapter delivers same-frame samples only;
        stale samples are caught by the adapter's `FRAME` rule. This is now disclosed.
      - Delivery freshness is measured in the host-monotonic domain, as the tick round trip against a 200 ms
        bound (`hostLatency`).
      - The earlier Argus flow artefacts, with their spurious deadline-miss events, are disclosed as defective.
    - **R-3 (DLG-12).** The stimulus is keyed on host time in both runs (`--time-base wall`). The legacy ÷1.2
      throttle damping is declared, and the report shows the actuated and commanded throttle of each run.
    - **R-4.** The reconciliation is corrected, with a throttle-mapping row, and copied to
      `bridge-identity-reconciliation.md` here.
    - **R-5.** The XDL elements are renamed to meaningful names and the fixture's declared text is replaced.
      The remaining limits are recorded in `maestro-run.json` (`xdlLimits`): one schedule domain, and the runtime
      flows and `carla-simulation` domain are bound in the loop, not planned.
    - **R-6.**
      - The cancel case now pauses for 6 s, beyond the 5 s probe freshness.
      - **Platform finding:** after a cancel, Maestro reports `cleanupComplete` false and
        `normalUnitRecordsComplete` false. The Argus manifest of the cancelled run shows 0 events, unassessed,
        while `events.jsonl` has events. The cancellation is not recorded in Argus or the M3 journal.
      - Not repaired (platform); the "Maestro closure after cancel" coverage is marked partial.
    - **R-7.**
      - `LiveSource.close()` holds an owned ego (throttle 0, brake 1, hand brake) before destroying it, and
        releases a bound vehicle to neutral; this is best effort.
      - The guard holds owned egos before un-pausing.
      - The run command checks residue before the guard, keeps the observer running through the guard, and
        runs its cleanup from a `trap` on EXIT, INT and TERM.
    - **R-8 (DLG-11).** The guard restores the pre-run settings that the run command recorded
      (`world-before.json`).
    - **R-9 (DLG-13).** Success requires every owned completion marker, and each is written only after the
      unit completes. The report checks completion per run.
    - **R-10.** Established CARLA connections are recorded before and after the run. Any client other than
      the session host's port detection (`moshi-hook`) blocks the run.
    - **R-11.** Correction to finding 11: with the simulator missing, the adapter is still alive at the
      observe probe, which checks liveness only. The failure surfaces as a child exit once the 5 s client
      timeout expires (`ML-RUN-CHILD-EXIT`).
    - **R-12.** Brake onset is measured from deceleration (below −2 m/s² after the peak), and the
      brake-signal onset is reported separately. The −25 m/s² values are annotated as simulator physics.
    - **R-13.** The report states where the freeze fell relative to the actuation.
    - **R-14.** `carla-items-2.md` is added as a successor contract note.
    - **R-15.** The numbers are reconciled (final: 80 ticks, 9.5 s). The guard record is timestamped. The
      synthetic harness placeholders are labelled in `maestro-run.json`.
    - **R-16.** The driver's link and session are inside its error handling, and the socket is created
      under umask 0177.
    - **R-17.** The shared snapshot source is stated in the report.

    Tests: 3 new tests. Suite: 195 passed.
15. **Live finding 06, recorded before repair.** Re-verification of R-7(a) in run `lite-…010544-cancel-paused`
    (clean commits). The guard's hold step reported `held: []`, although the killed adapter's ego, camera and
    radar were present: the guard destroyed them after its commit tick. In a paused synchronous world a new
    client's actor list is stale until a tick (compare finding 04), so the hold before un-pausing found
    nothing. The ego therefore ran one commit frame with its last control.

    Repair:
    - The adapter writes an owned-actor registry (`--owned-registry FILE`) right after spawning.
    - The guard reads it, holds owned vehicles with a server-side `ApplyVehicleControl` batch addressed by ID
      before un-pausing, and destroys the registry actors by ID with `DestroyActor`.
    - The list-based destroy and the verification stay as they are.
16. **Re-verification from clean commits (compat `6fd7f28`, blueprints `085983b`; 2026-10-23 01:07–01:10).**
    - **Runs:** baseline, nominal, freeze-vcu, cancel-paused and no-carla were all re-run. One nominal attempt
      failed at Maestro startup with `ML-CONTROLLER-TIMEOUT`, before any unit, and was re-run.
    - **Guard:** in cancel-paused it held the ego by ID while the world was still paused (`held [52]`), then
      destroyed the three owned actors via the registry, with none remaining.
    - **Two follow-ups found in the final evidence:**
      - The nominal Argus flow run was empty. With the repaired activation there are no anomalies, and no
        summary events were written. Repair: the loop writes one `FlowEvidence.summary` event per flow, as the
        platform harness does.
      - The report did not find the fault events, which are under the `io.xverse.faults` extension. Repair: the
        lookup checks any extension.

      Nominal and freeze-vcu are re-run after this change.
17. **Defect found by re-verification, recorded with its recovery (2026-10-23 about 01:13).**
    - **What happened:** the baseline run `baseline-…011253` followed two Lite runs whose guard had restored,
      per DLG-11, the recorded pre-run state. That state was the unexplained synchronous start-up state with
      frame 0 and no tick owner.
    - **Effect:**
      - the legacy `virtual_vehicle.py` could not get a ticking world, so the stimulus exited `no-clock`;
      - the legacy process ignored SIGINT and SIGTERM, and the script's `wait` hung until `timeout`;
      - the legacy vehicle's `ego_vehicle` actor (id 30) was left behind.
    - **Manual recovery, recorded in that run directory:**
      - SIGKILL of the hung legacy process (pid 1582975, started by this session);
      - world set asynchronous;
      - actor 30 destroyed by ID; no vehicles remained.
    - **Repairs:**
      - **DLG-11a:** the preflight records whether the frame advances, and the guard restores a recorded
        synchronous state only when it had a tick owner, otherwise asynchronous, with the reason recorded.
      - The baseline normalizes an ownerless synchronous world to asynchronous as a declared setup step.
      - The baseline has a cleanup trap and a bounded stop: INT, then TERM, then KILL, then `wait`.
18. **Final evidence set (2026-10-23 01:18–01:22).** Revisions: compat `f2b9088`; blueprints `cc5774f`, and
    `6666953` for the freeze case. All trees were clean (`dirty=0`, empty-diff hash). Evidence root
    `…/runs/xverse-lite-live-20261022/report-final` (`report.json`, `report.md`, and `run-index.json` with 55
    runs and their dispositions).

    | Run | Result |
    | --- | --- |
    | `baseline-…011802` | legacy loop; peak 23.2 km/h at actuated throttle 0.5 (÷1.2 damping) for 3.48 s; world asynchronous afterwards, no vehicles |
    | `lite-…011815-nominal` | Maestro succeeded, all markers collected; peak 28.8 km/h at commanded throttle 0.6 for 3.45 s; standstill 0.55 s after deceleration onset; host tick latency p95 about 24 ms, no tick above 200 ms; 376 flow items delivered; Argus flow run holds its 2 summary events |
    | `lite-…012125-freeze-vcu` | Maestro succeeded; freeze applied and cleared over 1.38 s of host time, overlapping the stimulus throttle window; commanded throttle delayed by 0.647 s; peak 24.0 km/h; automatic thaw recovered the loop |
    | `lite-…011934-cancel-paused` | Maestro `ML-SCHEDULE-CANCELLED` after 6 s paused; the guard held the ego by ID before un-pausing, destroyed 3 owned actors and restored asynchronous mode, because the recorded synchronous state had no owner (DLG-11a) |
    | `lite-…012000-no-carla` | Maestro `ML-RUN-CHILD-EXIT`; adapter failed after its 5 s client timeout; cleanup complete; no residue |

    At the end CARLA was stopped by this session and `zenohd` was left running, which is the state at session
    start apart from the author's own `zenohd`, which had died and was replaced.
19. **Independent review 2 (2026-10-23 about 01:30, on compat `8517de6` and blueprints `5ce3bc8`): NOT READY.**
    It reports two MEDIUM findings, both on documentation and traceability. It confirmed that R-1, R-2, R-4,
    R-7, R-8, R-11 to R-14, R-16 and R-17 are repaired; R-5 and R-10 are partly repaired; R-3 is repaired in
    the evidence, with a partial declaration; R-6 is accepted as a disclosed platform finding; and R-9 is
    repaired by DLG-13. It also confirmed that the clocks are comparable: Maestro's host time and the units'
    monotonic time agree within 0.8 ms.

    Findings, recorded before repair:
    - **N-1 MED.** The clean freeze run `lite-…011855` (Maestro succeeded, freeze in the idle second) was
      superseded without a log entry. The 8→20 tick change and the restart of server instance 4 are not
      recorded, and the run index gives 011855 a generic disposition.
    - **N-2 MED.**
      - Item 18 wrongly attributes the cancel-paused restore to DLG-11a; that run's pre-run state was
        asynchronous and advancing.
      - The blueprint README is stale: no DLG-11, 11a or 12, no ÷1.2 damping, no wall time base, no registry,
        no contract notes.
      - `report.md` lacks the actuated and commanded throttle.
    - **N-3 LOW.** The cancel pause happened with the ego at rest (throttle 0), so the hold was not shown
      against a throttled ego.
    - **N-4 LOW.** Markers are also written on failure, and the completion check reads file names only.
    - **N-5 LOW.** After a BLOCKED preflight, the trapped guard still runs.
    - **N-6 LOW.** The baseline trap lacks EXIT, a leftover legacy `ego_vehicle` is not destroyed, and the exit
      status ignores failures.
    - **N-7 LOW.** CARLA clients without a `users:` field pass the check, and the advancing-synchronous branch
      of DLG-11a is probably unreachable.
    - **N-8 LOW.**
      - The "monotonic_ns" label in the log is a wall-clock value.
      - `restored` ignores `fixedDeltaSeconds`.
      - The registry destroy does not check the role prefix.
      - The report revision is not recorded.
      - The tick-rate range in the README is wrong (0.069 s per tick was seen).
20. **Repairs for review 2 (2026-10-23 about 01:35).**
    - **N-1, the history that was missing.**
      - `lite-…011855-freeze-vcu` (compat `f2b9088`, blueprints `cc5774f`, clean) succeeded, but its freeze
        (ticks 16 to 24, 0.40 s of host time) fell in the stimulus's idle second. A 0.15 s stale window was
        observed, with no effect on motion. It was superseded for that reason.
      - The fault duration was changed from 8 to 20 ticks (blueprints `6666953`), and CARLA server instance 4
        was started (01:20:53).
      - That instance's start state was again synchronous at frame 0 with no tick owner (finding 05).
      - The case was re-run as `lite-…012125`.
      - The final set from item 18 therefore spans server instances 3 and 4. The run index now gives 011855 a
        specific disposition.
    - **N-2.**
      - Correction to item 18: cancel-paused (`…011934`) restored asynchronous mode because its pre-run state
        *was* asynchronous and advancing. DLG-11a applied only in freeze `…012125`.
      - The README is updated: preflight, guard order and registry, DLG-11 to DLG-13, the wall time base, the
        ÷1.2 damping, and the contract notes.
      - `report.md` gains an actuated and commanded throttle column.
    - **N-3.** The cancel case now pauses at 4 s, inside the throttle segment.
    - **N-4.** The harness records the marker contents and `markersOk`, and nominal success requires them; the
      report adds `allOwnedUnitsSucceeded`.
    - **N-5.** The guard is skipped when `world-before.json` is absent.
    - **N-6.** The baseline traps EXIT, INT and TERM. It destroys a leftover `ego_vehicle` that did not exist
      before the run, and exits non-zero on a stimulus failure or residue.
    - **N-7.** Any CARLA client except `moshi-hook` blocks the run, including connections without a `users:`
      field. The advancing-synchronous branch of DLG-11a is noted as normally unreachable, because preflight
      blocks a connected tick owner; it is kept as a safety net.
    - **N-8.**
      - The log label is corrected to `wall_epoch_ns`.
      - `restored` also compares `fixedDeltaSeconds`.
      - Registry entries must carry the `xverse-lite-` role prefix.
      - The report records its own revision.
      - The README tick range is corrected to 0.07–0.7 s per tick.

    Every case is re-run from the new commits (item 21).
21. **Re-verification defect, recorded with its repair (2026-10-23 about 01:33).**
    - **What happened:** on the newly started server instance 5, the final baseline (`baseline-20261023T013121`)
      normalized the world, which was in the synchronous start-up state at frame 0. The guard applied
      asynchronous settings and one 2 s commit tick, but the world stayed synchronous, so the normalization
      failed.
    - **Effect:**
      - the legacy vehicle had no ticking world, so the stimulus exited `no-clock`;
      - the bounded stop killed the legacy vehicle (exit 137);
      - the baseline correctly reported FAILED, with exit 3.
    - **Probe:** the same apply-and-tick sequence, run by hand a minute later on the same instance, took
      effect (`normalisation-probe.txt`). The likely cause is that the commit tick timed out while the server
      was still initializing.
    - **Repair:** the guard retries apply-and-tick up to 3 times with a 5 s tick, and records the number of
      attempts (`applyAttempts`). A new test covers it; suite: 197 passed.
    - **Re-run:** every case, from the new commits.
22. **Invalid baseline, recorded with its repair (2026-10-23 about 01:37).**
    - **What happened:** the baseline `…013416` ran while a leftover `ego_vehicle` (actor 24) was in the
      world. Its observer, which selects by role name, tracked that stationary actor (1501 frames, peak 0)
      instead of the vehicle the run spawned. The run is **INVALID** as evidence.
    - **Origin:** the failed baseline `…013121` killed its legacy vehicle. The vehicle's queued spawn most
      likely executed when the manual normalization probe ticked the synchronous world.
    - **Repair:**
      - actor 24 was destroyed by ID, and no vehicles remained;
      - the baseline refuses to start when an `ego_vehicle` already exists (blueprints, next commit).
    - **Re-run:** the baseline.
23. **Final evidence set, replacing item 18 (2026-10-23 01:36–01:39, CARLA server instance 5).**
    - **Revisions** (clean trees, empty-diff hash): compat `f08b4e3`; blueprints `381780e` for the baseline
      and `1c6cfa5` for the Lite cases. The `1c6cfa5` change only adds the Lite preflight's empty-world check.
    - **Where:** `…/runs/xverse-lite-live-20261022/report-final` (`report.json`, `report.md`, and
      `run-index.json` with 65 runs and specific dispositions).
    - **World before each case:** no vehicles. The cases ran consecutively on instance 5.

    | Run | Result |
    | --- | --- |
    | `baseline-…013652` | legacy loop; actuated throttle 0.5 (÷1.2) for 3.495 s; peak 23.75 km/h; standstill 0.43 s after onset; minimum −38.5 m/s² (simulator physics at a 4–14 ms asynchronous step); world afterwards asynchronous with no vehicles |
    | `lite-…013723-nominal` | Maestro succeeded; markers collected, each recording success; commanded and actuated throttle 0.6 for 3.45–3.5 s; peak 28.8 km/h; standstill 0.55 s after onset |
    | `lite-…013803-freeze-vcu` | Maestro succeeded; the freeze overlapped the stimulus throttle window; commanded throttle shortened to 2.2 s; peak 18.75 km/h; automatic thaw recovered the loop |
    | `lite-…013844-cancel-paused` | paused at 4 s while throttled (13.9 km/h); Maestro `ML-SCHEDULE-CANCELLED`; the guard held the ego by ID before un-pausing, and the observer saw it decelerate (−7.0 m/s²); 3 owned actors destroyed; settings restored with 1 apply attempt |
    | `lite-…013916-no-carla` | Maestro `ML-RUN-CHILD-EXIT`; adapter marker `{code: 3}`; cleanup complete; no residue |

    End state: CARLA stopped (by this session), GPU free, `zenohd` running, no unit processes, no sockets.
24. **Independent review 3 (2026-10-23 about 01:47, on compat `8657e5f` and blueprints `1c6cfa5`): READY FOR
    AUTHOR REVIEW**, with no HIGH or MEDIUM finding.
    - N-1 to N-8 are repaired; N-3 and N-6 leave LOW residue.
    - Item 23 was confirmed against the raw evidence.
    - Suite: 197 passed.

    LOW findings and dispositions (engineer decision):
    - **Fixed (documentation and report only; no run code changed):**
      - M-1: README behaviour sections;
      - M-6: the report's throttle label follows the run kind;
      - M-7: item 22 and item 23 corrections, below;
      - M-8: the cancel-hold limit is disclosed, below.
    - **Left open for the author.** Each would change run code after the final evidence was recorded:
      - M-2: the `restore.py` docstrings are stale, and the retry stops on a synchronous-mode match only;
      - M-3: the baseline does not check the `world_settings` result;
      - M-4: the baseline's `ego_vehicle` check runs before normalization;
      - M-5: the baseline's leftover destroy is unverified, and its exit status is incomplete.

    Corrections:
    - **Item 22:** the Lite runs `…013430-nominal`, `…013509-freeze-vcu` and `…013549-cancel-paused` also ran
      with leftover actor 24 in the world, and are superseded for that reason, as the run index records.
    - **Item 23:** the baseline's asynchronous step range is 4.8–31.5 ms over all frames, and 5.2–11.9 ms while
      the ego exists (not "4–14 ms").
    - **Item 23, cancel row (M-8):** the guard destroyed the ego about 0.25 s of simulation time after the hold,
      at 8.49 km/h. The hold is shown as deceleration (−4.6, −7.0 and −6.0 m/s²), not as standstill.
25. **Decision (engineer, 2026-10-23 about 04:15, under the author's delegation): repair M-2 to M-5 now and
    re-run the evidence set,** so that the author's AD-01 decision does not depend on a repair cycle.
    Acceptance stays with the author.

    Planned repairs, recorded before the edits:
    - **M-2:** correct the `restore.py` docstrings (bounded retry; the record format). The retry stop
      condition also compares `fixedDeltaSeconds`.
    - **M-3:** the baseline blocks when `world_settings` fails or yields an empty record.
    - **M-4:** after normalization the baseline lists the vehicles again, and blocks on an `ego_vehicle`
      found then.
    - **M-5:**
      - the baseline verifies the leftover destroy by listing the world again;
      - its exit status includes the virtual-vehicle, VCU and observer exit codes, any vehicles remaining
        after the run, the stimulus outcome and residue.
26. **Re-run after the M-2 to M-5 repairs (2026-10-23 04:06–04:13). The final evidence set replaces item 23.**
    - **First attempt, invalid:** CARLA server instance 6 hung. It was listening on 2000, but every client
      timed out after 15 s, at 0% CPU (`carla-server-6/HUNG.txt`). The baseline `…040604` was correctly
      reported FAILED (legacy vehicle exit 137, no clock), and the Lite preflights `…040739`, `…040750` and
      `…040801` correctly BLOCKED ("cannot read the world settings"). All four are INVALID because the
      external dependency failed. The instance was replaced by instance 7.
    - **Final set:** blueprints `320a284`, compat `f6d4a3b`, clean trees, all on instance 7.

    | Run | Result |
    | --- | --- |
    | `baseline-…041014` | normalized the ownerless synchronous start-up state with **2 apply attempts**, the review-log 21 case now handled; the world listed again after normalization has no vehicles; exit 0 with full status (stimulus ok, virtual vehicle 0, VCU 0, observer 0, no vehicles left, no residue); peak 23.74 km/h at actuated throttle 0.5 for 3.48 s |
    | `lite-…041029-nominal` | Maestro succeeded; `markersOk`; peak 28.82 km/h at 0.6 for 3.45–3.5 s |
    | `lite-…041108-freeze-vcu` | Maestro succeeded; commanded throttle shortened to 2.05 s by the freeze; peak 18.67 km/h |
    | `lite-…041146-cancel-paused` | `ML-SCHEDULE-CANCELLED`; guard held ego 35 by ID before un-pausing, destroyed 3 owned actors, restored with 1 attempt |
    | `lite-…041222-no-carla` | `ML-RUN-CHILD-EXIT`; cleanup complete |

    `report-final` and `run-index.json` (74 runs) are regenerated. End state: CARLA stopped; `zenohd` running.
