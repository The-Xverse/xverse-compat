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
SRC = Path(__file__).resolve().parents[1]
STATUS = ("running", "ticked", "draining", "done")


class CarlaProtocolError(RuntimeError):
    """An outbound message violates the protocol; the child is killed."""


def _reject_constant(name):
    raise CarlaProtocolError(f"non-finite JSON constant {name}")


def _is_int(value) -> bool:
    return type(value) is int


def _is_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def parse_outbound(line: str) -> dict:
    """Validate one adapter -> platform line (contract rules 1-3; ground truth is not a type)."""

    if len(line.encode("utf-8")) > MAX_LINE:
        raise CarlaProtocolError("outbound line exceeds the limit")
    try:
        message = json.loads(line, parse_constant=_reject_constant)
    except ValueError as error:
        raise CarlaProtocolError(f"outbound line is not JSON: {error}") from error
    kind = message.get("type") if isinstance(message, dict) else None
    if kind == "hello":
        ok = (set(message) == {"type", "protocol", "carlaVersion", "python", "source", "flows"} and message["protocol"] == PROTOCOL_ID
              and isinstance(message["flows"], list) and all(isinstance(f, str) for f in message["flows"])
              and message["source"] in ("live", "fake") and isinstance(message["python"], str)
              and (message["carlaVersion"] is None or isinstance(message["carlaVersion"], str)))
    elif kind == "item":
        ok = (set(message) == {"type", "flowId", "sequence", "originNs", "frame", "value"} and isinstance(message["flowId"], str)
              and _is_int(message["sequence"]) and message["sequence"] >= 0 and _is_int(message["originNs"]) and message["originNs"] >= 0
              and _is_int(message["frame"]) and isinstance(message["value"], dict))
    elif kind == "refusal":
        ok = (set(message) == {"type", "code", "flowId", "frame"} and isinstance(message["code"], str)
              and message["code"].startswith("XVERSE-COMPAT-CARLA-") and (message["flowId"] is None or isinstance(message["flowId"], str))
              and (message["frame"] is None or _is_int(message["frame"])))
    elif kind == "ack":
        ok = (set(message) == {"type", "commandId", "result", "echoFrame", "responded"} and message["result"] in ("echoed", "unacknowledged")
              and (message["echoFrame"] is None or _is_int(message["echoFrame"])) and message["responded"] in (True, False, None))
    elif kind == "status":
        state = message.get("state")
        members = {"type", "state", "frame", "forbiddenModulesLoaded"} if state == "done" else {"type", "state", "frame"}
        ok = (state in STATUS and set(message) == members and (message["frame"] is None or _is_int(message["frame"]))
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

    def start(self) -> dict:
        """Launch the child, read ``hello``, answer ``start``; return the hello."""

        self._proc = subprocess.Popen(self.argv, cwd=SRC, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._pump, args=(self._proc.stdout, self._lines), daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self.hello = self._read()
        if self.hello.get("type") != "hello":
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
            return parse_outbound(line.rstrip("\n"))
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
            raise CarlaProtocolError("pacing: previous tick not finished")
        self._awaiting = True
        try:
            self._send({"type": "tick"})
            return self._collect(TickResult(), ("ticked", "done"))
        finally:
            self._awaiting = False

    def read_until_done(self) -> TickResult:
        """Collect messages up to ``status: done`` without sending anything (an adapter that ended on its own)."""

        return self._collect(TickResult(), ("done",))

    def stop(self) -> tuple[int, TickResult]:
        """Send ``stop``, collect acks and ``done``, and wait for the exit code."""

        self._send({"type": "stop"})
        self._proc.stdin.close()
        result = self._collect(TickResult(), ("done",))
        return self._proc.wait(timeout=self.timeout_s), result

    def wait(self) -> int:
        """Wait for the child to exit; return its code."""

        return self._proc.wait(timeout=self.timeout_s)

    def kill(self) -> None:
        """Kill the child if it is running."""

        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=5)
