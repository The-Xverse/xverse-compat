# Review log: Thesis Lite Phase 4b (CARLA client adapters)

Candidate: `candidate/phase4b-carla-client-20261022` from `xverse-compat` main `39ae980`.

Specification (thesis `specs/028-lite-carla-client-adapters`): planning rev 5a (five planning
reviews; environment location amended to loop10) and detailed design rev 1 (under review).

Decisions: DLG-1 (pinned `carla 0.9.15` cp310 client, out of process) and DLG-2 (owned adapters,
bridge unchanged). CARLA, the bridge and zenohd are never executed; there is no live session. Every
log edit is committed immediately.

1. Opening (2026-10-22). P4b-T01 first: `tools/carla/make-client-env.sh` creates the pinned
   environment on loop10 and writes `env-record.json`. Then P4b-T02–T05 follow the detailed design
   once its review passes.

2. P4b-T01 first attempt (2026-10-22). The environment was created on loop10 (195 MB) and the
   pinned wheel was verified and installed with `--no-deps`. The offline `import carla` aborted
   (rc 134): `std::logic_error: basic_string::_M_construct null not valid`. Under `env -i` the
   variable `HOME` is unset, and the CARLA extension evidently builds a `std::string` from it at
   import.

   With `HOME=/nonexistent-carla-home` (a deliberately absent directory, so no user configuration
   can be read), the import succeeds: version `0.9.15`, `carla.Client` present.

   Repair (recorded before the change):
   - The script and every adapter launch use
     `env -i PATH=/usr/bin HOME=/nonexistent-carla-home … -s`.
   - The thesis contract rule 5 and FR-001a launch command are amended accordingly. This is an
     engineering amendment under the author's delegation.
   - The script recreates the environment it created in the first attempt.

3. P4b-T01 complete (2026-10-22).
   - **Environment.** `…/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310` on loop10, 195 MB.
     The wheel is kept in `…/cache/xverse-compat-wheels/` (SHA-256 `61449e33…4ad6`, 31 895 950
     bytes).
   - **Record.** `env-record.json` (SHA-256 `b63a490e…`): the import returns 0 and `carla` version
     0.9.15; `pip freeze` lists only `carla`, `pip` and `setuptools`; `py_compile` result 0 (the
     package does not exist yet, so this is re-checked at V01b).
   - **User-site comparison** (`user-site-comparison.json`, plan item 1): all 9 payload files of the
     user-site `carla 0.9.15` cp310 are byte-identical to the pinned wheel. G6 is unchanged: the
     bridge runtime also loads unpinned `pygame`, `eclipse-zenoh` and `numpy` from the user site.

4. P4b-T02–T04 implemented (2026-10-22) against thesis detailed design rev 4, which is READY FOR
   IMPLEMENTATION after design reviews 1 (G1–G10), 2 (N1–N4) and 3 (PASS).

   **`src/xverse_compat_carla/`** (Python 3.10, standard library only): `codes`, `timeconv`,
   `descriptors`, `settings`, `items`, `sensors`, `actuation`, `groundtruth`, `sources`
   (`FakeSource`; `LiveSource`, a declared-unverified skeleton), `protocol` and `main`.

   **`src/xverse_compat/carla_client.py`**: `CarlaAdapterProcess` and `parse_outbound`.

   **Descriptors and fixtures.** `xdl/descriptors/aeb-sim/carla-sensors.json`. Fake fixtures
   `tests/carla/fixtures/{nominal,faults,episode,asynchronous,actuation}.json`.

   **Tests** in `tests/carla/`:
   - `test_units.py` (9): descriptors, settings, camera, radar (including the 500-detection line
     bound), motion, origins, counters, the command window, the fake mapping.
   - `test_protocol_subprocess.py` (6): runs the 3.10 adapter process through the client.
     - V06: nominal items through `xverse.flows.FlowReceiver`, all delivered with age 5 ms; no
       child process survives.
     - V03: refusals continue the stream without consuming sequence numbers.
     - `EPISODE`: exit 3, with the earlier flows of that frame standing.
     - Asynchronous settings: refused, exit 3.
     - V05: echo, `responded`, mismatch and pending acks; `COMMAND` refusals for a bad command and
       an unknown type.
     - V04: ground truth as a file only, and the client refuses a ground-truth message or NaN.
   - `test_env.py` (3): V01 env record, a live import 0.9.15 in the pinned env, and V01b: compile
     and import under 3.10 with no forbidden module loaded.

   **Results.** `tests/carla` gives 18 passed, three times in a row. The full owner suite gives 110
   passed.

   **Test-design correction (not a product defect).** The asynchronous test first expected
   `start()` to raise. The adapter correctly ends right after `hello`, so the test now uses
   `read_until_done()`, and `_send` tolerates an adapter that has already exited (BrokenPipe). The
   adapter's own output is unchanged.

   **Next:** P4b-T05, the re-derivation items 1–8.

