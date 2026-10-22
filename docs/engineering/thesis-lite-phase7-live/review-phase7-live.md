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
