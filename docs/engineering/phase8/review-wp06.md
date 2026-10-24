# Review log: Phase 8 WP-06, camera raw-frame side channel (xverse-compat)

Candidate `candidate/phase8-wp06-image-path-20261024`, base main `855878a` (WP-08 merged). Specification:
thesis `specs/002-assured-aeb` rev 3g:
- `implementation-plan.md` WP-06 (ED-03, GA-03) and K-8, K-10, K-12;
- `decisions.md` §J (camera corruption in the U2 sensor-model stage; the U3 self-checks see the corrupted
  images, AD-18, AD-31) and §K (the owned Unix-socket hub in U2);
- `design/wp12-xdl-topology.md` F01 (`camera-raw` on the adapter link, with the raw frame on the
  run-scoped side channel);
- thesis `028` D4b-2 (pixel bytes stay out of evidence; only a SHA-256 and metadata).
Decided under the author's delegation of 2026-10-24, flagged for the author's review. Findings are recorded
before repairs. The maturity is an engineering increment verified offline: not M1, not AEB evidence, live
behaviour unverified (E8-3a).

## Findings

1. **Design record: the camera raw-frame side channel (2026-10-24 11:39:25, before any code).**
   - **Starting point (verified at `855878a`).**
     - `sensors.camera_value` (33–43) emits `{width, height, fovDeg, rawSha256, rawLength}` from CARLA's
       BGRA `raw_data` (4·w·h bytes). No pixel bytes cross the `carla-items` boundary (FR-002).
     - `protocol._frame_items` emits the camera item first in `FLOWS` order.
     - `FakeSource` builds `raw_data` from the fixture's `rawLength` and `rawFill`.
     - Protocol 2 connects the adapter to a platform-side Unix socket (DLG-8).
   - **Transport: a second Unix stream socket, not a shared-memory ring.**
     - **Reuse.** DLG-8 already accepted a Unix-socket adapter link, and WP-12 §2.1 chose a Unix-socket
       star through U2, so no new transport class is introduced.
     - **Ordering and lifecycle.** A stream is ordered, and end-of-file marks the adapter's end. A ring file
       would need stale-file handling and cleanup.
     - **No cross-process memory ordering needed.** A Python shared-memory ring needs a seqlock across two
       interpreters, without atomics in the standard library. The hash check would catch torn frames but not
       prevent them.
     - **Cost.** At the K-10 sensor format (800 × 600 BGRA, 1 920 000 bytes) and the 0.05 s step this is
       about 38 MB/s, two copies, well within a local socket. The host cost is measured with D-4c.
     - As for the link, U2 listens, with mode 0600 under umask 0177, and the adapter connects with retry.
       A Unix socket path is limited to 107 bytes, so the path is chosen as the link's is (R-4).
   - **Wire format `xverse-compat.camera-frames/1`.** One JSON header line (at most the protocol's 65 536 bytes,
     strict UTF-8, no NaN), followed for `frame` records by exactly `rawLength` raw bytes:
     - `hello`: `protocol`, `format` (the declared frame-format record) and `formatSha256`;
     - `frame`: `frame` (the CARLA frame of the camera item), `sequence` (per offered frame, dropped ones
       included), `rawSha256`, `rawLength`, `dropped` (cumulative adapter drops);
     - `end`: `offered`, `sent`, `dropped`, `error`.
   - **Frame format (AD-02 input fidelity; a protocol value).** A record
     `xverse-compat.camera-frame-format/1` with exactly `schema`, `width`, `height` and `encoding`. It has
     **no defaults**, and no format file is shipped: the values belong to AD-02 and the freeze (AD-27).
     - `encoding` must be `bgra8`, CARLA's `raw_data` layout. The 3.10 adapter does not transcode.
     - The adapter refuses to start the side channel when `--frames` is given without `--frame-format` (an
       argument error, **exit 2**; corrected by finding 5, it read "exit 3"), and before the protocol with exit 3
       when the record is malformed or when its width and height differ from the camera descriptor.
     - The receiver refuses a `hello` whose format or `formatSha256` differs from its own declared record,
       and refuses any `rawLength` other than `4·width·height`.
   - **Adapter side** (`xverse_compat_carla/frames.py`, CPython 3.10, standard library only; never imports
     `xverse_compat`):
     - `FramePublisher` offers each emitted camera frame **before** its item is sent;
     - it holds a bounded queue of depth 2, serviced by one writer thread doing `sendall`. The tick path
       never blocks. The basis for depth 2: U2 consumes a step's frame before it requests the next tick
       (WP-12 lockstep), so at most one frame is outstanding; it is an engineering constant, not a protocol
       value;
     - a full queue drops the **new** frame and counts it (`dropped`, `sequence` advanced). After a socket
       error the writer stops and every later offer counts as dropped. The `end` record and a close summary
       give `offered = sent + dropped`;
     - it is enabled only by `--frames unix:<path> --frame-format <file>` (protocol 2). Without those options
       the adapter is byte-for-byte unchanged on the wire, so the Phase 7 and S1 harness and tonight's soak
       are not affected.
   - **U2 side** (`xverse_compat/live/frames.py`, CPython 3.13):
     - `FrameReceiver` listens and accepts with a bound, then reads each record with one reader thread. Its
       buffer is bounded at 2 frames. When the buffer is full the reader waits, so backpressure flows
       through the kernel buffer to the adapter's queue, where drops are counted at one point;
     - `take(item, wait_s)` takes a camera item from the adapter link and returns a `FrameResult`. Its
       `status` is one of:
       - `verified`: the bytes' SHA-256 equals the **item's** `rawSha256` and their length equals
         `rawLength`; the bytes are returned, in memory only;
       - `mismatch`: no bytes are returned;
       - `dropped`: the adapter reported the drop through `sequence` and `dropped`;
       - `missing`: the frame did not arrive within the bounded `wait_s`;
     - buffered frames older than the item are discarded as `skipped`. A sequence gap not covered by the
       adapter's `dropped` counter is counted as `lost` (a protocol fault);
     - `summary()` and `reconcile()` return counters and hashes only: `offered = sent + dropped`,
       `received = sent`, `lost = 0`, and every item taken is accounted.
   - **No pixel bytes in evidence (D4b-2).** The items and flows keep exactly the five K-8 members. The
     receiver's records (`FrameResult.record()`, `summary`, `reconcile`) carry only frame numbers, hashes,
     lengths, statuses and counters. Bytes are handed only to the in-process consumer (the U2 imaging stage,
     GA-36). Nothing on the side channel is written to disk.
   - **Tests (offline).**
     - In-process publisher and receiver: verified frames; a tampered frame gives `mismatch`; queue-full
       drops are accounted and reconciled; a failed socket is accounted; a format mismatch and an undeclared
       format are refused; the bounded buffer; `skipped`; `missing` after the bounded wait.
     - End to end: the pinned 3.10 adapter (`require_env`, as the Phase 7 subprocess tests) on a fake source
       with `--frames`, against `SocketAdapterLink` and `FrameReceiver`. Each tick's camera item is
       verified, and the adapter's `forbiddenModulesLoaded` is `[]`.
     - **No pixels in evidence:** every protocol line, item value and receiver record of that run is JSON
       with no line above 1 KiB, while a frame is 1.92 MB, and no record holds bytes.
     - Unchanged: without `--frames` the hello, items and statuses are identical to a base run.
   - **Out of scope.** The corruption stage (GA-36) and the U3 self-checks (FR-034) are blueprint increments.
     The U2 entry point and loop integration belong to WP-12. Live use is under E8-3a.
