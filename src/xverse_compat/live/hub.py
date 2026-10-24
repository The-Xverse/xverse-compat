"""U2 hub core without faults (Phase 8 WP-10 increment #2; design record ``docs/engineering/phase8/review-wp10-hub.md``).

The vehicle-loop unit is the platform side of the adapter link and the single delivery point of every inter-unit
flow (thesis ``decisions.md`` §K). ``HubSchedule`` is the pure, deterministic delivery core: AD-30 delivery at the
first step boundary at or after ``deliverAtNs``, plus the flow's declared hub delay in whole steps. ``UnitLinks`` is
the ``xverse-compat.hub-units/1`` transport over one Unix socket. ``Hub`` runs the lockstep: adapter tick, frame
verification (WP-06), late origin binding, local consumers and producers, delivery rounds with a bounded consumer
wait, lost verdicts, simulation-time start-up deadlines and a bounded step hold. Every bound and deadline is a
required parameter with no default. No fault is applied here (increment #4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import select
import socket
import threading
import time
from typing import Any, Callable

from .hub_topology import validate as validate_topology

PROTOCOL = "xverse-compat.hub-units/1"
MAX_LINE = 65536
F17 = "f17-brake-command"


class HubInvalidRun(RuntimeError):
    """The run is invalid (FR-042): a missed wait or hold bound, or an undeclared cycle."""


class HubProtocolError(RuntimeError):
    """A unit violated the hub protocol."""


def _reject_constant(name):
    raise HubProtocolError(f"non-finite JSON constant {name}")


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _positive(name, value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0 (no default; D-4c)")
    return float(value)


@dataclass(order=True)
class _Pending:
    flow: str
    source_unit: str
    sequence: int
    produced_step: int = field(compare=False)
    origin_ns: int = field(compare=False)
    deliver_at_ns: int = field(compare=False)
    message: dict = field(compare=False)
    first_step: int | None = field(default=None, compare=False)  # first boundary at or after deliverAtNs


class HubSchedule:
    """Deterministic delivery schedule over simulator-step boundaries (no I/O)."""

    def __init__(self, topology: dict) -> None:
        self.topology = validate_topology(topology)
        self.flows = {f["id"]: f for f in self.topology["flows"]}
        self.boundaries: list[int] = []  # T_k, the simulation time of step k
        self._pending: list[_Pending] = []
        self._last_sequence: dict[tuple[str, str], int] = {}
        self.refused: list[dict] = []
        self.lost: set[str] = set()  # lost-flow barrier (decisions.md "Lost-flow rule"; finding 4, M2)
        self.discarded: list[dict] = []

    def boundary(self, sim_ns: int) -> int:
        """Register the next step boundary ``T_k`` (strictly increasing); return ``k``."""

        if type(sim_ns) is not int or (self.boundaries and sim_ns <= self.boundaries[-1]):
            raise HubProtocolError(f"step boundary {sim_ns!r} does not increase")
        self.boundaries.append(sim_ns)
        step = len(self.boundaries) - 1
        for item in self._pending:
            if item.first_step is None and sim_ns >= item.deliver_at_ns:
                item.first_step = step
        return step

    def admit(self, step: int, source_unit: str, message: Any) -> bool:
        """Queue one message produced in ``step`` by ``source_unit``; refuse (and count) a non-conforming one."""

        reason = None
        flow = self.flows.get(message.get("flowId")) if isinstance(message, dict) else None
        if flow is None or flow["route"] != "hub":
            reason = "unknown or non-hub flow"
        elif flow["source"]["unit"] != source_unit:
            reason = f"unit {source_unit} does not host the source of {flow['id']}"
        else:
            seq, origin, deliver = message.get("sequence"), message.get("originNs"), message.get("deliverAtNs")
            if not all(type(v) is int and v >= 0 for v in (seq, origin, deliver)):
                reason = "sequence, originNs and deliverAtNs must be non-negative ints"
            elif deliver < origin:
                reason = "deliverAtNs before originNs"
            elif origin > self.boundaries[step]:
                reason = "originNs after the producing step's boundary (future origin)"
            elif seq <= self._last_sequence.get((flow["id"], source_unit), -1):
                reason = "sequence does not increase"
        if reason is not None:
            self.refused.append({"step": step, "unit": source_unit, "flowId": message.get("flowId") if isinstance(message, dict) else None,
                                 "reason": reason})
            return False
        if flow["id"] in self.lost:  # a lost flow never delivers again: discarded, kept as evidence
            self.discarded.append(_discard_record(step, flow["id"], source_unit, message, "admitted after the lost verdict"))
            return False
        self._last_sequence[(flow["id"], source_unit)] = message["sequence"]
        item = _Pending(flow["id"], source_unit, message["sequence"], step, message["originNs"], message["deliverAtNs"], message)
        if self.boundaries[step] >= item.deliver_at_ns:
            item.first_step = step
        self._pending.append(item)
        return True

    def due(self, step: int) -> list[_Pending]:
        """Remove and return the messages due at ``step``, ordered by (flow, source unit, sequence)."""

        ready = [p for p in self._pending if p.first_step is not None and p.first_step + self.flows[p.flow]["hubDelaySteps"] <= step]
        for p in ready:
            self._pending.remove(p)
        return sorted(ready)

    def pending(self) -> int:
        return len(self._pending)

    def discard_flow(self, flow_id: str, step: int) -> list[dict]:
        """Lost-flow barrier: drop every pending message of ``flow_id``, record each, and refuse later ones."""

        self.lost.add(flow_id)
        dropped = sorted(p for p in self._pending if p.flow == flow_id)
        for p in dropped:
            self._pending.remove(p)
            self.discarded.append(_discard_record(step, p.flow, p.source_unit, p.message, "pending at the lost verdict"))
        return dropped


def _discard_record(step, flow_id, source_unit, message, reason) -> dict:
    return {"step": step, "flowId": flow_id, "from": source_unit, "sequence": message.get("sequence"),
            "deliverAtNs": message.get("deliverAtNs"), "payloadSha256": hashlib.sha256(_canonical(message.get("payload"))).hexdigest(),
            "reason": reason}


def _send_bounded(sock, data: bytes, deadline: float) -> None:
    """Write ``data`` without blocking past ``deadline`` (finding 4, M1); raise ``TimeoutError`` at the bound.

    The socket stays blocking for its reader thread; each write is ``MSG_DONTWAIT`` after ``select`` says writable.
    """

    view = memoryview(data)
    while view:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("unit send bound exceeded")
        _, writable, _ = select.select([], [sock], [], remaining)
        if not writable:
            continue
        try:
            view = view[sock.send(view, socket.MSG_DONTWAIT):]
        except BlockingIOError:
            continue


class UnitLinks:
    """``xverse-compat.hub-units/1``: one listener; each remote unit connects and says ``hello``."""

    def __init__(self, socket_path, expected_units, send_timeout_s: float) -> None:
        self.send_timeout_s = _positive("send_timeout_s", send_timeout_s)
        self.path = Path(socket_path)
        self.expected = sorted(expected_units)
        if self.path.is_socket():
            self.path.unlink()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous = os.umask(0o177)
        try:
            self._listener.bind(str(self.path))
        finally:
            os.umask(previous)
        self._listener.listen(len(self.expected) or 1)
        self._conns: dict[str, socket.socket] = {}
        self._readers: dict[str, Any] = {}
        self.inbox: dict[str, queue.Queue] = {}
        self.closed: set[str] = set()
        self.failed: dict[str, str] = {}
        self._shut = False

    def accept_all(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while len(self._conns) < len(self.expected):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HubInvalidRun(f"units did not connect within {timeout_s} s: {sorted(set(self.expected) - set(self._conns))}")
            self._listener.settimeout(remaining)
            try:
                conn, _ = self._listener.accept()
            except OSError as error:
                raise HubInvalidRun(f"units did not connect within {timeout_s} s") from error
            conn.settimeout(max(0.001, deadline - time.monotonic()))
            reader = conn.makefile("rb")
            try:
                hello = self._parse(reader.readline(MAX_LINE + 1))
            except (OSError, HubProtocolError, ValueError) as error:
                conn.close()
                raise HubProtocolError(f"invalid hello: {error}") from error
            unit = hello.get("unit")
            if hello.get("type") != "hello" or hello.get("protocol") != PROTOCOL or unit not in self.expected or unit in self._conns:
                conn.close()
                raise HubProtocolError(f"unexpected hello {hello!r}")
            conn.settimeout(None)
            self._conns[unit] = conn
            self._readers[unit] = reader
            self.inbox[unit] = queue.Queue()
            threading.Thread(target=self._pump, args=(unit, reader), daemon=True).start()

    @staticmethod
    def _parse(line: bytes) -> dict:
        if not line:
            raise EOFError
        if len(line) > MAX_LINE or not line.endswith(b"\n"):
            raise HubProtocolError("line exceeds the limit or is truncated")
        message = json.loads(line.decode("utf-8", errors="strict"), parse_constant=_reject_constant)
        if not isinstance(message, dict):
            raise HubProtocolError("message is not an object")
        return message

    def _pump(self, unit, reader) -> None:
        while True:
            try:
                message = self._parse(reader.readline(MAX_LINE + 1))
            except EOFError:
                self.inbox[unit].put(("eof", None))
                return
            except Exception as error:  # noqa: BLE001 - a violation ends this unit's link
                self.inbox[unit].put(("error", f"{type(error).__name__}: {error}"))
                return
            self.inbox[unit].put(("message", message))

    def send(self, unit: str, message: dict, deadline: float | None = None) -> bool:
        """Send one line within the send bound (or ``deadline``); False, and the unit closed, on a timeout or error.

        A line above ``MAX_LINE`` raises ``HubProtocolError`` at the hub (finding 4, L4).
        """

        line = _canonical(message) + b"\n"
        if len(line) - 1 > MAX_LINE:
            raise HubProtocolError(f"outbound {message.get('type')} line to {unit} is {len(line) - 1} bytes, above {MAX_LINE}")
        if unit in self.closed:
            return False
        try:
            _send_bounded(self._conns[unit], line, deadline if deadline is not None else time.monotonic() + self.send_timeout_s)
            return True
        except (OSError, TimeoutError) as error:  # a partial line may be on the wire: the unit's link is closed for good
            self.closed.add(unit)
            self.failed[unit] = f"{type(error).__name__}: {error}"
            self._shutdown(unit)
            return False

    def _shutdown(self, unit: str) -> None:
        try:
            self._conns[unit].shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def close(self, timeout_s: float | None = None) -> None:
        """Send ``end`` to every open unit within one shared bound, then shut down and close; idempotent (M1, L7)."""

        if self._shut:
            return
        self._shut = True
        deadline = time.monotonic() + (self.send_timeout_s if timeout_s is None else timeout_s)
        for unit in sorted(self._conns):
            if unit not in self.closed:
                self.send(unit, {"type": "end"}, deadline=deadline)
            self._shutdown(unit)
            for closer in (self._readers.get(unit), self._conns[unit]):
                try:
                    closer.close()
                except (OSError, ValueError):
                    pass
        try:
            self._listener.close()
            if self.path.is_socket():
                self.path.unlink()
        except OSError:
            pass


@dataclass
class HubResult:
    steps: int = 0
    end_reason: str = ""
    deliveries: list = field(default_factory=list)
    lost: list = field(default_factory=list)
    invalid: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    frames: list = field(default_factory=list)
    episode_origin_ns: int | None = None
    max_rounds: int = 0
    discarded: list = field(default_factory=list)
    boundary_gaps: list = field(default_factory=list)


class Hub:
    """Lockstep hub over one adapter link and the remote units of a hub topology."""

    def __init__(self, topology: dict, *, link, units_socket_path, command_source: Callable, wait_bound_s, hold_bound_s,
                 startup_deadlines_ns: dict, connect_timeout_s, frames=None, frame_wait_s=None,
                 local_consumers: dict | None = None, local_producers: tuple = ()) -> None:
        self.frames, self.units, self._closed = frames, None, False
        try:
            self._init(topology, link=link, units_socket_path=units_socket_path, command_source=command_source,
                       wait_bound_s=wait_bound_s, hold_bound_s=hold_bound_s, startup_deadlines_ns=startup_deadlines_ns,
                       connect_timeout_s=connect_timeout_s, frames=frames, frame_wait_s=frame_wait_s,
                       local_consumers=local_consumers, local_producers=local_producers)
        except BaseException:
            self.close()  # a refused construction still closes the caller's frame receiver (finding 4, L7)
            raise

    def _init(self, topology, *, link, units_socket_path, command_source, wait_bound_s, hold_bound_s, startup_deadlines_ns,
              connect_timeout_s, frames, frame_wait_s, local_consumers, local_producers) -> None:
        self.schedule = HubSchedule(topology)
        topo = self.schedule.topology
        self.hub_unit, self.adapter_unit = topo["hubUnit"], topo["adapterUnit"]
        self.wait_bound_s = _positive("wait_bound_s", wait_bound_s)
        self.hold_bound_s = _positive("hold_bound_s", hold_bound_s)
        self.connect_timeout_s = _positive("connect_timeout_s", connect_timeout_s)
        if frames is not None:
            self.frame_wait_s = _positive("frame_wait_s", frame_wait_s)
        self.frames = frames
        if not isinstance(startup_deadlines_ns, dict) or any(type(v) is not int or v < 0 for v in startup_deadlines_ns.values()):
            raise ValueError("startup_deadlines_ns must map flow ids to non-negative ints (simulation ns after the origin)")
        unknown = set(startup_deadlines_ns) - set(self.schedule.flows)
        if unknown:
            raise ValueError(f"start-up deadlines for unknown flows {sorted(unknown)}")
        if F17 in self.schedule.flows and F17 not in startup_deadlines_ns:
            raise ValueError("a start-up deadline for f17-brake-command is required (no default; AD-07, WP-04 LOW-2)")
        self.deadlines = dict(startup_deadlines_ns)
        self.local_consumers = {k: list(v) for k, v in (local_consumers or {}).items()}
        for flow in self.schedule.flows.values():
            if flow["route"] == "hub" and any(d["unit"] == self.hub_unit for d in flow["destinations"]) \
                    and not self.local_consumers.get(flow["id"]):
                raise ValueError(f"flow {flow['id']} is delivered to the hub unit but has no local consumer")
        self.local_producers = tuple(local_producers)
        self.remote_units = sorted(u for u in topo["units"] if u not in (self.hub_unit, self.adapter_unit))
        self.link, self.command_source = link, command_source
        self.units = UnitLinks(units_socket_path, self.remote_units, send_timeout_s=self.wait_bound_s)
        self.live = set(self.remote_units)
        self.result = HubResult()
        self._origin = None
        self._delivered_flows: set[str] = set()
        self._lost_flows: set[str] = set()
        self._deadline_checked: set[str] = set()

    # ---- origin and verdicts ------------------------------------------------------------------------

    def close(self) -> None:
        """Close the frame receiver (WP-06 N1) and the unit links, bounded; idempotent. The adapter link belongs to the
        caller, which started it and stops or kills it (finding 4, L2)."""

        if self._closed:
            return
        self._closed = True
        try:
            if self.frames is not None:
                self.frames.close()
        finally:
            if self.units is not None:
                self.units.close()

    def _bind_origin(self, origin_ns: int) -> None:
        if self._origin is not None:
            if origin_ns != self._origin:
                raise HubProtocolError(f"episode origin {origin_ns} differs from the bound {self._origin}")
            return
        self._origin = self.result.episode_origin_ns = origin_ns
        for consumers in self.local_consumers.values():
            for consumer in consumers:
                if hasattr(consumer, "bind_origin"):
                    consumer.bind_origin(origin_ns)
        for unit in sorted(self.live):
            self.units.send(unit, {"type": "origin", "episodeOriginNs": origin_ns})

    def _mark_lost(self, flow_id: str, reason: str, step: int) -> None:
        if flow_id in self._lost_flows:
            return
        self._lost_flows.add(flow_id)
        self.result.lost.append({"step": step, "flowId": flow_id, "reason": reason})
        self.schedule.discard_flow(flow_id, step)  # barrier: nothing on this flow is delivered after the verdict
        flow = self.schedule.flows[flow_id]
        for dest in flow["destinations"]:
            if dest["unit"] == self.hub_unit:
                for consumer in self.local_consumers.get(flow_id, []):
                    if hasattr(consumer, "mark_lost"):
                        consumer.mark_lost()
            elif dest["unit"] in self.live:
                self.units.send(dest["unit"], {"type": "lost", "flowId": flow_id})

    def _unit_gone(self, unit: str, reason: str, step: int) -> None:
        if unit not in self.live:
            return
        self.live.discard(unit)
        self.result.invalid.append({"step": step, "unit": unit, "reason": reason})
        for flow in sorted(self.schedule.flows.values(), key=lambda f: f["id"]):
            if flow["source"]["unit"] == unit:
                self._mark_lost(flow["id"], f"producer {unit} {reason}", step)

    def _check_deadlines(self, step: int, sim_ns: int) -> None:
        for flow_id, deadline in sorted(self.deadlines.items()):
            if flow_id in self._deadline_checked or flow_id in self._delivered_flows:
                continue
            if sim_ns >= self._origin + deadline:
                self._deadline_checked.add(flow_id)
                self._mark_lost(flow_id, f"no message within the start-up deadline of {deadline} ns", step)

    # ---- delivery rounds ----------------------------------------------------------------------------

    def _deliver(self, step: int, rnd: int, items) -> dict[str, list]:
        per_unit: dict[str, list] = {}
        for item in items:
            flow = self.schedule.flows[item.flow]
            self._delivered_flows.add(item.flow)
            for dest in flow["destinations"]:
                entry = {"step": step, "round": rnd, "flowId": item.flow, "from": item.source_unit, "to": dest["unit"],
                         "sequence": item.sequence, "deliverAtNs": item.deliver_at_ns, "deliveredAtNs": self.schedule.boundaries[step],
                         "payloadSha256": hashlib.sha256(_canonical(item.message.get("payload"))).hexdigest()}
                self.result.deliveries.append(entry)
                if dest["unit"] == self.hub_unit:
                    for consumer in self.local_consumers.get(item.flow, []):
                        consumer.deliver(item.message)
                else:
                    per_unit.setdefault(dest["unit"], []).append(
                        {"flowId": item.flow, "from": item.source_unit, "sequence": item.sequence, "originNs": item.origin_ns,
                         "deliverAtNs": item.deliver_at_ns, "payload": item.message.get("payload")})
        return per_unit

    def _round(self, step: int, rnd: int, per_unit: dict, recipients) -> None:
        sim_ns = self.schedule.boundaries[step]
        targets = sorted(u for u in recipients if u in self.live)
        for unit in targets:
            if not self.units.send(unit, {"type": "round", "step": step, "round": rnd, "simNs": sim_ns, "deliveries": per_unit.get(unit, [])}):
                self._unit_gone(unit, f"send failed: {self.units.failed.get(unit, 'link closed')}", step)
        deadline = time.monotonic() + self.wait_bound_s
        for unit in targets:
            if unit not in self.live:
                continue
            while True:
                try:
                    kind, message = self.units.inbox[unit].get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    self.result.invalid.append({"step": step, "unit": unit, "reason": f"missed the {self.wait_bound_s} s wait bound"})
                    raise HubInvalidRun(f"unit {unit} missed the consumer wait bound at step {step} round {rnd}") from None
                if kind != "message":
                    self._unit_gone(unit, "disconnected" if kind == "eof" else f"protocol error: {message}", step)
                    break
                if message.get("type") != "outputs" or message.get("step") != step or message.get("round") != rnd:
                    self.result.refused.append({"step": step, "unit": unit, "reason": "unexpected or late message"})
                    continue
                outputs = message.get("messages")
                if type(outputs) is not list:  # finding 4, L3: a protocol error of this unit
                    self._unit_gone(unit, "protocol error: outputs.messages is not a list", step)
                    break
                for out in outputs:
                    self.schedule.admit(step, unit, out)
                break

    def _rounds(self, step: int) -> None:
        cap = len(self.schedule.topology["units"]) + 1
        rnd = 0
        recipients = set(self.live)  # round 0 reaches every live unit, deliveries or not
        while True:
            per_unit = self._deliver(step, rnd, self.schedule.due(step))
            if rnd > 0:
                recipients = set(per_unit)
            if recipients & self.live:
                self._round(step, rnd, per_unit, recipients)
            self.result.max_rounds = max(self.result.max_rounds, rnd + 1)
            if not any(p.first_step is not None and p.first_step + self.schedule.flows[p.flow]["hubDelaySteps"] <= step
                       for p in self.schedule._pending):
                return
            rnd += 1
            if rnd >= cap:
                raise HubInvalidRun(f"step {step}: more than {cap} delivery rounds (an undeclared cross-unit cycle)")

    # ---- the step loop ------------------------------------------------------------------------------

    def hold(self, condition: Callable[[], bool], poll_s: float = 0.005) -> None:
        """Hold the simulator step (no tick) until ``condition()`` is true, within ``hold_bound_s``."""

        deadline = time.monotonic() + self.hold_bound_s
        while not condition():
            if time.monotonic() >= deadline:
                raise HubInvalidRun(f"step hold exceeded its {self.hold_bound_s} s bound")
            time.sleep(poll_s)

    def run(self, max_steps: int) -> HubResult:
        """Run at most ``max_steps`` adapter ticks; always close the frame receiver and the unit links."""

        sim_s, last_motion = 0.0, None
        try:
            self.units.accept_all(self.connect_timeout_s)
            for tick in range(max_steps):
                throttle, brake, _meta = self.command_source(sim_s, last_motion)
                self.link.command(f"t{tick}", brake, 1, throttle)
                step_result = self.link.tick()
                if step_result.done is not None:
                    self.result.end_reason = "adapter-done"
                    break
                items = step_result.items
                motion = next((i for i in items if i["flowId"] == "vehicle-motion"), None)
                if motion is None:  # finding 4, L5: the boundary is the vehicle-motion origin only; flagged, no step
                    self.result.boundary_gaps.append({"tick": tick, "items": sorted(i["flowId"] for i in items),
                                                      "reason": "no vehicle-motion item: no step boundary"})
                    continue
                frame_ns = motion["originNs"]
                step = self.schedule.boundary(frame_ns)
                if self._origin is None:  # late binding at the first frame, before any consumer runs
                    self._bind_origin(frame_ns)
                sim_s = (frame_ns - self._origin) / 1e9
                if motion is not None:
                    last_motion = motion
                camera = next((i for i in items if i["flowId"] == "camera"), None)
                frame = self.frames.take(camera, wait_s=self.frame_wait_s) if self.frames is not None and camera is not None else None
                if frame is not None:
                    self.result.frames.append(frame.record())
                for flow_id, item in (("f01-camera-raw", {"item": camera, "frame": frame} if camera else None),
                                      ("f02-radar-raw", next((i for i in items if i["flowId"] == "radar-adas"), None)),
                                      ("f03-motion-raw", motion)):
                    if item is not None:
                        for consumer in self.local_consumers.get(flow_id, []):
                            consumer.deliver(item)
                for producer in self.local_producers:
                    for message in producer(step, frame_ns, items) or ():
                        self.schedule.admit(step, self.hub_unit, message)
                self._rounds(step)
                self._check_deadlines(step, frame_ns)  # after the step's rounds: a delivery in this step counts
                self.result.steps += 1
            else:
                self.result.end_reason = "max-steps"
        finally:
            self.result.refused = self.result.refused + self.schedule.refused
            self.result.discarded = list(self.schedule.discarded)
            self.close()  # WP-06 N1: the frame receiver always; the unit links within their bound
        return self.result
