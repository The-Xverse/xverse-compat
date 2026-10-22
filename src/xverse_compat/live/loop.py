"""Lite vehicle loop: paces ``carla-items/2`` ticks, routes adapter items through the Phase 6 flow receiver
and records raw per-tick observations.

Time domains:
- ``carla-simulation``: item origins (``originNs``) and the receiver clock (the simulation time of the
  latest ticked frame);
- ``host-monotonic``: pacing, deadlines and cancellation (``time.monotonic``), so they keep working while
  simulation time is paused.

Runtime decisions use only runtime items and commands; nothing here reads ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable

from xverse.flows import FlowItem, FlowReceiver, TickClock
from xverse.flows.binding import FlowBinding, FlowPolicy
from xverse.flows.timebase import TimeMapping

DOMAIN = "carla-simulation"
RUNTIME_FLOWS = ("vehicle-motion", "radar-adas")


def motion_binding(flow_id: str, freshness_ns: int, deadline_ns: int) -> FlowBinding:
    """The ordered best-effort loopback binding of one adapter flow in the ``carla-simulation`` domain."""

    return FlowBinding(flow_id, flow_id + "-out", flow_id + "-in", flow_id, "ordered", FlowPolicy("fifo", "best-effort", 8, "reject", 0, 0),
                       "best_effort", "per_route_fifo", "loopback", DOMAIN, DOMAIN, TimeMapping(DOMAIN, DOMAIN, 0, 0), freshness_ns, deadline_ns)


@dataclass
class LoopResult:
    """Outcome of one bounded loop."""

    ticks: int = 0
    end_reason: str = ""
    done: dict | None = None
    refusals: list = field(default_factory=list)
    verdicts: dict = field(default_factory=dict)
    receivers: dict = field(default_factory=dict)


class LiteVehicleLoop:
    """Drive one adapter link for a bounded episode.

    @param link A started ``SocketAdapterLink`` (or ``CarlaAdapterProcess`` for protocol 1 tests).
    @param command_source ``f(sim_time_s, last_motion) -> (throttle, brake, meta)``; runtime inputs only.
    @param on_motion Optional ``f(motion_item, frame_sim_s)`` (e.g. the gateway's status publication).
    @param record Writable text stream for raw JSON Lines records.
    """

    def __init__(self, link, command_source: Callable, *, record, on_motion: Callable | None = None, tick_period_s: float = 0.05,
                 max_ticks: int, wall_deadline: float, freshness_ns: int = 100_000_000, deadline_ns: int = 200_000_000,
                 cancelled: Callable[[], bool] = lambda: False, deadline_frames: int = 1, listener: Any = None) -> None:
        self.link, self.command_source, self.record, self.on_motion = link, command_source, record, on_motion
        self.tick_period_s, self.max_ticks, self.wall_deadline = tick_period_s, max_ticks, wall_deadline
        self.cancelled, self.deadline_frames = cancelled, deadline_frames
        self.clock = TickClock({})
        self.receivers = {f: FlowReceiver(motion_binding(f, freshness_ns, deadline_ns), self.clock, listener=listener) for f in RUNTIME_FLOWS}
        for receiver in self.receivers.values():
            receiver.activate()

    def _write(self, data: dict) -> None:
        self.record.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")

    def run(self) -> LoopResult:
        result = LoopResult()
        sim_s, last_motion, episode_ns = 0.0, None, None  # sim_s: seconds since the first ticked frame of this episode
        start = time.monotonic()
        for tick in range(self.max_ticks):
            now = time.monotonic()
            if self.cancelled():
                result.end_reason = "cancelled"
                break
            if now >= self.wall_deadline:
                result.end_reason = "wall-deadline"
                break
            throttle, brake, meta = self.command_source(sim_s, last_motion)
            command_id = f"t{tick}"
            self.link.command(command_id, brake, self.deadline_frames, throttle)
            sent = time.monotonic_ns()
            step = self.link.tick()
            received = time.monotonic_ns()
            result.ticks += 1
            if step.done is not None:
                result.done, result.end_reason = step.done, "adapter-done"
                self._write({"kind": "done", "tick": tick, "done": step.done})
                break
            motion = next((i for i in step.items if i["flowId"] == "vehicle-motion"), None)
            frame_ns = motion["originNs"] if motion else max((i["originNs"] for i in step.items), default=None)
            verdicts = {}
            if frame_ns is not None:
                self.clock.at(frame_ns)  # receiver clock: simulation time of the ticked frame
                episode_ns = frame_ns if episode_ns is None else episode_ns
                sim_s = (frame_ns - episode_ns) / 1e9
                for item in step.items:
                    if item["flowId"] in self.receivers:
                        verdict = self.receivers[item["flowId"]].receive(FlowItem(item["flowId"], item["sequence"], item["originNs"]))
                        verdicts[item["flowId"]] = verdict.verdict
                        result.verdicts[verdict.verdict] = result.verdicts.get(verdict.verdict, 0) + 1
                for receiver in self.receivers.values():
                    receiver.poll()
            if motion is not None:
                last_motion = motion
                if self.on_motion is not None:
                    self.on_motion(motion, sim_s)
            result.refusals += step.refusals
            self._write({"kind": "tick", "tick": tick, "frame": step.frame, "commandId": command_id, "throttle": throttle, "brake": brake,
                         "commandMeta": meta, "sentMonotonicNs": sent, "tickedMonotonicNs": received, "simS": sim_s,
                         "motion": motion["value"] if motion else None, "motionOriginNs": motion["originNs"] if motion else None,
                         "radarCount": next((i["value"]["count"] for i in step.items if i["flowId"] == "radar-adas"), None),
                         "items": [i["flowId"] for i in step.items], "refusals": step.refusals, "acks": step.acks, "flowVerdicts": verdicts})
            pause = start + (tick + 1) * self.tick_period_s - time.monotonic()
            if pause > 0:
                time.sleep(pause)
        else:
            result.end_reason = "max-ticks"
        result.receivers = {f: r.summary() for f, r in self.receivers.items()}
        return result


def profile_source(profile: list[dict]) -> Callable:
    """A declared open-loop command profile ``[{"untilS": s, "throttle": t, "brake": b}, ...]`` (live check only)."""

    def source(sim_s: float, last_motion: Any):
        for segment in profile:
            if sim_s < segment["untilS"]:
                return segment["throttle"], segment["brake"], {"segmentUntilS": segment["untilS"]}
        return 0.0, profile[-1]["brake"], {"segmentUntilS": None}

    return source
