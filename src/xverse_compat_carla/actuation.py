"""Brake commands and command-echo acknowledgement (data model "Commands"; window amendment G1).

A command applied at a tick has the window F ... F+d-1, F being the frame that tick produces. The ack
is emitted at the end of the window: ``echoed`` when any window frame's ``get_control().brake`` is
within ``echoTolerance`` of the command (``echoFrame`` = the first such frame), else
``unacknowledged``; ``responded`` is whether any window frame showed forward acceleration at or below
``responseAccelMps2`` (``None`` when no motion was available). An echo is client-cached control and
is **not** evidence that braking occurred.
"""

from __future__ import annotations

import math

from .codes import COMMAND, CarlaRefusal
from .descriptors import SensorDescriptors


class CommandTracker:
    """Validate, apply and acknowledge brake commands."""

    def __init__(self, d: SensorDescriptors, protocol: int = 1) -> None:
        """Create the tracker; protocol 2 commands also carry ``throttle`` (Phase 7 successor, carla-items/2)."""

        self._d = d
        self._protocol = protocol
        self._seen: set[str] = set()
        self._pending: list[dict] = []
        self._open: list[dict] = []

    def submit(self, command: dict) -> None:
        """Queue ``command`` for the next tick or raise ``COMMAND``."""

        cid, brake, frames = command.get("commandId"), command.get("brake"), command.get("deadlineFrames")
        if not isinstance(cid, str) or not cid or cid in self._seen:
            raise CarlaRefusal(COMMAND, "commandId missing or repeated")
        if type(brake) not in (int, float) or not math.isfinite(brake) or not 0 <= brake <= 1:
            raise CarlaRefusal(COMMAND, "brake outside [0, 1]")
        if type(frames) is not int or not 1 <= frames <= self._d.deadline_frames:
            raise CarlaRefusal(COMMAND, "deadlineFrames outside [1, descriptor]")
        entry = {"commandId": cid, "brake": float(brake), "deadlineFrames": frames}
        if self._protocol == 2:
            throttle = command.get("throttle")
            if type(throttle) not in (int, float) or not math.isfinite(throttle) or not 0 <= throttle <= 1:
                raise CarlaRefusal(COMMAND, "throttle outside [0, 1]")
            entry["throttle"] = float(throttle)
        self._seen.add(cid)
        self._pending.append(entry)

    def take_pending(self) -> list[dict]:
        """Return and clear the commands to apply at this tick."""

        pending, self._pending = self._pending, []
        return pending

    def opened(self, commands: list[dict], frame: int) -> None:
        """Open the windows of ``commands`` applied at the tick producing ``frame``."""

        for cmd in commands:
            self._open.append(dict(cmd, first=frame, last=frame + cmd["deadlineFrames"] - 1, echoFrame=None, responded=None))

    def observe(self, frame: int, echo_brake, accel_forward) -> list[dict]:
        """Record ``frame``'s echo and motion; return the acks whose window ends at ``frame``."""

        acks, still = [], []
        for w in self._open:
            if w["first"] <= frame <= w["last"]:
                if w["echoFrame"] is None and type(echo_brake) in (int, float) and abs(echo_brake - w["brake"]) <= self._d.echo_tolerance:
                    w["echoFrame"] = frame
                if accel_forward is not None:
                    hit = accel_forward <= self._d.response_accel_mps2
                    w["responded"] = bool(w["responded"]) or hit
            if frame >= w["last"]:
                acks.append(self._ack(w))
            else:
                still.append(w)
        self._open = still
        return acks

    def restore(self, commands: list[dict]) -> None:
        """Return commands taken for a tick that produced no frame to the pending list (review M2)."""

        self._pending = list(commands) + self._pending

    def close(self) -> list[dict]:
        """Acknowledge every open or pending command at termination (design §9.11).

        An open window keeps its observed echo (truncated window); a window without an echo and a command
        never applied are ``unacknowledged``."""

        acks = [self._ack(w) for w in self._open]
        acks += [self._ack(dict(c, echoFrame=None, responded=None)) for c in self._pending]
        self._open, self._pending = [], []
        return acks

    @staticmethod
    def _ack(w: dict) -> dict:
        """Return the protocol ack of window ``w``."""

        return {"type": "ack", "commandId": w["commandId"], "result": "echoed" if w["echoFrame"] is not None else "unacknowledged",
                "echoFrame": w["echoFrame"], "responded": w["responded"]}
