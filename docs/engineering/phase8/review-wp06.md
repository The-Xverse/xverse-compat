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
     - The adapter refuses to start the side channel (exit 3 before the protocol) when `--frames` is given
       without `--frame-format`, when the record is malformed, or when its width and height differ from the
       camera descriptor.
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
