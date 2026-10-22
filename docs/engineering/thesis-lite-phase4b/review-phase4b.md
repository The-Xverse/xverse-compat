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

9. Repairs for review 1 applied (2026-10-22), as planned in findings 7 and 8:
   - **M1:** after the handshake, `start` is a `COMMAND` refusal and the stream continues.
   - **M2:** `tracker.restore()` returns the commands taken at an empty or failed tick to pending,
     so `done` acknowledges them `unacknowledged`.
   - **M3:** `parse_outbound` requires `forbiddenModulesLoaded` on `done`; the client fails on a
     non-empty list.
   - **M4:** `LiveSource` tests against a fake `carla` module (`tests/carla/test_review1.py`).
   - **Finding 8:** `LiveSource._wait` drains queued data with `get_nowait` after the deadline.
   - **L1–L9:** applied as listed in finding 7.
   - **L9 addendum:** `env-record-addendum.json` binds `env-record.json` (`b63a490e…`) and
     records `py_compile` return code 0 for `src/xverse_compat_carla` on the pinned 3.10
     interpreter.

   Verification: the full suite gives 126 passed, 39 subtests
   (`verification-20261022-b.log`). The admission record was rebuilt against platform
   `8b3d8c8e8` (`f1981d9946d2…`), and the suite was re-run after the rebuild: 126 passed. Inventory
   `0b784c71bca6…`. Next: independent review 2.

