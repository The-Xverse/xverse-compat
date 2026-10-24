# X-Verse Lite 1.0 release record: `xverse-compat`

**Status: release candidate rc.1, recorded 2026-10-24.** The step from rc.1 to the final release depends on the
S1d soak, which is pending and runs on the tagged revisions (platform record, section 9).

| Item | Value |
| --- | --- |
| Repository | `/home/jefferson/xverse-compat` |
| Code revision | main `30446f6c7f234ec600398ba5db6c57846210c772` (S1d2 merge, equal to `origin/main` on 2026-10-24) |
| Release commit | the commit on `release/xverse-lite-1.0-rc.1` that adds this record; its parent is `30446f6`, and it changes documentation only (this record and `README.md`) |
| Tag | `xverse-lite-v1.0.0-rc.1`, naming the release commit (created and pushed separately, not by this commit) |
| Last revision changing `src/`, `tests/` or `xdl/` | `e05d467` (S1c-2); `f0f31f9` and the S1d2 merge change only `docs/engineering/thesis-lite-stabilization/review-s1c.md` |
| Package | `xverse-compat` 0.2.0, depending on `xverse-xdl` 0.4.0 |
| Shared sections | program history, platform evidence, CAPA, decision table and open items: `xverse-platform` `docs/releases/xverse-lite-1.0.md` (the platform record) |

## 1. What X-Verse Lite 1.0 is

X-Verse Lite 1.0 is the first engineering-integration baseline of X-Verse Lite across `xverse-platform`,
`xverse-compat` and `xverse-blueprints`. This repository supplies the compatibility side: the descriptors and
admission record of the selected CARLA and bridge artifacts, the owned CARLA client adapters, the owned live units
that connect Maestro Lite to the unchanged legacy VCU, and the restore guard that returns the CARLA world to its
recorded state. It is engineering integration only: not AEB validation, not M1, not X-Verse fitness for purpose
and not a scientific result. The admission record keeps `executionAuthority: absent`; live execution was
authorized separately for Phase 7 and for S1 (S-D6).

## 2. Components and entry points

| Component | Phase | Location and entry points |
| --- | --- | --- |
| Compatibility descriptors | 4 | `xdl/descriptors/aeb-sim/` (`system`, `profile`, `deployment`, `component-carla-server`, `component-bridge-auto` `.xdl.yaml`; `carla-sensors.json`; `live-scenario.json`); `src/xverse_compat/{descriptors,selection,admission,contracts,platform_pin}.py` |
| Selection and admission record | 4 | `xdl/selection/aeb-sim-selection.json`, `aeb-sim-contracts.json`, `artifact-inventory-20261022.json`, `aeb-sim-admission.json`; built by `scripts/admit_phase4.py`, which also re-pins `platform-api.lock.json` |
| Bridge route adapter | 6 | `src/xverse_compat/adapters/bridge_route.py` (`BridgeRouteAdapter`), `bridge_samples.py`; the bridge's vehicle-speed stream only |
| CARLA client adapters | 4b, 7 | `src/xverse_compat_carla/`: `main.py` (adapter process, the only tick owner and actuator writer), `protocol.py` (`xverse-compat.carla-items/1`; `carla-items/2` over a Unix socket since Phase 7), `sensors.py`, `actuation.py`, `observe.py`, `groundtruth.py` (evaluation-only), `scenario.py`, `settings.py`, `readiness.py`. Runs on `/usr/bin/python3.10` with the pinned `carla` 0.9.15 cp310 site (`tools/carla/make-client-env.sh`) |
| Live driver | 7, S1c-2 | `src/xverse_compat/live/driver.py` (`xverse_compat.live.driver`): platform side of `carla-items/2`, Phase 6 flow receivers, Argus flow evidence, zenoh gateway to the legacy VCU |
| Live stimulus | 7, S1c-2 | `src/xverse_compat/live/stimulus.py` (`xverse_compat.live.stimulus`): the declared pedal profile, including the long-run profile |
| Readiness helpers | S1c-2 | `src/xverse_compat/live/readiness.py`: nonce-marker announcement (`announce_ready`) for the owned units (S1 FR-011) |
| Restore guard | 7, S1c-1 | `src/xverse_compat_carla/restore.py` (`python3.10 -m xverse_compat_carla.restore --carla-site … --settings-from world-before.json --owned-registry …`): holds the owned ego to standstill, restores the recorded settings (DLG-11, DLG-11a), destroys `xverse-lite-*` actors and records the hold, un-pause, standstill and destroy times (FR-022) |

