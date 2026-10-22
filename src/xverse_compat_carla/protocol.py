"""``xverse-compat.carla-items/1`` adapter loop (contract rules 1-8; design §9.1-§9.2).

Handshake ``hello`` -> settings check -> wait for ``start``; then per ``tick``: apply pending commands,
advance the source, emit that frame's items and refusals in ``flowId`` order, the acks decided at
that frame, and ``status: ticked``. ``stop`` or EOF acknowledge open commands and end with
``status: done`` and exit 0. ``EPISODE``, ``SETTINGS`` and source exceptions emit a refusal and
``done`` and exit 3; a protocol violation writes one stderr line and exits 2 with nothing further on
stdout.
"""

from __future__ import annotations

import json
import math
import sys

from . import codes as C
from .actuation import CommandTracker
from .groundtruth import GroundTruthExporter
from .items import ItemBuilder
from .sensors import camera_value, motion_value, radar_value, sensor_origin
from .settings import check_settings
from .timeconv import seconds_to_ns

PROTOCOL_ID = "xverse-compat.carla-items/1"
MAX_LINE = 65536
FLOWS = ("camera", "radar-adas", "radar-vc", "vehicle-motion")
FORBIDDEN = ("xverse_compat", "xverse_xdl")


class ProtocolViolation(Exception):
    """A malformed inbound line: non-JSON, NaN/Infinity, over the limit, or a non-start first message (exit 2)."""


class UnknownInbound(Exception):
    """An unknown message type or malformed command: a ``COMMAND`` refusal; the stream continues (rule 4)."""


def _reject_constant(name):
    """``json.loads`` hook: NaN and Infinity are not admitted."""

    raise ProtocolViolation(f"non-finite JSON constant {name}")


class StrictLines:
    """Line reader over a binary stream that decodes each line strictly as UTF-8 (review 2 L-a, review 3 L4).

    Under ``env -i`` the interpreter runs in UTF-8 mode with ``surrogateescape``; decoding per line serves
    every valid line that precedes an invalid one, which then raises ``UnicodeDecodeError`` (exit 2).
    """

    def __init__(self, raw) -> None:
        self._raw = raw

    def readline(self) -> str:
        return self._raw.readline().decode("utf-8", errors="strict")

    def __iter__(self):
        while True:
            line = self.readline()
            if not line:
                return
            yield line


def parse_inbound(line: str) -> dict:
    """Validate one platform -> adapter line (rules 1, 4)."""

    if len(line.rstrip("\n").encode("utf-8")) > MAX_LINE:  # the terminator is not counted (review 3 nit)
        raise ProtocolViolation("inbound line exceeds the limit")
    try:
        message = json.loads(line, parse_constant=_reject_constant)
    except ValueError as error:
        raise ProtocolViolation(f"inbound line is not JSON: {error}") from error
    if not isinstance(message, dict) or message.get("type") not in ("start", "tick", "command", "stop"):
        raise UnknownInbound("unknown inbound message type")
    if message["type"] == "command" and set(message) != {"type", "commandId", "brake", "deadlineFrames"}:
        raise UnknownInbound("command members differ from the schema")
    if message["type"] in ("start", "tick", "stop") and set(message) != {"type"}:
        raise UnknownInbound(f"{message['type']} carries extra members")
    return message


def forbidden_modules_loaded() -> list:
    """Return loaded module names that must never be imported by this process."""

    return sorted(name for name in sys.modules if name in FORBIDDEN or name.startswith(tuple(f + "." for f in FORBIDDEN)))


class _Out:
    """Line writer with the outbound line limit."""

    def __init__(self, stream) -> None:
        self._stream = stream

    def send(self, message: dict) -> None:
        line = json.dumps(message, separators=(",", ":"), allow_nan=False, sort_keys=True)
        if len(line.encode("utf-8")) > MAX_LINE:
            raise ProtocolViolation("outbound line exceeds the limit")
        self._stream.write(line + "\n")
        self._stream.flush()


def _frame_items(fd, d, builder: ItemBuilder, out: _Out) -> float | None:
    """Emit the items/refusals of one frame in flow order; return the forward acceleration if known."""

    accel = None
    for flow in FLOWS:
        try:
            # time and identity are checked before the value for every stream (review 2 L-f)
            if flow == "camera":
                if fd.camera is None:
                    continue
                frame, origin = sensor_origin(fd.camera, fd.frame, flow)
                builder.check(flow, frame, origin)
                value = camera_value(fd.camera, d, flow, frame)
            elif flow.startswith("radar"):
                if fd.radar is None:
                    continue
                frame, origin = sensor_origin(fd.radar, fd.frame, flow)
                builder.check(flow, frame, origin)
                value = radar_value(fd.radar, d, flow, frame)
            else:
                if fd.motion is None:
                    continue
                frame, origin = fd.frame, fd.elapsed_seconds
                builder.check(flow, frame, origin)
                value = motion_value(fd.motion, flow, frame)
            out.send(builder.emit(flow, frame, origin, value))
            if flow == "vehicle-motion":
                accel = value["accelForwardMps2"]  # only an emitted sample feeds ``responded`` (review 2 L-e)
        except C.CarlaRefusal as refusal:
            if refusal.code in C.EXIT_3:
                raise
            out.send(refusal.to_message())
    return accel