5. P4b-T05 re-derivation, planned (recorded before the changes; thesis plan "P4b-T05 re-derivation"
   items 1–7 and design §9.8 item 8):
   1. **Inventory revision 7**, both copies in step (identical today, `67e579f1…`): add the cp310
      wheel (URL, SHA-256, size, `localPath`); `env-record.json` and `user-site-comparison.json` as
      cited files; and the user-site `RECORD` hashes of `carla 0.9.15`, `pygame 2.6.1`,
      `eclipse_zenoh 1.3.4`, `numpy 2.2.6`, `shapely 2.1.2`, `networkx 3.4.2` and `zenoh_cli 0.6.8`.
   2. **Selection pin `carla-python-client`.**
      - Make it `present`, with the PyPI `sourceRef`, `releaseArtifact: true`, digest,
        `digestCommand` and `localPath`.
      - Remove `reason`.
      - Set `toolchain` to "system CPython 3.10.12, out of process".
      - Update the D4-1 decision text to DLG-1.
      - Drop G1 from the five adapter streams.
      - Add the G6 note on `vehicleSpeed`.
   3. **Contracts.**
      - C-04 restated and verified (evidence: the wheel and the env record).
      - C-05 verified (the wheel hash).
      - Remove G1 from `gaps`.
      - Add G6 with a blocker row C-16.
   4. **`deployment.xdl.yaml`.** The client artifact gets its source and digest. The bridge binding's
      blockers become G3, G6, UNEXECUTED, and its limitation text changes. Line 14 of
      `component-bridge-auto.xdl.yaml` changes.
   5. **Admission.** A new field `sensorDescriptors {path, sha256}`, written by
      `build_admission_record` and checked by `verify_admission_record`.
   6. **Tests.** U-CON-02, U-ADM-03 and U-DSC-02, the re-anchored tamper tests, a synthetic
      NOT_AVAILABLE fixture, and the `sensorDescriptors` tests.
   7. **Packaging.** The wheel packages add `src/xverse_compat_carla`; `bridge_route` re-exports
      `xverse_compat_carla.timeconv.seconds_to_ns`.
   8. **`system.xdl.yaml`.** Add the `carla-simulation` time domain.

   The admission record is then rebuilt (`admit_phase4.py --platform-main 8b3d8c8e8`) and the suite
   re-run.