Contracts: `docs/engineering/thesis-lite-phase7-live/carla-items-2.md` and `bridge-identity-reconciliation.md`.

## 3. History of this repository

| Step | Merge | Date | Suite at acceptance | Review log |
| --- | --- | --- | --- | --- |
| Phase 4 compatibility descriptors | `ee9db2a` | 2026-10-22 | 76 passed | `docs/engineering/thesis-lite-phase4/review-phase4.md` |
| Phase 6 bridge route adapter, platform re-pin | `39ae980` | 2026-10-22 | 92 passed (admission record rebuilt, finding 8) | `docs/engineering/thesis-lite-phase6/review-phase6.md` |
| Phase 4b CARLA client adapters | `6271ac2` | 2026-10-22 | 181 passed, 39 subtests | `docs/engineering/thesis-lite-phase4b/review-phase4b.md`, findings 1–21 |
| Phase 7 live CARLA integration | `39d31fa` | 2026-10-23 | 197 passed, 39 subtests | `docs/engineering/thesis-lite-phase7-live/review-phase7-live.md`, items 1–28 |
| S1c-1 | `25e4e1f` | 2026-10-23 | 207 passed, 39 subtests | `docs/engineering/thesis-lite-stabilization/review-s1c.md`, findings 1–14 |
| S1c-2a (log only in compat) | `bb07492` | 2026-10-23 | — | findings 15–27 |
| S1c-2 | `e05d467` | 2026-10-24 | 244 passed, 39 subtests | findings 28–56 |
| S1d soak health-check repair (log only in compat) | `f0f31f9` | 2026-10-24 | — | findings 57–59 |
| S1d2 operator-signal stop (log only in compat) | `30446f6` | 2026-10-24 | — | findings 60–62 |

The release commit also updates `README.md` to the current state of this repository. The acceptance basis of each
step is in the platform record, section 3. Phase 4 was accepted as a bounded partial
delivery under the author's goal; Phases 4b and 6 under delegation (DLG-1, DLG-2, DLG-5, DLG-6); Phase 7, S1c-1 and
S1c-2a by the author; S1c-2, S1d and S1d2 under the author's acceptance of 2026-10-24.

## 4. Cross-repository compatibility set

| Element | Value |
| --- | --- |
| Platform main | `a9db0ac39a858c0b2d341149042a8a97b7dcf393` |
| Compat main | `30446f6c7f234ec600398ba5db6c57846210c772` |
| Blueprints main | `5fa8bcba3545e5675e512baf5baa5738bac42599` |
| Platform-API lock | `platform-api.lock.json`: algorithm `sha256-path-null-content-null-v1`, 26 files (`pyproject.toml`, `src/xverse_xdl`, `xdl/profiles`, `xdl/schemas`), `treeSha256` `ce779e57d888b61b2a40fa7b4a05999ad900a33e48fc71e340a082b902fb43cd`, `platformRevision` `a9db0ac39a858c0b2d341149042a8a97b7dcf393`. Re-pinned in finding 55; the surface is unchanged since the `ee91697a4` re-pin (finding 48) because S1a-6 changed only `src/xverse/maestro/coverage.py` |
| Pinned live environment | `xverse-lite-live-20261022`, rebuilt from platform `a9db0ac39`; wheel SHA-256 `cea5ced404c277157df9496086fd4a0a8f011c58e01c8e7d659fc2fb5b53cddf` (finding 55). The test venv `/dev/shm/compat-p6-venv` has the same wheel |
| Pinned artifacts (admission record) | `carla-server` `sha256:1da989e4ff136e0658fdea421bc1da2b0e5cb018c6e767efc4f6129c21ab1a81`; `bridge-auto` `sha256:37b6b6be6ac843475bcddd9f2139d6f265e42aaa30d7f295f8d586022bce62ed`; `carla-python-client` `sha256:61449e33260f6a0cfd2f88d56f2463a5797a0b51bc46618beec07365422d4ad6`; all `recomputed: match` |