10. Independent implementation review 2 (2026-10-22, on `7677afd`): **FAIL**, with no HIGH and two
    MEDIUM findings (recorded before any repair). The reviewer confirmed:
    - the repairs for M1–M4, finding 8, L1 and L3–L9;
    - the 3.10 / standard-library-only constraint, using an in-memory compile and an AST scan;
    - re-derivation items 1–8;
    - `verify_admission_record` against `8b3d8c8e8`, with execution authority absent;
    - the bridge unchanged at `eef3f71`;
    - the suite: 126 passed.

    | # | Sev | Finding | Planned repair |
    | --- | --- | --- | --- |
    | N1 | MEDIUM | `parse_outbound` does not enforce exact item, ack, hello and refusal schemas. A ground-truth payload is accepted as an `item` with any `flowId`. | Accept only the four declared flows, and only those announced in `hello`. Closed value schemas per flow. `commandId` must be a non-empty string. `refusal.code` must be in the closed code set. `hello` must match the contract. Add a test that ground truth sent as an `item` is refused. |
    | N2 | MEDIUM | Live `--ground-truth` writes empty `actors` for every frame. This fails open, and the limit is not in the selection record. | Live mode refuses `--ground-truth` (exit 3, `SOURCE`) until actor collection exists. Design amendment §9.7 (under the author's delegation): ground-truth export is fake-source only in Phase 4b, and live collection is carried to Phase 7. Record the limit in the selection record's `groundTruth` entry. |

    Repairs for the LOW findings:
    - **L-a:** under `env -i` the interpreter runs in UTF-8 mode with `surrogateescape`. Read
      `sys.stdin.buffer` and decode strictly, so invalid UTF-8 exits 2. Add a subprocess test with
      `\xff`. This corrects finding 9, which wrongly listed L2's UTF-8 part as effective.
    - **L-b:** descriptor load, missing fixture, unwritable ground-truth path and non-integer
      fixture frames take the exit-3 path with one stderr line; `opened` moves inside the guarded
      block.
    - **L-c:** look up the carla version before building `LiveSource`.
    - **L-d:** restore settings in a `finally` around the sensor stops.
    - **L-e:** capture `accel` only after a successful emit.
    - **L-f:** run the time and identity checks before the value checks for every stream.
    - **L-g:** the 3.10 compile test compiles in memory and writes no bytecode.
    - **L-h:** the client raises `CarlaProtocolError` when there is no `hello`, and tolerates
      `BrokenPipeError` at `stop()`.
    - **L-i:** at bind time, check the ego actor and each sensor's blueprint and attributes against
      `carla-sensors.json`.

11. Repairs for review 2 applied (2026-10-22), as planned in finding 10:
    - **N1:** `parse_outbound` admits only the declared flows, and only those announced in `hello`,
      with closed value schemas per flow. It also requires a non-empty string `commandId`, a code
      from the closed code set, and an exact `hello` (`python` 3.10.12, `carlaVersion` per
      source).
    - **N2:** a live `--ground-truth` exits 3 with `SOURCE` before binding. The selection record's
      `groundTruth` interface states the limit. Thesis design §9.7 is amended, under the author's
      delegation, for N1 and N2.
    - **L-a:** `main` reads stdin through a strict UTF-8 `TextIOWrapper`. Invalid UTF-8 exits 2; it
      is tested by a subprocess under `env -i`.
    - **L-b:** descriptor, fixture and export-path failures exit 3 with one stderr line. A
      non-integer source frame takes the `SOURCE` path.
    - **L-c:** the carla version is read before binding.
    - **L-d:** `close()` restores the settings in a `finally`.
    - **L-e:** `accel` is set only after the motion item is emitted.
    - **L-f:** `builder.check` runs before the value readers.
    - **L-g:** the 3.10 compile test compiles in memory.
    - **L-h:** the client raises when there is no `hello` and tolerates `BrokenPipeError` at
      `stop()`.
    - **L-i:** the ego vehicle and the sensors' blueprints and attributes are checked at bind time;
      the fake world carries `type_id` and `attributes`.

    `tests/carla/test_review2.py` adds 31 tests. The review-1 tests were adapted: the review-1
    item fixture now carries a valid value, and an unknown actor gives `None`, which is refused
    with `SETTINGS`.

    Verification: the full suite gives 157 passed, 39 subtests (`verification-20261022-c.log`).
    The admission record was rebuilt against `8b3d8c8e8` (`3dea9416…`), and the selection record
    is `06f38edc…`. The suite was re-run after the rebuild: 157 passed. Next: independent review 3.

12. Independent implementation review 3 (2026-10-22, on `4fbc8bd`): **FAIL**, with no HIGH and one
    MEDIUM finding (recorded before any repair). The reviewer confirmed:
    - the review-2 repairs N1, N2 and L-a to L-i, each with a test;
    - exit-code and stdout/stderr discipline, check precedence and oracle separation;
    - the 3.10 / standard-library-only constraint;
    - re-derivation, and `verify_admission_record` against `8b3d8c8e8`;
    - the bridge unchanged;
    - the suite: 157 passed.

    | # | Sev | Finding | Planned repair |
    | --- | --- | --- | --- |
    | R3-M1 | MEDIUM | The client does not kill the child on rule-6 ordering, unexpected-message or pacing violations (design §9.2). A live world would stay in synchronous mode. | `_collect` and the pacing check kill the child before raising. Add a test asserting the child has exited. |
    | R3-L1 | LOW | Ack `result` is not tied to `echoFrame`. | `echoed` requires an integer `echoFrame` ≥ 0; `unacknowledged` requires null. |
    | R3-L2 | LOW | A float image width or height passes the adapter check. Overflowing motion values give `SOURCE` instead of `RANGE`. | Integer width and height, otherwise `SIZE`. Finite speed and acceleration, otherwise `RANGE`. |
    | R3-L3 | LOW | No tick-level monotonicity: a frame going back, or `elapsed_seconds` decreasing, is still served and acknowledged. | Adapter: a decreasing finite `elapsed_seconds` gives `EPISODE` (exit 3), and a non-increasing source frame gives `SOURCE` (exit 3). Client: `ticked` frames must increase. |
    | R3-L4 | LOW | Strict decoding by chunk can drop valid lines that precede an invalid one. | Decode each line of `sys.stdin.buffer` strictly. |
    | R3-L5 | LOW | `run()` called directly with `LiveSource` and an export path would write empty actors. | `LiveSource` returns `actors=None`, and the exporter refuses `None` (`SOURCE`, exit 3). |
    | R3-N | nit | A negative refusal `frame` and a null `ticked` frame are accepted; the inbound limit counts the trailing `\n`. | Tighten all three. |

13. Repairs for review 3 applied (2026-10-22), as planned in finding 12:
    - **R3-M1:** `_collect` kills the child on every `CarlaProtocolError`, and so does the pacing
      check.
    - **R3-L1:** `echoed` requires an integer `echoFrame` ≥ 0, and `unacknowledged` requires null.
    - **R3-L2:** a non-integer image width or height gives `SIZE`; overflowing motion values give
      `RANGE`.
    - **R3-L3:**
      - adapter: a non-increasing source frame gives `SOURCE` (exit 3, before the window
        opens);
      - adapter: a decreasing finite `elapsed_seconds` gives `EPISODE` (exit 3). This is checked
        after the frame's flows, so design §9.10 (earlier flows of the frame stand) is preserved;
        a first placement before the items broke that rule's test, and was moved;
      - client: `ticked` frames must increase.
    - **R3-L4:** `StrictLines` decodes each line of `sys.stdin.buffer` strictly.
    - **R3-L5:** `LiveSource` returns `actors=None`, and the exporter refuses `None`.
    - **Nits:** a refusal `frame` must be ≥ 0, a `ticked` frame must be an integer, and the
      inbound limit excludes the terminator.

    `tests/carla/test_review3.py` adds 15 tests. Verification: the full suite gives 172 passed,
    39 subtests (`verification-20261022-d.log`). The admission record was rebuilt against
    `8b3d8c8e8` (`e0df9020f030…`), and the suite was re-run after the rebuild. Next: independent review 4.

14. Independent implementation review 4 (2026-10-22, on `83873e5`): **PASS**, with no HIGH or MEDIUM
    finding. The reviewer confirmed:
    - every review-3 repair, with probes of the client kill (no zombie, no unbounded wait),
      `StrictLines` end-of-file and `stop` behaviour, and the command windows at the tick-level
      checks;
    - the whole delta: protocol, exit codes, FR-004, FR-005 and FR-006, the 3.10 constraint and
      re-derivation;
    - `verify_admission_record` against `8b3d8c8e8` (`e0df9020…`);
    - the bridge unchanged;
    - the suite: 172 passed.

    The LOW findings and nits are recorded before repair, and all will be repaired before
    acceptance (engineer decision):

    | # | Sev | Finding | Planned repair |
    | --- | --- | --- | --- |
    | R4-L1 | LOW | The tick-level EPISODE check admits a negative `elapsed_seconds`, which inverts the §9.10 order. | Compare and update only when `elapsed_seconds` ≥ 0. Add a test. |
    | R4-L2 | LOW | A non-increasing tick frame giving `SOURCE` (exit 3) is not in the normative documents. | Thesis design amendment §9.10a under the author's delegation: `FRAME` applies to sample frames; a non-increasing tick frame is `SOURCE`, exit 3. |
    | R4-L3 | LOW | Live-only exceptions from `settings()` or `close()` give exit 1 with a traceback. | Any settings-check exception gives a `SOURCE` refusal and `done(3)`. A `close()` failure writes one stderr line and gives exit 3, unless the run already returned a non-zero code. Add tests. |
    | R4-N1 | nit | A `stop()` or `wait()` timeout leaves the child running. | Kill on `TimeoutExpired`. |
    | R4-N2 | nit | `FrameData.actors` defaults to `[]`. | Default `None`. `FakeSource` passes the fixture's `actors` only when the fixture has them, and the exporter refuses `None`. |
    | R4-N3 | nit | Ignored `__pycache__` folders are left by the runs. | Remove them before acceptance. |

15. Repairs for review 4 applied (2026-10-22), as planned in finding 14:
    - **R4-L1:** the tick-level EPISODE check and the `elapsed` update require `elapsed_seconds`
      ≥ 0.
    - **R4-L2:** thesis design amendment §9.10a, under the author's delegation, records the
      tick-level frame and elapsed-time rules, the settings and close handling, and the client
      rules.
    - **R4-L3:**
      - a settings-check exception gives a `SOURCE` refusal and `done(3)`;
      - `main` always closes the source, also when `run` raises;
      - a `close()` failure writes one stderr line and turns exit 0 into exit 3.
    - **R4-N1:** `wait()` kills the child on `TimeoutExpired`, and `stop()` uses it.
    - **R4-N2:** `FrameData.actors` defaults to `None`, and `FakeSource` passes the fixture's
      `actors` only when the fixture has them.
    - **R4-N3:** the ignored `__pycache__` folders were removed after the runs.

    Five tests were added to `tests/carla/test_review3.py`. Verification: the full suite gives
    177 passed, 39 subtests (`verification-20261022-e.log`). The admission record was rebuilt
    against `8b3d8c8e8` (`eb98e1cd7dbb…`), and the suite was re-run after the rebuild. Next: a focused
    independent check of the review-4 repair diff, then acceptance.

16. Independent check 5 of the review-4 repair diff (2026-10-22, `54f56a7..d200f53`): **PASS**, with
    no HIGH or MEDIUM finding. The reviewer confirmed:
    - the close handling in `main` (closed exactly once on every path) and the settings-exception
      path;
    - the `elapsed` ≥ 0 conditions;
    - that every fixture carries `actors`, so V04 is unaffected;
    - kill on timeout;
    - that §9.10a matches the code;
    - `verify_admission_record` against `8b3d8c8e8` (`eb98e1cd…`);
    - the suite: 177 passed.

    The findings are recorded before repair. All of them will be repaired (engineer decision):

    | # | Sev | Finding | Planned repair |
    | --- | --- | --- | --- |
    | R5-L1 | LOW | After exit 2, a close failure adds a second stderr line, against rule 5. | When the run code is 2, the close failure is not written; the code stays 2. |
    | R5-N1 | nit | An exception that `run` does not catch (for example a broken stdout) exits 1 with a traceback. | `main` maps it to exit 3 with one stderr line, after closing the source. |
    | R5-N2 | nit | The exporter guard uses `isinstance`, so a bool elapsed time reaches `seconds_to_ns`. | Use `type(...) in (int, float)`. |
    | R5-N3 | nit | Kill on timeout has no test. | Add one with a stubbed process. |
    | R5-N4 | nit | Python 3.13 bytecode was left by the admission run. | Removed. Run `admit_phase4.py` with `-B` from now on. |

17. Repairs for check 5 applied (2026-10-22), as planned in finding 16:
    - **R5-L1:** `_close(quiet=…)` writes nothing after exit 2.
    - **R5-N1:** an exception that `run` does not catch closes the source quietly and exits 3 with
      one stderr line.
    - **R5-N2:** the exporter guard uses a `type` check.
    - **R5-N3:** a kill-on-timeout test was added.
    - **R5-N4:** the bytecode was removed, and `admit_phase4.py` now runs with `-B`.

    Thesis design §9.10a is extended accordingly. Verification: the full suite gives 180 passed,
    39 subtests (`verification-20261022-f.log`). The admission record was rebuilt against
    `8b3d8c8e8` (`35a2c24c0919…`), and the suite was re-run after the rebuild.

18. Independent check 6 of the check-5 repair diff (2026-10-22, `d200f53..111b6aa`): **FAIL**, with
    one MEDIUM finding (recorded before repair). The reviewer confirmed:
    - the source is closed once on every path, and `KeyboardInterrupt` and `SystemExit` still
      propagate;
    - the exporter type check;
    - that the new tests exercise their behaviour;
    - `verify_admission_record` (`35a2c24c…`);
    - the suite: 180 passed.

    | # | Sev | Finding | Planned repair |
    | --- | --- | --- | --- |
    | R6-M1 | MEDIUM | A broken stdout makes the real adapter process exit 120 with three stderr lines: the failed write stays buffered, and the interpreter's shutdown flush fails again. The R5-N1 test patched `run` in process, so it could not see this. | In that path, `dup2` `os.devnull` onto stdout's descriptor before returning 3. Add a subprocess test with the stdout reader closed, asserting exit 3 and one stderr line. |
    | R6-L1 | LOW | After `run` returns 3 with a `SOURCE` line, a close failure adds a second line. Rule 5 allows this, but it is undocumented. | §9.10a states that the single-line rule binds exit 2, and that exit 3 may carry a close line. |
    | R6-N1 | nit | Finding 17 says `admit_phase4.py` "now runs with `-B`". That is a procedure, not code. | Correction: the procedure is to invoke it as `python -B`; the script is unchanged. |
