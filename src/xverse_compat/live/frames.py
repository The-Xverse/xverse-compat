"""Camera raw-frame side channel, U2 side (Phase 8 WP-06; design record ``docs/engineering/phase8/review-wp06.md``).

``FrameReceiver`` listens on a Unix socket (mode 0600) for the adapter's ``xverse-compat.camera-frames/1`` records
and verifies each frame against the camera item's own ``rawSha256`` from the ``carla-items`` link (``take``). Its
buffer holds at most ``capacity`` frames: when full, the reader waits, so backpressure reaches the adapter's bounded
queue, where drops are counted. Every taken item ends in one status (``verified``, ``mismatch``, ``dropped``,
``lost``, ``missing`` or ``failed``), and ``reconcile`` checks that nothing was lost silently.

Pixel bytes stay out of evidence (D4b-2): ``FrameResult.record``, ``summary`` and ``reconcile`` carry frame numbers,
hashes, lengths, statuses and counters only. The bytes are handed to the in-process consumer and never written.
The declared frame format is a protocol value (AD-02): there is no default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

PROTOCOL = "xverse-compat.camera-frames/1"
FORMAT_SCHEMA = "xverse-compat.camera-frame-format/1"
FORMAT_MEMBERS = {"schema", "width", "height", "encoding"}
ENCODINGS = {"bgra8": 4}
CAPACITY = 2
MAX_LINE = 65536
STATUSES = ("verified", "mismatch", "dropped", "lost", "missing", "failed")
HEX = frozenset("0123456789abcdef")


class FrameChannelError(RuntimeError):
    """The side channel violated its protocol or format; the receiver stops reading (fail-closed)."""


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_format(record) -> dict:
    """Validate a declared frame-format record (AD-02 input fidelity; no defaults). Raise ``ValueError``."""

    if not isinstance(record, dict) or set(record) != FORMAT_MEMBERS or record["schema"] != FORMAT_SCHEMA:
        raise ValueError(f"frame format must be exactly {sorted(FORMAT_MEMBERS)} with schema {FORMAT_SCHEMA}")
    if any(type(record[k]) is not int or record[k] <= 0 for k in ("width", "height")) or record["encoding"] not in ENCODINGS:
        raise ValueError("frame format needs positive int width and height and a supported encoding")
    return dict(record)


def _reject_constant(name):
    raise FrameChannelError(f"non-finite JSON constant {name}")


def _sha(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


@dataclass
class FrameResult:
    """The outcome of one ``take``; ``data`` is never part of ``record()``."""

    status: str
    frame: int
    rawSha256: str
    rawLength: int
    actualSha256: str | None = None
    reason: str | None = None
    data: bytes | None = field(default=None, repr=False)

    def record(self) -> dict:
        return {"status": self.status, "frame": self.frame, "rawSha256": self.rawSha256, "rawLength": self.rawLength,
                "actualSha256": self.actualSha256, "reason": self.reason}


class FrameReceiver:
    """Platform (U2) side of the side channel: listen, accept, read with a bounded buffer, verify on ``take``."""

    def __init__(self, socket_path, fmt: dict, *, capacity: int = CAPACITY) -> None:
        self.fmt = load_format(fmt)
        self.length = self.fmt["width"] * self.fmt["height"] * ENCODINGS[self.fmt["encoding"]]
        self.format_sha256 = hashlib.sha256(_canonical(self.fmt)).hexdigest()
        self.capacity = capacity
        self.path = Path(socket_path)
        if self.path.is_socket():
            self.path.unlink()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous = os.umask(0o177)  # created 0600, with no window of wider access (as SocketAdapterLink)
        try:
            self._listener.bind(str(self.path))
        finally:
            os.umask(previous)
        self._listener.listen(1)
        self._conn = None
        self._cond = threading.Condition()
        self._buffer = {}  # frame -> (sequence, actual sha256, bytes); at most ``capacity`` entries
        self._closed = False
        self.error = None
        self.eof = False
        self.end = None
        self.hello = None
        self.counts = dict.fromkeys(STATUSES, 0)
        self.counts.update(received=0, skipped=0, headerMismatch=0, taken=0, gapUnaccounted=0)
        self._last_sequence = -1
        self._last_dropped = 0
        self._pending_drops = 0  # adapter-reported drops not yet attributed to a taken item
        self._latest_frame = None

    def start(self, accept_timeout_s: float) -> dict:
        """Accept the adapter's connection within ``accept_timeout_s`` and read ``hello``; return it."""

        self._listener.settimeout(accept_timeout_s)
        try:
            self._conn, _ = self._listener.accept()
        except OSError as error:
            raise FrameChannelError(f"adapter frames channel did not connect: {error}") from error
        self._conn.settimeout(None)
        self._reader = self._conn.makefile("rb")
        hello = self._header()
        if (hello.get("type") != "hello" or hello.get("protocol") != PROTOCOL or hello.get("format") != self.fmt
                or hello.get("formatSha256") != self.format_sha256 or set(hello) != {"type", "protocol", "format", "formatSha256"}):
            self.close()
            raise FrameChannelError("hello differs from the declared protocol or frame format")
        self.hello = hello
        threading.Thread(target=self._read_loop, name="camera-frames-reader", daemon=True).start()
        return hello

    def _header(self) -> dict:
        line = self._reader.readline(MAX_LINE + 1)
        if not line:
            raise EOFError
        if len(line) > MAX_LINE or not line.endswith(b"\n"):
            raise FrameChannelError("header line exceeds the limit or is truncated")
        message = json.loads(line.decode("utf-8", errors="strict"), parse_constant=_reject_constant)
        if not isinstance(message, dict):
            raise FrameChannelError("header is not an object")
        return message

    def _read_loop(self) -> None:
        try:
            while True:
                try:
                    header = self._header()
                except EOFError:
                    with self._cond:
                        self.eof = True
                        self._cond.notify_all()
                    return
                if header.get("type") == "end":
                    if set(header) != {"type", "offered", "sent", "dropped", "error"}:
                        raise FrameChannelError("malformed end record")
                    if not all(type(header[k]) is int and header[k] >= 0 for k in ("offered", "sent", "dropped")):
                        raise FrameChannelError("malformed end record")
                    with self._cond:
                        self.end = header
                        # drops after the last received frame are reported only here
                        self._pending_drops += max(0, header["dropped"] - self._last_dropped)
                        self._last_dropped = max(self._last_dropped, header["dropped"])
                        self._cond.notify_all()
                    continue
                if header.get("type") != "frame" or set(header) != {"type", "frame", "sequence", "rawSha256", "rawLength", "dropped"}:
                    raise FrameChannelError("unknown or malformed record")
                frame, sequence, dropped, length = header["frame"], header["sequence"], header["dropped"], header["rawLength"]
                if not all(type(v) is int and v >= 0 for v in (frame, sequence, dropped, length)) or not _sha(header["rawSha256"]):
                    raise FrameChannelError("frame header fields are invalid")
                if length != self.length:
                    raise FrameChannelError(f"rawLength {length} differs from the declared format's {self.length}")
                data = self._reader.read(length)
                if len(data) != length:
                    raise FrameChannelError("frame bytes truncated")
                actual = hashlib.sha256(data).hexdigest()
                with self._cond:
                    if sequence <= self._last_sequence or dropped < self._last_dropped:
                        raise FrameChannelError("sequence or drop counter went backwards")
                    gap, reported = sequence - self._last_sequence - 1, dropped - self._last_dropped
                    self._pending_drops += min(gap, reported)
                    self.counts["gapUnaccounted"] += max(0, gap - reported)  # a gap the adapter did not account for
                    self._last_sequence, self._last_dropped = sequence, dropped
                    self.counts["received"] += 1
                    self.counts["headerMismatch"] += actual != header["rawSha256"]
                    while len(self._buffer) >= self.capacity and not self._closed:
                        self._cond.wait()  # backpressure: stop reading until a take frees space
                    if self._closed:
                        return
                    self._buffer[frame] = (sequence, actual, data)
                    self._latest_frame = frame
                    self._cond.notify_all()
        except Exception as error:  # noqa: BLE001 - any violation stops the channel; later takes are ``failed``
            with self._cond:
                self.error = f"{type(error).__name__}: {error}"
                self._cond.notify_all()

    def take(self, item: dict, wait_s: float) -> FrameResult:
        """Return the verified frame of camera ``item`` (from the ``carla-items`` link), waiting at most ``wait_s``."""

        value = item.get("value") if isinstance(item, dict) and item.get("flowId") == "camera" else None
        if not isinstance(value, dict) or type(item.get("frame")) is not int or not _sha(value.get("rawSha256")) \
                or type(value.get("rawLength")) is not int:
            raise ValueError("take needs a camera item with frame, rawSha256 and rawLength")
        frame, want, length = item["frame"], value["rawSha256"], value["rawLength"]
        deadline = time.monotonic() + wait_s
        with self._cond:
            self.counts["taken"] += 1
            while True:
                for older in [f for f in self._buffer if f < frame]:  # superseded: never consumed
                    del self._buffer[older]
                    self.counts["skipped"] += 1
                    self._cond.notify_all()
                if frame in self._buffer:
                    _, actual, data = self._buffer.pop(frame)
                    self._cond.notify_all()
                    ok = actual == want and len(data) == length
                    status = "verified" if ok else "mismatch"
                    self.counts[status] += 1
                    return FrameResult(status, frame, want, length, actual, None if ok else "bytes differ from the item's rawSha256",
                                       data if ok else None)
                passed = (self._latest_frame is not None and self._latest_frame > frame) or self.end is not None or self.eof
                if passed:  # the frame will not come: the adapter dropped it, or it was lost
                    if self._pending_drops > 0:
                        self._pending_drops -= 1
                        status, reason = "dropped", "adapter-reported drop"
                    else:
                        status, reason = "lost", "absent and not reported as dropped"
                    self.counts[status] += 1
                    return FrameResult(status, frame, want, length, reason=reason)
                if self.error is not None:
                    self.counts["failed"] += 1
                    return FrameResult("failed", frame, want, length, reason=self.error)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.counts["missing"] += 1
                    return FrameResult("missing", frame, want, length, reason=f"not received within {wait_s} s")
                self._cond.wait(remaining)

    def summary(self) -> dict:
        """Counters and identities only (no pixel bytes)."""

        with self._cond:
            return {"protocol": PROTOCOL, "formatSha256": self.format_sha256, "format": self.fmt, "counts": dict(self.counts),
                    "pendingDrops": self._pending_drops, "buffered": len(self._buffer), "end": self.end, "eof": self.eof,
                    "error": self.error}

    def reconcile(self) -> dict:
        """Check the accounting after the run: every offered frame sent or dropped, every absent take explained by an
    adapter-reported drop, no unaccounted sequence gap, and every take in exactly one status."""

        s = self.summary()
        end, c = s["end"] or {}, s["counts"]
        absent = c["dropped"] + c["missing"] + c["lost"]  # a frame dropped last is known only from ``end`` (R-1)
        checks = {"endReceived": bool(end), "noUnaccountedGap": c["gapUnaccounted"] == 0,
                  "absencesExplainedByDrops": bool(end) and absent == end["dropped"], "noChannelError": s["error"] is None,
                  "offeredEqualsSentPlusDropped": bool(end) and end["offered"] == end["sent"] + end["dropped"],
                  "receivedEqualsSent": bool(end) and c["received"] == end["sent"], "noHeaderMismatch": c["headerMismatch"] == 0,
                  "everyTakeAccounted": c["taken"] == sum(c[k] for k in STATUSES)}
        return {"ok": all(checks.values()), "checks": checks, "summary": s}

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        if self._conn is not None:  # shut down first: the reader's makefile would otherwise keep the descriptor open
            try:
                self._conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for closer in (getattr(self, "_reader", None), self._conn, self._listener):
            try:
                if closer is not None:
                    closer.close()
            except (OSError, ValueError):
                pass
        try:
            if self.path.is_socket():
                self.path.unlink()
        except OSError:
            pass
