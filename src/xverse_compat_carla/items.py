"""Item envelope: per-flow consecutive counters, frame and episode rules (data model)."""

from __future__ import annotations

import math

from .codes import EPISODE, FRAME, TIMESTAMP, CarlaRefusal
from .timeconv import seconds_to_ns


class ItemBuilder:
    """Build items for a fixed set of flows; refusals consume no sequence number."""

    def __init__(self, flows) -> None:
        """Create the builder for ``flows`` (ids)."""

        self.flows = tuple(flows)
        self._next = {flow: 0 for flow in self.flows}
        self._frame = {flow: None for flow in self.flows}
        self._origin = {flow: None for flow in self.flows}

    def check(self, flow_id: str, frame, origin_s) -> int:
        """Validate frame and origin for ``flow_id``; return the origin in ns or raise.

        ``TIMESTAMP`` (missing/non-finite/negative origin) and ``FRAME`` (non-increasing frame) continue
        the stream; ``EPISODE`` (decreasing origin) ends it.
        """

        if type(origin_s) not in (int, float) or not math.isfinite(origin_s) or origin_s < 0:
            raise CarlaRefusal(TIMESTAMP, "origin is missing, non-finite or negative", flow_id, frame if type(frame) is int else None)
        if type(frame) is not int or frame < 0:
            raise CarlaRefusal(FRAME, "frame is not a non-negative integer", flow_id, None)
        last_frame = self._frame[flow_id]
        if last_frame is not None and frame <= last_frame:
            raise CarlaRefusal(FRAME, f"frame {frame} does not increase", flow_id, frame)
        last_origin = self._origin[flow_id]
        if last_origin is not None and origin_s < last_origin:
            raise CarlaRefusal(EPISODE, "origin decreased: episode reset", flow_id, frame)
        return seconds_to_ns(origin_s)

    def emit(self, flow_id: str, frame: int, origin_s, value: dict) -> dict:
        """Return the next item of ``flow_id`` (consumes one sequence number)."""

        origin_ns = self.check(flow_id, frame, origin_s)
        sequence = self._next[flow_id]
        self._next[flow_id] = sequence + 1
        self._frame[flow_id] = frame
        self._origin[flow_id] = origin_s
        return {"type": "item", "flowId": flow_id, "sequence": sequence, "originNs": origin_ns, "frame": frame, "value": value}
