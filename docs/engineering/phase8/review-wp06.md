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