## 5. Verification and evidence

- **Compat suite: 244 passed, 0 failed, 39 subtests** in
  `docs/engineering/thesis-lite-stabilization/verification-20261024-s1c2-f.log` (log SHA-256 `dd72e243…`, as
  recorded in the admission record). Command recorded in `xdl/selection/aeb-sim-admission.json`:

  ```bash
  env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src \
    /dev/shm/compat-p6-venv/bin/python -m pytest tests -q -p no:cacheprovider
  ```

  Finding 55 records an erratum: the first admission call passed log e with pre-re-pin counts (243 and 1); the
  committed record was rebuilt against log f, and a rerun gave 244 passed. The same command on `30446f6`, with the
  same venv, gave 244 passed and 39 subtests on 2026-10-24.
- **Admission record** (`recordedAt` 2026-10-24T05:53:18Z): `executionAuthority: absent`; blockers
  `XVERSE-PLAN-RESOURCE-LIMITS-UNAPPROVED`, `XVERSE-PLAN-THESIS-G2` to `G6`, `XVERSE-PLAN-THESIS-UNEXECUTED`;
  `review` and `acceptance` null; contracts 16 statements, 11 verified.
- **Live evidence** in which these modules ran, on loop10 under
  `/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/runs/lite-stabilization-s1/`: dev3–dev8 and
  `vs09-20261024` (blueprints record, section 5). In 86 of 86 recorded `restore-guard.json` files the target was
  asynchronous, `after.synchronousMode` false and `restored` true (finding 58).
- **Platform evidence** consumed through the pinned wheel: platform record, section 5.

## 6. Engineering decisions

The decision table (S-D1 to S-D9, DR-1 to DR-21) is in the platform record, section 6; source
`specs/029-lite-stabilization/review/author-decisions-20261023.md` (thesis repository), SHA-256
`38a6fc23888727a1f4904601d824d3c2af49604fd1864c10e0676179d35169e4`. Decisions that shape this repository:

| ID | Effect here |
| --- | --- |
| DLG-1 | Pinned `carla` 0.9.15 cp310 client on system CPython 3.10.12, out of process (`specs/021-thesis-lite-program/review/delegated-decisions-20261022.md`) |
| DLG-2 | Camera, radar, ground-truth and actuation streams on owned adapters over CARLA's public client API; the bridge unchanged |
| DLG-10, DLG-11, DLG-11a | Restore guard: owned actors only; restore the recorded settings; a synchronous world without a tick owner is restored to asynchronous (Phase 7 authorization record) |
| DR-6, DR-14 | Argus conditions and the no-carla diagnostics that the live driver's evidence must meet (flagged; DR-14 delegated) |
| DR-21 | A freshly started server is synchronous with no tick owner; the guard always ends asynchronous (delegated, flagged) |

## 7. Declared limits and residuals

- Live behaviour of the adapters is verified only through the Lite blueprint runs (Phase 7, S1c, VS-09); the
  offline suite runs on owned fakes and a stub zenoh.
- `brakeStatus` and `wheelSpeedEscStatus` stay blocked (G2). A brake command echo is acknowledgement, not braking
  evidence. A live ground-truth export is evaluation-only.
- No steering; the reverse gear is not carried (blueprint README).
- The bridge supplies only the vehicle-speed stream. Blockers G3 to G6 remain recorded in the admission record.
- The cold-start readiness of the adapter after a CARLA server start (1.27 s to more than 1.70 s) is covered only
  by the soak warm-up (DR-18, DR-19).
- The restore guard does not run after a BLOCKED preflight or in baseline runs (finding 59, LOW-4).
- Carried LOW items: R4-2 (a TERM sent only to the script PID during the harness waits for it), the observer
  orphaned after a group SIGKILL or hangup, one-command signal windows (S1c-1 package).
- Non-claims: platform record, section 7.

## 8. How to verify a checkout