6. P4b-T05 re-derivation applied (2026-10-22), items 1–8 as recorded in finding 5.
   - **Inventory revision 7** in both copies (thesis and compat).
   - **Selection.** Client pin `present`, PyPI release, digest `61449e33…`, `localPath` on loop10.
     G1 dropped from five adapter streams; G6 note on `vehicleSpeed`; D4-1 decided.
   - **Contracts.** C-04 and C-05 verified, G1 removed, G6 added with blocker row C-16.
   - **Descriptors.** The bridge binding's blockers are now G3/G6/UNEXECUTED; limitation texts
     updated; `carla-simulation` time domain added.
   - **Admission.** The `sensorDescriptors` binding is validated at build and checked by
     `verify_admission_record`.
   - **Packaging.** `xverse_compat_carla` packaged; `bridge_route` re-exports `timeconv.seconds_to_ns`.
   - **Tests.** U-ADM-03, U-CON-02 and U-DSC-02 updated; tamper anchors moved to G3/G6; U-DSC-04c
     (a synthetic NOT_AVAILABLE pin keeps the G1 rule covered); U-ADM-05 (sensor descriptors
     binding and tampering).

   The admission record was rebuilt (`admit_phase4.py --platform-main 8b3d8c8e8`):
   - pins `carla-server`, `bridge-auto` and `carla-python-client` all `match`;
   - blockers RESOURCE-LIMITS-UNAPPROVED, G2–G6 and UNEXECUTED (G1 absent);
   - execution authority absent; platform lock unchanged.

   Suite: 112 passed (log `verification-20261022-a.log`), and 112 again on the final record.
   Next: independent implementation review.

7. Independent implementation review 1 (2026-10-22, on `624e6ff`): **FAIL**, with no HIGH and
   four MEDIUM findings (recorded before any repair). The reviewer confirmed:
   - the suite (112 passed) and `verify_admission_record` against `8b3d8c8e8`;
   - identical inventory copies;
   - the Python 3.10 / standard-library-only constraint;
   - re-derivation items 1–8;
   - the gates.

   | # | Sev | Finding | Planned repair |
   | --- | --- | --- | --- |
   | M1 | MEDIUM | A second `start` after the handshake is processed as a `tick`. | After the handshake, `start` is an unknown inbound message: `COMMAND` refusal, the stream continues. Add a test. |
   | M2 | MEDIUM | Commands taken by `take_pending()` are lost when `tick()` returns None or fails, so they get no ack. | Restore them to pending before any early exit, so `done` acks them `unacknowledged`. Add tests. |
   | M3 | MEDIUM | The client does not check `forbiddenModulesLoaded`. | `parse_outbound` requires the field on `done`; the client fails on a non-empty list. |
   | M4 | MEDIUM | There is no `LiveSource` test against a fake `carla` module. | Add one: settings applied and restored, shared per-tick deadline, stale snapshot means no motion, frame filtering, sensors stopped at close. |

   Repairs for the LOW findings:
   - **L1:** design amendment (thesis 028 §4/§9.10, under the author's delegation): at termination
     an already-echoed open window keeps `echoed` (truncated window); only commands never applied
     get `unacknowledged`. The no-op code is removed.
   - **L2:** non-refusal exceptions in the tick path and in ground-truth export take the `SOURCE`
     exit-3 path; invalid UTF-8 on stdin exits 2; a source construction failure exits 3 with a
     stderr line.
   - **L3:** the constructor restores settings on failure; `close()` stops the sensors; empty live
     `actors` is recorded as a limit.
   - **L4:** `TIMESTAMP` is checked before `FRAME` in `sensor_origin`.
   - **L5:** the fake image, measurement and motion objects raise on `platform_timestamp`; a canary
     test is added.
   - **L6:** the per-tick timeout is `sensorWaitMs/1000 + 5`, read from the descriptors.
   - **L7:** rule 6 phase tracking inside a tick; exact `hello` and `status` schemas.
   - **L8:** tests for the exit-2 paths, partial-motion `responded`, exit-3 termination acks, and
     V01 against the selection pin.
   - **L9:** inventory D4-1 text updated; an environment addendum records the current `py_compile`
     result.

8. Defect found by the new M4 test (2026-10-22), recorded before repair. In `LiveSource._wait`,
   once the shared per-tick deadline has expired (here because the camera was silent), the radar
   wait returns None immediately, even though that frame's radar data is already queued. So one
   silent sensor drops the others. Repair: after the deadline, drain already-queued data without
   blocking (`get_nowait`). Only the waiting is bounded per tick; data that has already arrived is
   not discarded.