def run(source, descriptors, stdin, stdout, stderr, *, carla_version=None, ground_truth=None) -> int:
    """Serve the protocol until stop/EOF; return the exit code (0, 2 or 3)."""

    out = _Out(stdout)
    builder = ItemBuilder(FLOWS)
    tracker = CommandTracker(descriptors)
    try:
        exporter = GroundTruthExporter(ground_truth) if ground_truth else None
    except OSError as error:  # review 2 L-b: an unwritable export path ends the run before any protocol
        print(f"{C.SOURCE}: {type(error).__name__}: {error}", file=stderr)
        return 3
    frame = None
    elapsed = None

    def done(code: int) -> int:
        for ack in tracker.close():  # every termination path acknowledges open and pending commands
            out.send(ack)
        out.send({"type": "status", "state": "done", "frame": frame, "forbiddenModulesLoaded": forbidden_modules_loaded()})
        return code

    try:
        out.send({"type": "hello", "protocol": PROTOCOL_ID, "carlaVersion": carla_version,
                  "python": ".".join(str(v) for v in sys.version_info[:3]), "source": "live" if carla_version else "fake",
                  "flows": list(FLOWS)})
        try:
            check_settings(source.settings(), descriptors)
        except C.CarlaRefusal as refusal:
            out.send(refusal.to_message())
            return done(3)
        except Exception as error:  # noqa: BLE001 - a client failure while reading settings (review 4 L3)
            print(f"{C.SOURCE}: {type(error).__name__}: {error}", file=stderr)
            out.send({"type": "refusal", "code": C.SOURCE, "flowId": None, "frame": None})
            return done(3)
        first = stdin.readline()
        if not first:
            return done(0)
        try:
            is_start = parse_inbound(first)["type"] == "start"
        except UnknownInbound:
            is_start = False
        if not is_start:
            raise ProtocolViolation("first inbound message must be start")
        for line in stdin:
            try:
                message = parse_inbound(line)
                if message["type"] == "start":  # only the handshake may carry start (review M1)
                    raise UnknownInbound("start after the handshake")
            except UnknownInbound as error:
                print(f"{C.COMMAND}: {error}", file=stderr)
                out.send({"type": "refusal", "code": C.COMMAND, "flowId": None, "frame": None})
                continue
            if message["type"] == "command":
                try:
                    tracker.submit(message)
                except C.CarlaRefusal as refusal:
                    out.send(refusal.to_message())
                continue
            if message["type"] == "stop":
                break
            commands = tracker.take_pending()
            try:
                source.apply(commands)
                fd = source.tick()
                if fd is not None and (type(fd.frame) is not int or fd.frame < 0):  # review 2 L-b
                    raise ValueError(f"source frame {fd.frame!r} is not a non-negative integer")
                if fd is not None and frame is not None and fd.frame <= frame:  # tick-level monotonicity (review 3 L3)
                    raise ValueError(f"source frame {fd.frame} does not increase after {frame}")
            except C.CarlaRefusal as refusal:
                tracker.restore(commands)  # review M2: acked unacknowledged by done()
                out.send(refusal.to_message())
                return done(3)
            except Exception as error:  # noqa: BLE001 - any client failure ends the run (SOURCE)
                tracker.restore(commands)
                print(f"{C.SOURCE}: {type(error).__name__}: {error}", file=stderr)
                out.send({"type": "refusal", "code": C.SOURCE, "flowId": None, "frame": frame})
                return done(3)
            if fd is None:
                tracker.restore(commands)
                break
            frame = fd.frame
            tracker.opened(commands, frame)
            try:
                accel = _frame_items(fd, descriptors, builder, out)
                # tick level, after the frame's flows (which stand, design §9.10): an episode reset is caught even
                # when no flow carries the elapsed time (review 3 L3)
                if (type(fd.elapsed_seconds) in (int, float) and math.isfinite(fd.elapsed_seconds) and fd.elapsed_seconds >= 0
                        and elapsed is not None and fd.elapsed_seconds < elapsed):  # a negative time is TIMESTAMP only (review 4 L1)
                    raise C.CarlaRefusal(C.EPISODE, "elapsed_seconds decreased: episode reset", None, frame)
                if (exporter is not None and type(fd.elapsed_seconds) in (int, float) and math.isfinite(fd.elapsed_seconds)
                        and fd.elapsed_seconds >= 0):  # a bool is not a time (review 5 N2)
                    exporter.write(frame, seconds_to_ns(fd.elapsed_seconds), fd.actors)
            except C.CarlaRefusal as refusal:
                out.send(refusal.to_message())
                return done(3)
            except ProtocolViolation:
                raise
            except Exception as error:  # noqa: BLE001 - review L2: e.g. a non-finite ground-truth value
                print(f"{C.SOURCE}: {type(error).__name__}: {error}", file=stderr)
                out.send({"type": "refusal", "code": C.SOURCE, "flowId": None, "frame": frame})
                return done(3)
            if type(fd.elapsed_seconds) in (int, float) and math.isfinite(fd.elapsed_seconds) and fd.elapsed_seconds >= 0:
                elapsed = fd.elapsed_seconds
            for ack in tracker.observe(frame, fd.echo_brake, accel):
                out.send(ack)
            out.send({"type": "status", "state": "ticked", "frame": frame})
        return done(0)
    except (ProtocolViolation, UnicodeError) as error:  # invalid UTF-8 on stdin is a protocol violation (L2, review 2 L-a)
        print(f"{C.PROTOCOL}: {error}", file=stderr)
        return 2