1. `git -C <checkout> rev-parse HEAD` equals the release revision; `git -C <checkout> status --porcelain` is empty.
2. `platform-api.lock.json` shows `platformRevision` `a9db0ac39a858c0b2d341149042a8a97b7dcf393` and `treeSha256`
   `ce779e57…`.
3. Run the compat suite with the command in section 5. It needs a venv with the platform wheel `cea5ced4…`; the
   recorded venv is `/dev/shm/compat-p6-venv` on the development host. Expected: 244 passed, 39 subtests.
4. Rebuilding the admission record and the lock uses `scripts/admit_phase4.py --platform-root PATH
   --verification-log PATH --passed N --failed N [--command TEXT] [--output PATH]` (usage line of the script);
   it changes tracked files and is not part of a read-only verification.
5. Live cases (`run-live.sh`) and the soak dry run: blueprints record (`xverse-blueprints` `docs/releases/xverse-lite-1.0.md`), section 8. They need loop10, the pinned
   CARLA client environment `/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310`
   and, except for no-carla and the dry run, a CARLA 0.9.15 server.

## 9. Open items

- The S1d soak (S1-T16) is pending; the rc.1 to final step depends on it.
- The ledgers (S1-T17), Phase 8 (planning; AD-01, AD-21, AD-23, AD-29, AD-30, AD-33 and AD-34 decided) and
  Phase 9: platform record, section 9.
- Phase 8 re-carries the D6-11 assembled-system flow verification (D7-5) and the G2 streams.

## Sources

Thesis repository `/home/jefferson/distributed_safety_critical_thesis`. These files are untracked or locally
modified there, so the SHA-256 below, computed at 2026-10-24 09:15 WEST, is their identity for this record.

| File | SHA-256 |
| --- | --- |
| `specs/029-lite-stabilization/review/acceptance-package-s1c1-20261023.md` | `7f1e07fa10096c28f55e15c92d470ba711ea9b45010b68f31146dd3b42d0c342` |
| `specs/029-lite-stabilization/review/acceptance-package-s1c2a-20261023.md` | `5f9e6ae7f40b8ce70a410524e18819309b9597fb3ed6143b619f9af8f8116276` |
| `specs/029-lite-stabilization/review/acceptance-package-s1c2-20261024.md` | `deab3886875592e0a08d0866154bb7b22d8a01828cf4a24d7a9bade039c0412a` |
| `specs/021-thesis-lite-program/tasks.md` | `bee0c284b1a4f3a49c79ea4b547f543ce79416fdb3b5fd31669ddbda7cbd7b94` |
| `specs/021-thesis-lite-program/review/delegated-decisions-20261022.md` | `480397328a423cb868a0535b36583b2f0a1e4be4f4350f49fdf0a94389dcbd25` |
| `specs/003-thesis-lite-artifact-adapters/review/t07-acceptance-package-20261022.md` | `470527fce49100edde06f82d17bff5ca260a1f4f0d9e123596de083d619f440a` |
| `specs/028-lite-carla-client-adapters/review/acceptance-package-20261022.md` | `ff6fe275be4c3199b562ed0ece571b42559f1ec4e9aa1b4a160291fd0ad79cb5` |
| `specs/027-lite-flow-runtime/review/acceptance-package-20261022.md` | `e688de94a73b95f20988a1768b093e77d994328568fb32543485c3411506c547` |
| `specs/001-thesis-lite-compatibility-smoke/review/acceptance-package-20261023.md` | `566f555901a00c0caaec9713c903b75135d14245b90d8d56f08cc1528df5e72c` |
| `specs/001-thesis-lite-compatibility-smoke/review/author-authorization-20261022-live-integration.md` | `4eaac01cbfb4bc1a9a8589bdcc88cfefd5385d56fd9c91ffcdec0a66f18b1157` |
| `specs/029-lite-stabilization/review/author-decisions-20261023.md` | `38a6fc23888727a1f4904601d824d3c2af49604fd1864c10e0676179d35169e4` |
| `specs/029-lite-stabilization/review/acceptance-package-s1a6-s1d-20261024.md` | `ed579593a869427ac4b3d9261f3ea1aca15561cbc6d2c791432246ab2ea94814` |
