"""Platform-side client of the CARLA adapter process (thesis 028 design §1, §9.2, §9.7).

``CarlaAdapterProcess`` launches ``xverse_compat_carla.main`` under the pinned CPython 3.10 environment
with ``env -i PATH=/usr/bin HOME=/nonexistent-carla-home <python> -s -m ...`` from ``<checkout>/src``,
validates every outbound line (``parse_outbound``: closed types and schemas, strict types, no NaN,
line limit, rule-6 ordering), enforces tick pacing and a per-tick read timeout, and drains stderr on a
daemon thread. It never starts CARLA, the bridge or zenohd.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
from typing import Any

MAX_LINE = 65536
PROTOCOL_ID = "xverse-compat.carla-items/1"
PROTOCOL_ID_2 = "xverse-compat.carla-items/2"  # Phase 7 successor: Unix-socket transport, throttle commands
SRC = Path(__file__).resolve().parents[1]
STATUS = ("running", "ticked", "draining", "done")
FLOWS = ("camera", "radar-adas", "radar-vc", "vehicle-motion")
CODES = frozenset("XVERSE-COMPAT-CARLA-" + c for c in ("FRAME", "EPISODE", "SETTINGS", "RANGE", "SIZE", "TIMESTAMP", "COMMAND", "PROTOCOL", "SOURCE"))
PYTHON = "3.10.12"
CARLA_VERSION = "0.9.15"
MAX_DETECTIONS = 500
SHA256 = frozenset("0123456789abcdef")


class CarlaProtocolError(RuntimeError):
    """An outbound message violates the protocol; the child is killed."""


def _reject_constant(name):
    raise CarlaProtocolError(f"non-finite JSON constant {name}")


def _is_int(value) -> bool:
    return type(value) is int


def _is_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _value_ok(flow: str, value) -> bool:
    """Closed value schema of each flow (data model "Values"; review 2 N1)."""

    if not isinstance(value, dict):
        return False
    if flow == "camera":
        return (set(value) == {"width", "height", "fovDeg", "rawSha256", "rawLength"} and _is_int(value["width"]) and value["width"] > 0
                and _is_int(value["height"]) and value["height"] > 0 and _is_number(value["fovDeg"]) and value["fovDeg"] > 0
                and isinstance(value["rawSha256"], str) and len(value["rawSha256"]) == 64 and set(value["rawSha256"]) <= SHA256
                and _is_int(value["rawLength"]) and value["rawLength"] == 4 * value["width"] * value["height"])
    if flow in ("radar-adas", "radar-vc"):
        rows = value.get("detections")
        return (set(value) == {"detections", "count"} and isinstance(rows, list) and len(rows) <= MAX_DETECTIONS
                and all(isinstance(r, list) and len(r) == 4 and all(_is_number(c) for c in r) for r in rows)
                and _is_int(value["count"]) and value["count"] == len(rows))
    if flow == "vehicle-motion":
        return (set(value) == {"speedMps", "accelForwardMps2"} and _is_number(value["speedMps"]) and value["speedMps"] >= 0
                and _is_number(value["accelForwardMps2"]))
    return False


def parse_outbound(line: str, flows: tuple[str, ...] = FLOWS, protocol_id: str = PROTOCOL_ID) -> dict:
    """Validate one adapter -> platform line (contract rules 1-3; ground truth is not a type).

    @param flows The flows announced in ``hello``; an item or refusal of any other flow is a violation.
    """

    if len(line.encode("utf-8")) > MAX_LINE:
        raise CarlaProtocolError("outbound line exceeds the limit")
    try:
        message = json.loads(line, parse_constant=_reject_constant)
    except ValueError as error:
        raise CarlaProtocolError(f"outbound line is not JSON: {error}") from error
    kind = message.get("type") if isinstance(message, dict) else None
    if kind == "hello":
        ok = (set(message) == {"type", "protocol", "carlaVersion", "python", "source", "flows"} and message["protocol"] == protocol_id
              and message["flows"] == list(FLOWS) and message["python"] == PYTHON
              and ((message["source"] == "fake" and message["carlaVersion"] is None)
                   or (message["source"] == "live" and message["carlaVersion"] == CARLA_VERSION)))
    elif kind == "item":
        ok = (set(message) == {"type", "flowId", "sequence", "originNs", "frame", "value"} and message["flowId"] in flows
              and _is_int(message["sequence"]) and message["sequence"] >= 0 and _is_int(message["originNs"]) and message["originNs"] >= 0
              and _is_int(message["frame"]) and message["frame"] >= 0 and _value_ok(message["flowId"], message["value"]))
    elif kind == "refusal":
        ok = (set(message) == {"type", "code", "flowId", "frame"} and message["code"] in CODES
              and (message["flowId"] is None or message["flowId"] in flows)
              and (message["frame"] is None or (_is_int(message["frame"]) and message["frame"] >= 0)))
    elif kind == "ack":
        ok = (set(message) == {"type", "commandId", "result", "echoFrame", "responded"} and isinstance(message["commandId"], str)
              and message["commandId"] != "" and message["responded"] in (True, False, None)
              and ((message["result"] == "echoed" and _is_int(message["echoFrame"]) and message["echoFrame"] >= 0)  # review 3 L1
                   or (message["result"] == "unacknowledged" and message["echoFrame"] is None)))
    elif kind == "status":
        state = message.get("state")
        members = {"type", "state", "frame", "forbiddenModulesLoaded"} if state == "done" else {"type", "state", "frame"}
        ok = (state in STATUS and set(message) == members
              and ((state != "ticked" and message["frame"] is None) or (_is_int(message["frame"]) and message["frame"] >= 0))
              and (state != "done" or (isinstance(message["forbiddenModulesLoaded"], list)
                                       and all(isinstance(m, str) for m in message["forbiddenModulesLoaded"]))))
    else:
        ok = False
    if not ok:
        raise CarlaProtocolError(f"outbound {kind!r} message violates its schema")
    return message


@dataclass
class TickResult:
    """What one tick produced."""

    frame: int | None = None
    items: list = field(default_factory=list)
    refusals: list = field(default_factory=list)
    acks: list = field(default_factory=list)
    done: dict | None = None


class CarlaAdapterProcess:
    """Run one adapter process for one episode."""

    def __init__(self, python: str | os.PathLike, descriptors: str | os.PathLike, source: str, *,
                 ground_truth: str | os.PathLike | None = None, timeout_s: float | None = None) -> None:
        """Create (not start) the process.

        @param python The pinned 3.10 environment's interpreter.
        @param descriptors Path of ``carla-sensors.json``.
        @param source ``fake:<fixture>`` (live sources are gated to Phase 7).
        @param ground_truth Optional evaluation-only export path.
        @param timeout_s Per-tick read timeout; default ``sensorWaitMs/1000 + 5`` from the descriptors (design §9.7).
        """

        self.argv = ["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(python), "-s", "-m",
                     "xverse_compat_carla.main", "--source", source, "--descriptors", str(Path(descriptors).resolve())]
        if ground_truth is not None:
            self.argv += ["--ground-truth", str(Path(ground_truth).resolve())]
        if timeout_s is None:
            timeout_s = json.loads(Path(descriptors).read_text(encoding="utf-8"))["sensorWaitMs"] / 1000.0 + 5.0
        self.timeout_s = timeout_s
        self.hello: dict | None = None
        self.stderr: deque[str] = deque(maxlen=200)
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._awaiting = False
        self._last_tick_frame: int | None = None
        self.protocol_id = PROTOCOL_ID

    def start(self) -> dict:
        """Launch the child, read ``hello``, answer ``start``; return the hello."""

        self._proc = subprocess.Popen(self.argv, cwd=SRC, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._pump, args=(self._proc.stdout, self._lines), daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self.hello = self._read()
        if self.hello is None or self.hello.get("type") != "hello":  # review 2 L-h: an adapter that ended before hello
            self.kill()
            raise CarlaProtocolError("first message is not hello")
        self._send({"type": "start"})
        return self.hello

    def _pump(self, stream, sink) -> None:
        for line in stream:
            sink.put(line)
        sink.put(None)

    def _drain_stderr(self) -> None:
        for line in self._proc.stderr:
            self.stderr.append(line.rstrip("\n"))

    def _send(self, message: dict) -> None:
        try:
            self._proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
        except BrokenPipeError:
            pass  # the adapter already ended (e.g. a settings refusal); its last messages are still readable

    def _read(self) -> dict | None:
        try:
            line = self._lines.get(timeout=self.timeout_s)
        except queue.Empty:
            self.kill()
            raise CarlaProtocolError("adapter read timeout") from None
        if line is None:
            return None
        try:
            return parse_outbound(line.rstrip("\n"), tuple(self.hello["flows"]) if self.hello else FLOWS, self.protocol_id)
        except CarlaProtocolError:
            self.kill()
            raise

    def command(self, command_id: str, brake: float, deadline_frames: int) -> None:
        """Send a brake command (applied at the next tick)."""

        self._send({"type": "command", "commandId": command_id, "brake": brake, "deadlineFrames": deadline_frames})

    def send_raw(self, message: dict) -> None:
        """Send an arbitrary inbound message (tests of the adapter's refusals)."""

        self._send(message)

    def _collect(self, result: TickResult, until: tuple[str, ...]) -> TickResult:
        try:
            return self._collect_messages(result, until)
        except CarlaProtocolError:
            self.kill()  # any violation kills the child (design §9.2; review 3 M1)
            raise

    def _collect_messages(self, result: TickResult, until: tuple[str, ...]) -> TickResult:
        last_frame = None
        acks_started = False
        while True:
            message = self._read()
            if message is None:
                raise CarlaProtocolError("adapter closed stdout without done")
            kind = message["type"]
            if kind in ("item", "refusal"):
                frame = message.get("frame")
                if acks_started and not (kind == "refusal" and frame is None):  # rule 6: items/refusals, then acks (L7)
                    raise CarlaProtocolError("item or framed refusal after an ack")
                if frame is not None and last_frame is not None and frame < last_frame:
                    raise CarlaProtocolError("frames decrease within a tick")
                last_frame = frame if frame is not None else last_frame
                (result.items if kind == "item" else result.refusals).append(message)
            elif kind == "ack":
                acks_started = True
                result.acks.append(message)
            elif kind == "status" and message["state"] in until:
                if message["state"] == "done":
                    if message["forbiddenModulesLoaded"]:  # review M3: the adapter loaded a forbidden module
                        self.kill()
                        raise CarlaProtocolError(f"forbidden modules loaded: {message['forbiddenModulesLoaded']}")
                    result.done = message
                result.frame = message.get("frame")
                return result
            else:
                raise CarlaProtocolError(f"unexpected {kind} message")

    def tick(self) -> TickResult:
        """Request one step and collect until ``ticked`` or ``done`` (pacing: one tick at a time)."""

        if self._awaiting:
            self.kill()  # review 3 M1
            raise CarlaProtocolError("pacing: previous tick not finished")
        self._awaiting = True
        try:
            self._send({"type": "tick"})
            result = self._collect(TickResult(), ("ticked", "done"))
        finally:
            self._awaiting = False
        if result.done is None:  # ``ticked`` frames increase across ticks (review 3 L3)
            if self._last_tick_frame is not None and result.frame <= self._last_tick_frame:
                self.kill()
                raise CarlaProtocolError(f"ticked frame {result.frame} does not increase")
            self._last_tick_frame = result.frame
        return result

    def read_until_done(self) -> TickResult:
        """Collect messages up to ``status: done`` without sending anything (an adapter that ended on its own)."""

        return self._collect(TickResult(), ("done",))

    def stop(self) -> tuple[int, TickResult]:
        """Send ``stop``, collect acks and ``done``, and wait for the exit code."""

        self._send({"type": "stop"})
        try:
            self._proc.stdin.close()
        except BrokenPipeError:  # review 2 L-h: the adapter already ended on its own
            pass
        result = self._collect(TickResult(), ("done",))
        return self.wait(), result

    def wait(self) -> int:
        """Wait for the child to exit; return its code."""

        try:
            return self._proc.wait(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            self.kill()  # never leave the child running (review 4 N1)
            raise

    def kill(self) -> None:
        """Kill the child if it is running."""

        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)


class SocketAdapterLink(CarlaAdapterProcess):
    """Platform side of ``carla-items/2`` over a Unix socket (Phase 7 successor, DLG-8).

    Maestro launches the adapter as its own unit with ``/dev/null`` standard streams, so the adapter
    connects to this listener instead. Validation, pacing, ordering and the violation rules are those of
    ``CarlaAdapterProcess``; on a violation the link is closed (the adapter process belongs to Maestro,
    so it is not killed here; the adapter ends on end-of-file and restores the world).
    """

    def __init__(self, socket_path: str | os.PathLike, descriptors: str | os.PathLike, *, timeout_s: float | None = None) -> None:
        """Bind and listen on ``socket_path`` (mode 0600; a stale socket file is replaced)."""

        import socket  # noqa: PLC0415

        if timeout_s is None:
            timeout_s = json.loads(Path(descriptors).read_text(encoding="utf-8"))["sensorWaitMs"] / 1000.0 + 5.0
        self.argv = []
        self.timeout_s = timeout_s
        self.hello = None
        self.stderr = deque(maxlen=1)
        self._proc = None
        self._lines = queue.Queue()
        self._awaiting = False
        self._last_tick_frame = None
        self.protocol_id = PROTOCOL_ID_2
        self.path = Path(socket_path)
        if self.path.is_socket():
            self.path.unlink()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self._listener.listen(1)
        self._conn = None
        self._writer = None

    def start(self, accept_timeout_s: float = 30.0) -> dict:
        """Accept the adapter's connection, read ``hello``, answer ``start``; return the hello."""

        self._listener.settimeout(accept_timeout_s)
        try:
            self._conn, _ = self._listener.accept()
        except OSError as error:
            raise CarlaProtocolError(f"adapter did not connect: {error}") from error
        self._conn.settimeout(None)
        self._writer = self._conn.makefile("w", encoding="utf-8", newline="\n")
        threading.Thread(target=self._pump, args=(self._conn.makefile("r", encoding="utf-8", newline="\n"), self._lines), daemon=True).start()
        self.hello = self._read()
        if self.hello is None or self.hello.get("type") != "hello":
            self.kill()
            raise CarlaProtocolError("first message is not hello")
        self._send({"type": "start"})
        return self.hello

    def _send(self, message: dict) -> None:
        try:
            self._writer.write(json.dumps(message, separators=(",", ":")) + "\n")
            self._writer.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass  # the adapter already ended; its last messages are still readable

    def command(self, command_id: str, brake: float, deadline_frames: int, throttle: float = 0.0) -> None:
        """Send a throttle/brake command (applied at the next tick)."""

        self._send({"type": "command", "commandId": command_id, "brake": brake, "throttle": throttle, "deadlineFrames": deadline_frames})

    def stop(self) -> tuple[None, TickResult]:
        """Send ``stop`` and collect the acks and ``done``; the adapter then closes the connection."""

        self._send({"type": "stop"})
        result = self._collect(TickResult(), ("done",))
        self.kill()
        return None, result

    def wait(self) -> None:
        """No owned process: the adapter is a Maestro unit."""

    def kill(self) -> None:
        """Close the connection and the listener (the adapter sees end-of-file)."""

        for closer in (self._writer, self._conn, self._listener):
            try:
                if closer is not None:
                    closer.close()
            except OSError:
                pass
        try:
            if self.path.is_socket():
                self.path.unlink()
        except OSError:
            pass
