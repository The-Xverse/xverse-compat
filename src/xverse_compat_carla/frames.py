"""Camera raw-frame side channel, adapter side (Phase 8 WP-06; design record docs/engineering/phase8/review-wp06.md).

``xverse-compat.camera-frames/1`` over a second Unix stream socket that the platform (U2) listens on. Each record
is one JSON header line, and a ``frame`` header is followed by exactly ``rawLength`` raw bytes. The camera item on
the ``carla-items`` link is unchanged and keeps ``rawSha256``, which the receiver verifies. The tick path never
blocks: frames go into a bounded queue serviced by one writer thread, and a full queue or a failed socket drops
the frame with accounting (``offered = sent + dropped``). Standard library only; never imports ``xverse_compat``.
"""

from __future__ import annotations

import hashlib
import json
import queue
import threading

PROTOCOL = "xverse-compat.camera-frames/1"
FORMAT_SCHEMA = "xverse-compat.camera-frame-format/1"
FORMAT_MEMBERS = {"schema", "width", "height", "encoding"}
ENCODINGS = {"bgra8": 4}  # CARLA raw_data layout; the 3.10 adapter does not transcode
QUEUE_DEPTH = 2  # engineering constant: U2 consumes a step's frame before it requests the next tick (WP-12 lockstep)
MAX_LINE = 65536


def canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def load_format(record) -> dict:
    """Validate a declared frame-format record (AD-02 input fidelity; no defaults). Raise ``ValueError``."""

    if not isinstance(record, dict) or set(record) != FORMAT_MEMBERS:
        raise ValueError(f"frame format members must be exactly {sorted(FORMAT_MEMBERS)}")
    if record["schema"] != FORMAT_SCHEMA:
        raise ValueError(f"frame format schema must be {FORMAT_SCHEMA}")
    for key in ("width", "height"):
        if type(record[key]) is not int or record[key] <= 0:
            raise ValueError(f"frame format {key} must be a positive int")
    if record["encoding"] not in ENCODINGS:
        raise ValueError(f"frame format encoding must be one of {sorted(ENCODINGS)}")
    return dict(record)


def frame_length(fmt: dict) -> int:
    return fmt["width"] * fmt["height"] * ENCODINGS[fmt["encoding"]]


def format_sha256(fmt: dict) -> str:
    return hashlib.sha256(canonical(fmt)).hexdigest()


class FramePublisher:
    """Bounded, non-blocking publisher of camera frames to a connected Unix stream socket."""

    def __init__(self, sock, fmt: dict, depth: int = QUEUE_DEPTH) -> None:
        self.fmt = load_format(fmt)
        self.length = frame_length(self.fmt)
        self._sock = sock
        self._queue = queue.Queue(maxsize=depth)
        self._lock = threading.Lock()
        self.offered = self.sent = self.dropped = 0
        self.error = None
        self._send(canonical({"type": "hello", "protocol": PROTOCOL, "format": self.fmt, "formatSha256": format_sha256(self.fmt)}) + b"\n")
        self._thread = threading.Thread(target=self._writer, name="camera-frames", daemon=True)
        self._thread.start()

    def _send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def _writer(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            header, raw = item
            try:
                self._send(header + b"\n" + raw)
                with self._lock:
                    self.sent += 1
            except OSError as error:  # the socket failed: this frame and every later one count as dropped
                with self._lock:
                    self.error = f"{type(error).__name__}: {error}"
                    self.dropped += 1
                self._drain()
                return

    def _drain(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is None:
                return
            with self._lock:
                self.dropped += 1

    def offer(self, frame: int, raw: bytes) -> bool:
        """Queue one frame (never blocks); return whether it was queued. A refused frame is counted as dropped."""

        if len(raw) != self.length:
            raise ValueError(f"frame {frame}: {len(raw)} bytes, the declared format needs {self.length}")
        with self._lock:
            sequence = self.offered
            self.offered += 1
            failed = self.error is not None
            dropped = self.dropped
        header = canonical({"type": "frame", "frame": frame, "sequence": sequence, "rawSha256": hashlib.sha256(raw).hexdigest(),
                            "rawLength": len(raw), "dropped": dropped})
        if not failed:
            try:
                self._queue.put_nowait((header, raw))
                return True
            except queue.Full:
                pass
        with self._lock:
            self.dropped += 1
        return False

    def close(self, timeout_s: float = 5.0) -> dict:
        """Flush within ``timeout_s``, send the ``end`` record and return the accounting."""

        try:
            self._queue.put(None, timeout=timeout_s)
        except queue.Full:
            pass
        self._thread.join(timeout_s)
        with self._lock:
            if self._thread.is_alive():  # still blocked in sendall: the queued frames are unsent
                self.error = self.error or "writer did not finish within the close bound"
            self.dropped = self.offered - self.sent if self._thread.is_alive() else self.dropped
            summary = {"offered": self.offered, "sent": self.sent, "dropped": self.dropped, "error": self.error}
        if not self._thread.is_alive() and self.error is None:
            try:
                self._send(canonical({"type": "end", **summary}) + b"\n")
            except OSError as error:
                summary["error"] = f"{type(error).__name__}: {error}"
        return summary
