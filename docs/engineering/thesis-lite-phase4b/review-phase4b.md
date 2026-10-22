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