2. **Implementation of finding 1 (2026-10-24 11:48:04).**
   - **Change.**
     - `src/xverse_compat_carla/frames.py` (new; 3.10, standard library only): `load_format`,
       `format_sha256`, `FramePublisher` (depth-2 queue, one writer thread, `offer` never blocks,
       `close` sends `end`).
     - `protocol.py`: `run(..., frames=None)` and `_frame_items(..., frames)` offer the camera frame before
       its item is sent. `main.py`: `--frames unix:<path>` and `--frame-format <file>`, both required
       together and only with protocol 2. The format is validated, and must equal the descriptor geometry,
       before the protocol (exit 3). The publisher connects after the link and before readiness, and is
       closed on the normal and exception paths.
     - `src/xverse_compat/live/frames.py` (new; 3.13): `FrameReceiver` (`start`, `take`, `summary`,
       `reconcile`, `close`), `FrameResult` and `FrameChannelError`.
     - `FLOWS`, `camera_value`, the item schema and `carla_client` are unchanged.
   - **Defects found by the new tests before commit, and repaired in this commit.**
     - (a) **Regression, caught by `test_wp06_without_the_side_channel_the_link_is_unchanged`.** The first
       edit of `main.py` attached the stdio `else:` branch to `if args.frames` instead of
       `if args.connect`. Without `--frames`, protocol 2 then read standard input and ended with `done`
       before the first tick. Repaired by placing the publisher block after the link `if/else`. The test
       compares every link message with and without the side channel.
     - (b) `FrameReceiver.close` did not release the connection while the reader's `makefile` still held
       the descriptor. The adapter therefore saw no error, and counted queue-full drops instead. Repaired with
       `shutdown(SHUT_RDWR)` and by closing the reader file.
     - (c) A design consequence, now explicit. A frame that the adapter drops last is announced only by the
       next frame header or by `end`, so until then its `take` times out as `missing`. `reconcile`
       therefore checks `dropped + missing + lost == end.dropped`, with no unaccounted sequence gap (R-1).
   - **Tests.** `tests/live/test_phase8_frames.py`: 33 tests.
     - Format: 10 malformed or undeclared records refused on both sides; the shared protocol constants; the
       3.10 module's standard-library imports.
     - In process, over a real Unix socket:
       - verified frames, with the bytes returned and absent from `record()`;
       - a mismatch with no bytes returned;
       - backpressure with 1.92 MB frames: 12 offers return in under 2 s, the drops are counted at the
         adapter, every take is `verified`, `dropped` or `missing`, and `reconcile` is ok;
       - a failed socket: an error, and `offered = sent + dropped`;
       - a hello with another format refused; bytes of the wrong length refused;
       - `missing` after the bound, `skipped`, and the buffer holding exactly 2 while a third frame waits;
       - an unreported sequence gap: `lost`, and `reconcile` not ok;
       - four protocol violations: `failed`, and `reconcile` not ok.
     - End to end with the pinned 3.10 adapter on the fake `nominal` source:
       - all 4 camera items verified (fill bytes 0 to 3), with `end` reporting `offered 4, sent 4, dropped 0`
         and `forbiddenModulesLoaded` `[]`;
       - **no pixels in evidence:** camera values have exactly the 5 K-8 members, every link message, take
         record and reconciliation serialises below 1 KiB against a 1 920 000-byte frame, and no record holds
         bytes;
       - **unchanged link:** identical messages with and without `--frames`;
       - argument refusals (exit 2); invalid and mismatching formats refused before the protocol (exit 3).
     - The file was run 4 times with no failure.
   - **Mutation checks (not committed; restored).**
     - no hash comparison in `take`: 1 test fails;
     - a blocking `put` in `offer`: the backpressure test fails (the tick path blocks);
     - queue-full drops not counted: 2 tests fail.
   - **Suite.** 410 passed, 39 subtests (base `855878a`: 377).
   - **Residuals.**
     - R-1. A frame dropped by the adapter is known to U2 only from the next header or from `end`. Under the
       WP-12 lockstep, U2's `take` returns `missing` after its bounded wait, and the run record must treat a
       `missing` camera frame as a camera-input event. Its effect on run validity, and the bound (D-4c), are
       WP-12 and FR-042 items.
     - R-2. The live path (`LiveSource` with `--frames`) is not exercised offline beyond the shared
       `_frame_items` code: live CARLA `raw_data`, the host cost at 38 MB/s and kernel-buffer behaviour are
       E8-3a and D-4c items.
     - R-3. No frame-format file is shipped. AD-02 fixes the input fidelity and therefore both the camera
       descriptor and this record; the freeze binds the format's digest. The 3.10 adapter does not resize or
       transcode, so a model input resolution other than the sensor's is a U2 or U4 stage, outside this
       channel.
     - R-4. Socket paths must fit the 107-byte `sun_path` limit, as for the link (`/run/user/<uid>/…` in the
       tests). WP-12 chooses the run-scoped path.
     - R-5. Out of scope: the U2 entry point and loop integration (WP-12), the corruption stage (GA-36,
       blueprint), the U3 self-checks (FR-034, blueprint), and the contract note
       `docs/engineering/thesis-lite-phase7-live/carla-items-2.md`. That note still describes protocol 2
       without the side channel; an amendment is proposed with the blueprint increment.
     - R-6. The depth-2 queue and the 2-frame buffer are engineering constants based on the lockstep; they
       are not measured.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 11:52:20).** Reviewer: an independent Claude agent that did
   not write the increment. Scope: `430cfd1` and `56601a0` on `855878a`. **Verdict: PASS WITH NOTES.** Nothing
   blocks the merge. M1 must be repaired before the first live use with `--frames` (E8-3a) or the WP-12 U2
   integration.
   - **What was checked, and the result.**
     - **Suite.** The offline compat suite, with the command given: **410 passed, 39 subtests** in 24 s. The
       worktree stayed clean.
     - **The unchanged link, verified independently against the base.**
       - **Method.** I extracted `855878a:src` and `HEAD:src` with `git archive` into a scratch directory, and ran
         each with the pinned 3.10 interpreter on the fake `nominal` source, without `--frames`.
       - **Modes.** Four, with the same inbound bytes: protocol 1 on stdio, protocol 2 on stdio, protocol 2 with
         `--connect`, and protocol 2 with `--connect --marker`.
       - **Result.** The exit codes and the stdout, stderr and link bytes are **byte-identical** in all four.
       - **Why this matters.** The in-repo test `test_wp06_without_the_side_channel_the_link_is_unchanged`
         (`tests/live/test_phase8_frames.py:284-287`) compares the candidate with and without `--frames`, and only
         on a socket link. It is not a comparison with the base. The stdio branch, where defect 2(a) lived, is
         covered only by this external check (L5).
       - **Code reading agrees.** Without `--frames`, the only new executed code is the argument checks and
         `frame_format = None` (`main.py:76-79,86`). `frames=None` leaves `_frame_items` on its base path
         (`protocol.py:125-126`), and the publisher block sits after the link `if/else` (`main.py:133-142`).
     - **3.10 isolation.** `xverse_compat_carla/frames.py` imports only `hashlib`, `json`, `queue` and
       `threading` (`frames.py:12-15`), and `main.py` imports it lazily. `FORBIDDEN` is unchanged
       (`protocol.py:32`), and the end-to-end run reports `forbiddenModulesLoaded == []`.
     - **Transport choice.** A second Unix stream socket is sound. It reuses the DLG-8 link pattern (0600 under
       umask 0177), keeps ordering and EOF semantics, and avoids an interpreter-to-interpreter seqlock. A
       shared-memory ring would add stale-file handling and torn-read handling for no measured gain.
     - **Publisher.** `offer` never blocks on the socket: `put_nowait` is used, and a full queue drops the new
       frame (`frames.py:110-118`). The depth is bounded, the drops are counted, and the `sequence`/`dropped`
       header lets the receiver attribute gaps. `offered = sent + dropped` holds on every ordinary path; L1 is the
       exception.
     - **Receiver.**
       - **Backpressure.** The reader waits on the condition while the buffer is full (`live/frames.py:183-184`),
         so at most capacity + 1 frames are in memory.
       - **Verification.** It compares against the **item's** `rawSha256` and length (`:214`), not the header's.
         Wrong lengths are refused (`:168-169`), and counters running backwards are refused (`:175-176`).
       - **Soundness of `reconcile`.** Under the design rule that every camera item is taken once and in order,
         each adapter drop yields exactly one `dropped` or `missing` take. A frame that was sent but arrived late
         yields `missing` and then `skipped`. So `absent == end.dropped` with `received == sent` cannot hide a
         late or lost frame: it fails. The trailing-drop rule (2(c)) is consistent with this.
     - **No defaults in the format record.** Both `load_format` copies agree: exact members, the schema, positive
       non-bool `int` dimensions and `bgra8` only (`frames.py:29-41`; `live/frames.py:43-50`). The geometry must
       equal the descriptor before the protocol starts (`main.py:86-92`).
     - **No pixels in evidence.** The items keep the five K-8 members. `record()`, `summary()` and `reconcile()`
       hold no bytes, and nothing is written to disk.
   - **Issues.**
     - **M1 (MEDIUM; does not block the merge; blocks live use with `--frames`): `publisher.close()` runs before
       the source is closed, and can take twice its bound.**
       - **The delay.** `close` waits up to `timeout_s` for `put(None)` and then up to `timeout_s` again in
         `join` (`frames.py:123-127`). On the normal path it is called with the default 5 s (`main.py:163`),
         **before** `_close(source)` (`main.py:164`). For `LiveSource`, `_close(source)` destroys the owned CARLA
         actors (`sources.py:227-250`).
       - **When it happens.** If U2 keeps the socket open but stops taking frames, for example on a WP-12 stop or
         failure path, the adapter waits up to 10 s before cleaning up the actors. No SIGTERM handler is
         installed until the linger loop (`main.py:46-49`). A Maestro stop inside that window (TERM grace 0.6 s,
         stop action 5 s) therefore kills the process before the actors are destroyed.
       - **Measured in a scratch run.** With an unread socket pair and four 1.92 MB frames, `close(timeout_s=1.0)`
         returned after **2.0 s** with `error = "writer did not finish within the close bound"`.
       - **Repair.**
         - Close the source first, or bound `close` with one shared deadline that is shorter than the stop
           budget.
         - Shut down the socket on close (`SHUT_WR` after `end`, `SHUT_RDWR` on timeout). This also covers
           `--linger`, where the frames socket otherwise stays open.
     - **L1 (LOW): a failure race can break `offered = sent + dropped` in the close summary.**
       - **The race.** `offer` reads `failed` under the lock (`frames.py:106`), but puts the frame after releasing
         it (`:112`). If the writer fails and `_drain`s (`:80-85`) in between, the frame stays queued with no
         writer, and it is never counted as sent or dropped. `close` recomputes `dropped` only when the thread is
         alive (`:131`).
       - **Forced interleaving.** In a scratch run it gave `{'offered': 2, 'sent': 0, 'dropped': 1}`.
       - **Impact.** It is limited, because `end` is not sent after an error and `main` discards the summary.
       - **Repair.** Drain the queue in `close`, or always set `dropped = offered - sent` once the writer has
         ended or failed.
     - **L2 (LOW): the adapter-side accounting is never recorded.** `main.py:154,163` discard the dict that
       `close` returns. When the channel fails, the adapter's `offered`, `sent`, `dropped` and `error` are
       therefore lost, and U2 sees only `endReceived: false`. One stderr summary line would keep finding 1's claim
       ("a close summary gives offered = sent + dropped").
     - **L3 (LOW): the receiver's hello read has no time bound.**
       - `start` clears the socket timeout (`settimeout(None)`, `live/frames.py:119`) before reading `hello`
         (`:121`). A peer that connects but never sends a full line blocks `start` indefinitely. The accept is
         bounded; the handshake is not.
       - Maestro's action timeouts still bound U2 from outside. Apply the remaining accept bound to the hello
         read.
     - **L4 (LOW; robustness and hardening).**
       - The receiver does not refuse a non-increasing `frame` number. A repeated frame would overwrite
         `_buffer[frame]` (`live/frames.py:187`) without being counted.
       - `load_format` puts no upper bound on `width·height`, on either side. `rawLength` follows the trusted,
         declared record, so this is defence in depth only.
       - `dataclasses.asdict(FrameResult)` would include `data`. The U2 integration must use `record()`.
       - The tick path copies and hashes each 1.92 MB frame a second time, after `camera_value`
         (`protocol.py:126`; `sensors.py:40-43`), and `_writer` concatenates header and pixels before sending
         (`frames.py:77`). These are D-4c host-cost items; R-2 should name them.
     - **L5 (LOW; tests and records).**
       - **The unchanged-link test.** It compares the candidate with itself, on the socket link only. Adding a
         stdio protocol 1 and 2 case without `--frames` against a stored golden output from the base would make
         the regression of 2(a) directly testable in-repo.
       - **An exit code in finding 1.** It says `--frames` without `--frame-format` exits 3 before the protocol.
         The implementation and the tests exit 2 (an argument error, `main.py:76-77`; `test_phase8_frames.py:290-301`),
         as finding 2 states.
   - **Residuals R-1 to R-6.** They are honest and correctly scoped. Proposed additions:
     - **R-7.** The order and bound of the adapter close (M1), to repair before E8-3a.
     - **R-8.** The unbounded hello read (L3) and the dropped close summary (L2).
     - **R-2** should name the extra per-tick copy and hash (L4).
