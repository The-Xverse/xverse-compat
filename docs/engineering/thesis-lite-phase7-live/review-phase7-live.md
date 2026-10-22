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