4. **Disposition of finding 3 (2026-10-24 11:53:56; decided by the coordinator under the author's delegation of
   2026-10-24, flagged for the author's review). Repair before the merge. Recorded before repair.**
   - **M1.** Close the CARLA source and its owned actors before the frame publisher (`main.py` 163–164).
     Bound `publisher.close` to one total timeout (`frames.py` 123–127), with a socket `shutdown` so that a
     stalled reader cannot extend it. Add a test with a non-reading receiver showing that the close takes no
     longer than the timeout and that the source is closed first.
   - **L1.** Race-free close accounting, so that `offered = sent + dropped` holds in the summary, with a test
     that forces the timing.
   - **L2.** Log the close summary through the adapter's existing result or stderr path.
   - **L3.** Bound the receiver's `hello` read with a timeout.
   - **L4.**
     - Refuse repeated and non-increasing frame numbers.
     - Give width and height a tool upper limit: a refusal bound, recorded as such, not a protocol value.
     - Make `FrameResult` unable to dump pixel bytes through `asdict`.
     - Record under R-2 the extra copy and hash of each frame on the tick path.
   - **L5.** Add a base-golden test comparing the stdio protocol 1 and 2 output with fixtures captured from base
     `855878a`. Correct "exit 3" to "exit 2" in finding 1.
   - **Residuals.** Add R-7 (M1, repaired here) and R-8 (L2, L3).
5. **Repair of finding 4 (2026-10-24 12:02:02).**
   - **M1, close order and bound.**
     - `main._finish(source, publisher, quiet, log)` now closes the source, and with it the owned CARLA
       actors, first. Only then does it close the publisher, with `FRAMES_CLOSE_S = 1.0`: an engineering
       constant inside Maestro's 5 s stop action, which now only delays the process exit. The normal, exception
       and `BaseException` paths all use it.
     - `FramePublisher.close(timeout_s)` uses **one deadline** for the queue put, the writer join and the
       `end` record. It always shuts the socket down (`SHUT_RDWR`) and closes it, so a stalled reader cannot
       extend the close, and the `--linger` case no longer keeps the frames socket open.
     - Tests:
       - `test_wp06_m1_close_is_bounded_by_one_timeout_with_a_stalled_reader`: a peer that never reads;
         `close(1.0)` returns within 1.2 s, with the bound error and balanced accounting (before the repair,
         about 2 s);
       - `test_wp06_m1_the_source_and_its_actors_close_before_the_publisher`: the recorded order is source,
         then publisher, within `FRAMES_CLOSE_S` + 0.3 s.
     - Probe: restoring the separate put and join timeouts fails the bound test.
   - **L1, race-free accounting.** `close` takes one final snapshot under the lock, with
     `dropped = offered − sent` always. After the snapshot the writer cannot change a counter, and `offer`
     refuses. Test `test_wp06_l1_..._fails_between_the_check_and_the_put` forces the interleaving through a
     racy queue installed at construction: offer 2 passes its `failed` check, the writer then fails and
     drains an empty queue, and offer 2's put lands with no writer. The counter then reads 1, and the summary
     reads `offered 2, sent 0, dropped 2`. Probe: with the old rule (recompute only while the writer is
     alive) the test fails with `dropped 1`.
     - The first version of this test replaced the queue after the writer had started, so it did not force the
       race: it passed under the probe. That was found by the probe and rewritten before commit.
   - **L2.** With `log`, `_finish` writes one stderr line, `XVERSE-COMPAT-CARLA-FRAMES: {...}`, with
     `offered`, `sent`, `dropped` and `error`. It logs on exit 0 and on the exit-3 exception path. Exit 2
     keeps its single stderr line, so it does not log there. Tested in the M1 order test.
   - **L3.** `FrameReceiver.start` uses one deadline for the accept and the `hello` read. A peer that connects
     and sends nothing is refused with `FrameChannelError` ("no valid hello within …"), and the receiver
     closes. Test: refused within 1 s at a 0.5 s bound.
   - **L4.**
     - A repeated or decreasing frame number stops the channel ("does not increase").
     - `MAX_DIMENSION = 8192` bounds width and height on both sides. It is a **tool refusal bound, not a
       protocol value**; the declared AD-02 format is always inside it.
     - `FrameResult` keeps the pixels outside its dataclass fields: a private attribute, set by
       `with_pixels` and read by `pixels()` or `data`. So `dataclasses.asdict`, `repr` and `record()`
       cannot contain them. Tested.
     - The per-tick copy and hash are recorded under R-2 below.
   - **L5.**
     - `tests/live/fixtures/wp06-golden-855878a-p{1,2}.jsonl` hold the stdout of the **base** `855878a`
       adapter. It was run from a `git archive` export in the scratchpad, deleted afterwards, over stdio on the
       fake `nominal` source, with the input scripts `wp06-golden-input-p{1,2}.jsonl` (start, one command,
       five ticks, stop): 23 lines each, exit 0.
     - `test_wp06_l5_stdio_output_equals_the_base_golden[1,2]` runs the candidate on the same input and
       requires byte-identical stdout and an empty stderr. Probe: reintroducing a misplaced stdio branch fails
       the golden and unchanged-link tests.
     - Finding 1's exit code is corrected in place: an argument error exits 2.
   - **Other test change.** The failed-socket test failed once in 15 runs. Offers made before the writer has
     detected the dead peer are still queued, and counted as dropped by the drain, so the test now waits for
     `publisher.error` before asserting refusals. This was a test race, not a code defect.
   - **Tests.** `tests/live/test_phase8_frames.py`: 42 tests (33 before; 9 new). The file was run 8 times
     after the repair with no failure.
   - **Suite.** 419 passed, 39 subtests (finding 2: 410; base `855878a`: 377).
   - **Residuals, updated.**
     - R-2, amended (L4): the tick path makes a second copy and SHA-256 of each 1 920 000-byte frame after
       `camera_value` (`protocol.py` `bytes(fd.camera.raw_data)`), and the writer concatenates the header
       and the pixels before `sendall`. These are D-4c host-cost items.
     - R-7 (M1, repaired here): the source and its actors now close before the publisher, and the publisher's
       close is bounded at 1 s in total.
     - R-8 (L2 and L3, repaired here): the adapter's close summary is logged on stderr, and the receiver's
       `hello` read is bounded.
   - **Status.** Candidate for a focused re-review and the author's acceptance. Not accepted, not merged, not
     pushed.
