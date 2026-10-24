"""Phase 8 WP-10 #2: the U2 hub core without faults (review-wp10-hub finding 1), offline.

Fake units are threads speaking ``xverse-compat.hub-units/1`` over real Unix sockets. The adapter is a fake link,
except in one end-to-end test with the pinned 3.10 adapter on a fake source and the WP-06 frame receiver. Every
bound, deadline and latency here is a test-only value; none is a protocol value.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import socket
import subprocess
import threading
import time

import pytest

from xverse_compat.carla_client import SocketAdapterLink, TickResult
from xverse_compat.live.frames import FrameReceiver
from xverse_compat.live.hub import F17, MAX_LINE, PROTOCOL, Hub, HubInvalidRun, HubProtocolError, HubSchedule, UnitLinks
from xverse_compat.live.hub_topology import SCHEMA, TopologyError, from_system_document, validate

from ..carla.support import DESCRIPTORS, FIXTURES, ROOT, require_env
from .test_phase7_live import _socket_path

STEP = 50_000_000  # 0.05 s fixed step (K-10)
T0 = 10_000_000_000
FORM = Path(__file__).resolve().parent / "fixtures" / "wp10-topology-mloc-5f71cde.json"


def _flow(fid, src, dsts, delay=0, route="hub"):
    return {"id": fid, "source": src, "destinations": dsts, "route": route, "hubDelaySteps": delay, "returnFlow": False}


def _e(element, unit):
    return {"element": element, "unit": unit}


SMALL = {"schema": SCHEMA, "arm": "test", "hubUnit": "u2", "adapterUnit": "u1",
         "units": {"u1": ["carla-client"], "u2": ["loop-gateway", "objective-source"], "ua": ["a"], "ub": ["b"], "uc": ["c"]},
         "flows": [_flow("f-hub-a", _e("objective-source", "u2"), [_e("a", "ua")]),
                   _flow("f-a-b", _e("a", "ua"), [_e("b", "ub")]),
                   _flow("f-b-c", _e("b", "ub"), [_e("c", "uc")]),
                   _flow("f-c-a", _e("c", "uc"), [_e("a", "ua")], delay=1),  # the declared cycle breaker
                   _flow(F17, _e("c", "uc"), [_e("loop-gateway", "u2")], delay=1)]}


class Reader:
    """A local consumer with the BrakeCommandReader surface."""

    def __init__(self):
        self.messages, self.origins, self.lost = [], [], 0

    def deliver(self, message):
        self.messages.append(message)

    def bind_origin(self, ns):
        self.origins.append(ns)

    def mark_lost(self):
        self.lost += 1


class FakeLink:
    """Adapter link stand-in: frame k at T0 + k·STEP; ``empty`` ticks carry no items; then done."""

    def __init__(self, frames, empty=(), no_motion=()):
        self.frames, self.empty, self.no_motion, self.tick_count, self.commands = frames, set(empty), set(no_motion), 0, []
        self.owner_calls = []

    def stop(self):
        self.owner_calls.append("stop")

    def kill(self):
        self.owner_calls.append("kill")

    def command(self, command_id, brake, deadline_frames, throttle=0.0):
        self.commands.append((command_id, throttle, brake))

    def tick(self):
        n = self.tick_count
        self.tick_count += 1
        if n >= self.frames:
            return TickResult(done={"type": "status", "state": "done"})
        if n in self.empty:
            return TickResult(frame=None, items=[])
        origin = T0 + n * STEP
        if n in self.no_motion:
            return TickResult(frame=n, items=[{"flowId": "radar-adas", "sequence": n, "originNs": origin, "frame": n,
                                                "value": {"count": 0}}])
        return TickResult(frame=n, items=[{"flowId": "vehicle-motion", "sequence": n, "originNs": origin, "frame": n,
                                            "value": {"speedMps": 1.0, "accelForwardMps2": 0.0}}])


class FakeUnit(threading.Thread):
    """Answers every round; ``produce(unit, step, rnd, sim_ns, deliveries, seq)`` returns its outputs."""

    def __init__(self, path, unit, produce, jitter_seed=None, disconnect_after=None, silent_at=None):
        super().__init__(daemon=True)
        self.path, self.unit, self.produce = path, unit, produce
        self.rng = random.Random(jitter_seed) if jitter_seed is not None else None
        self.disconnect_after, self.silent_at = disconnect_after, silent_at
        self.origin, self.lost, self.rounds, self.order = None, [], [], []
        self.seq = {}

    def run(self):
        deadline = time.monotonic() + 10
        while True:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self.path)
                break
            except OSError:
                sock.close()
                if time.monotonic() > deadline:
                    return
                time.sleep(0.01)
        reader, writer = sock.makefile("rb"), sock.makefile("wb")
        writer.write(json.dumps({"type": "hello", "protocol": PROTOCOL, "unit": self.unit}).encode() + b"\n")
        writer.flush()
        for line in reader:
            msg = json.loads(line)
            self.order.append(msg["type"])
            if msg["type"] == "origin":
                self.origin = msg["episodeOriginNs"]
            elif msg["type"] == "lost":
                self.lost.append(msg["flowId"])
            elif msg["type"] == "end":
                break
            elif msg["type"] == "round":
                self.rounds.append((msg["step"], msg["round"], [(d["flowId"], d["sequence"]) for d in msg["deliveries"]]))
                if self.disconnect_after is not None and msg["step"] > self.disconnect_after:
                    break
                if self.silent_at is not None and msg["step"] == self.silent_at:
                    continue
                if self.rng:
                    time.sleep(self.rng.random() * 0.01)
                outputs = self.produce(self, msg["step"], msg["round"], msg["simNs"], msg["deliveries"])
                writer.write(json.dumps({"type": "outputs", "step": msg["step"], "round": msg["round"], "messages": outputs}).encode() + b"\n")
                writer.flush()
        sock.close()

    def message(self, flow, origin, deliver, payload=None):
        self.seq[flow] = self.seq.get(flow, -1) + 1
        return {"flowId": flow, "sequence": self.seq[flow], "originNs": origin, "deliverAtNs": deliver, "payload": payload}


def _emit_round0(flows_by_unit, latency=0):
    """Each unit emits one message per source flow in round 0 of every step (no chaining)."""

    def produce(unit, step, rnd, sim_ns, deliveries):
        if rnd != 0:
            return []
        return [unit.message(f, sim_ns, sim_ns + latency, {"step": step}) for f in flows_by_unit.get(unit.unit, [])]
    return produce


def _hub(topology, path, link, units_spec, deadlines=None, local_consumers=None, producers=(), wait=2.0, **kw):
    hub = Hub(topology, link=link, units_socket_path=path, command_source=lambda s, m: (0.0, 0.0, {}), wait_bound_s=wait,
              hold_bound_s=kw.pop("hold", 0.5), startup_deadlines_ns=deadlines if deadlines is not None else {F17: 10 * STEP},
              connect_timeout_s=5, local_consumers=local_consumers, local_producers=producers, **kw)
    units = [FakeUnit(path, u, produce, **opts) for u, produce, opts in units_spec]
    for u in units:
        u.start()
    return hub, units


def _hub_producer(flows, latency=0):
    seq = {}

    def produce(step, sim_ns, items):
        out = []
        for f in flows:
            seq[f] = seq.get(f, -1) + 1
            out.append({"flowId": f, "sequence": seq[f], "originNs": sim_ns, "deliverAtNs": sim_ns + latency, "payload": {"step": step}})
        return out
    return produce


# ---- topology contract -------------------------------------------------------------------------------


def test_wp10_contract_from_the_5f71cde_topology_form_pins_the_delay_points():
    record = validate(from_system_document(json.loads(FORM.read_text())))
    assert record["arm"] == "mloc" and record["hubUnit"] == "vehicle-loop-unit" and record["adapterUnit"] == "carla-adapter-unit"
    delays = {f["id"]: f["hubDelaySteps"] for f in record["flows"] if f["hubDelaySteps"]}
    assert delays == {"f04-actuation-command": 1, "f14-authorization": 1, "f15b-configuration-state-proposer": 1, F17: 1}
    routes = {f["id"]: f["route"] for f in record["flows"]}
    assert {k for k, v in routes.items() if v == "adapter-link"} == {"f01-camera-raw", "f02-radar-raw", "f03-motion-raw", "f04-actuation-command"}
    assert len(record["flows"]) == 20 and not any("intra" in f["id"] for f in record["flows"])


@pytest.mark.parametrize("mutate", [
    lambda d: d["spec"]["endpoints"].pop(0),
    lambda d: d["spec"]["flows"].append(dict(d["spec"]["flows"][0])),
    lambda d: d["spec"]["flows"][13]["extensions"]["io.xverse.assured-aeb"].update(hubDelay={"unit": "tick", "value": 1}),
    lambda d: d.pop("extensions"),
])
def test_wp10_an_inconsistent_topology_form_is_refused(mutate):
    doc = json.loads(FORM.read_text())
    mutate(doc)
    with pytest.raises(TopologyError):
        validate(from_system_document(doc))


# ---- schedule core (pure) ----------------------------------------------------------------------------


def test_wp10_delivery_is_rounded_up_to_the_next_step_boundary_plus_the_hub_delay():
    schedule = HubSchedule(SMALL)
    schedule.boundary(T0)
    msg = lambda flow, seq, deliver: {"flowId": flow, "sequence": seq, "originNs": T0, "deliverAtNs": deliver}  # noqa: E731
    assert schedule.admit(0, "ua", msg("f-a-b", 0, T0))  # due in its own step: a later round
    assert schedule.admit(0, "ua", msg("f-a-b", 1, T0 + 20_000_000))  # between boundaries: the next one
    assert schedule.admit(0, "ua", msg("f-a-b", 2, T0 + 60_000_000))  # beyond the next boundary: two steps
    assert schedule.admit(0, "uc", msg("f-c-a", 0, T0))  # delay point: one step later
    assert schedule.admit(0, "uc", msg(F17, 0, T0 + 20_000_000))  # rounded to step 1, plus the delay: step 2
    got = {}
    for k in range(4):
        if k:
            schedule.boundary(T0 + k * STEP)
        got[k] = [(p.flow, p.sequence) for p in schedule.due(k)]
    assert got == {0: [("f-a-b", 0)], 1: [("f-a-b", 1), ("f-c-a", 0)], 2: [("f-a-b", 2), (F17, 0)], 3: []}  # ordered by flow id


@pytest.mark.parametrize("message, reason", [
    ({"flowId": "f-a-b", "sequence": 0, "originNs": T0 + 1, "deliverAtNs": T0 + 1}, "future origin"),
    ({"flowId": "f-a-b", "sequence": 0, "originNs": T0, "deliverAtNs": T0 - 1}, "deliverAtNs before"),
    ({"flowId": "f-b-c", "sequence": 0, "originNs": T0, "deliverAtNs": T0}, "does not host"),
    ({"flowId": "f-x", "sequence": 0, "originNs": T0, "deliverAtNs": T0}, "unknown"),
    ({"flowId": "f-a-b", "sequence": True, "originNs": T0, "deliverAtNs": T0}, "non-negative ints"),
])
def test_wp10_non_conforming_stamps_are_refused_and_counted(message, reason):
    schedule = HubSchedule(SMALL)
    schedule.boundary(T0)
    assert not schedule.admit(0, "ua", message) and reason in schedule.refused[-1]["reason"]


def test_wp10_a_repeated_sequence_is_refused():
    schedule = HubSchedule(SMALL)
    schedule.boundary(T0)
    m = {"flowId": "f-a-b", "sequence": 3, "originNs": T0, "deliverAtNs": T0}
    assert schedule.admit(0, "ua", m) and not schedule.admit(0, "ua", dict(m)) and schedule.pending() == 1


# ---- hub over fake units -----------------------------------------------------------------------------


def _small_units(path, jitter=None, **opts):
    flows = {"ua": ["f-a-b"], "ub": ["f-b-c"], "uc": ["f-c-a", F17]}
    produce = _emit_round0(flows)
    return [(u, produce, dict(jitter_seed=None if jitter is None else jitter + i, **opts.get(u, {}))) for i, u in enumerate(("ua", "ub", "uc"))]


def _run_small(jitter=None, frames=5, **opts):
    path = _socket_path()
    reader = Reader()
    hub, units = _hub(SMALL, path, FakeLink(frames), _small_units(path, jitter, **opts), local_consumers={F17: [reader]},
                      producers=(_hub_producer(["f-hub-a"]),))
    result = hub.run(max_steps=frames + 1)
    for u in units:
        u.join(5)
    return result, units, reader


def test_wp10_the_same_inputs_give_the_same_delivery_schedule_whatever_the_answer_order():
    first, _, _ = _run_small(jitter=1)
    second, _, _ = _run_small(jitter=101)
    assert first.deliveries and first.deliveries == second.deliveries and first.end_reason == second.end_reason == "adapter-done"


def test_wp10_same_step_rounds_and_one_step_delay_points():
    result, units, reader = _run_small()
    by_flow = {}
    for d in result.deliveries:
        by_flow.setdefault(d["flowId"], []).append((d["step"], d["round"], d["sequence"]))
    assert by_flow["f-hub-a"][:2] == [(0, 0, 0), (1, 0, 1)]  # hub-produced, due in its step: round 0
    assert by_flow["f-a-b"][:2] == [(0, 1, 0), (1, 1, 1)]  # zero-latency chain: the next round of the same step
    assert by_flow["f-b-c"][:2] == [(0, 1, 0), (1, 1, 1)]
    assert by_flow["f-c-a"][:2] == [(1, 0, 0), (2, 0, 1)]  # delay point: one step later
    assert by_flow[F17][:2] == [(1, 0, 0), (2, 0, 1)] and [m["sequence"] for m in reader.messages][:2] == [0, 1]
    assert result.max_rounds == 2 and result.invalid == [] and result.lost == []


def test_wp10_the_real_topology_delays_f14_f15b_and_f17_by_one_step():
    record = validate(from_system_document(json.loads(FORM.read_text())))
    hub_unit = record["hubUnit"]
    sources = {}
    for f in record["flows"]:
        if f["route"] == "hub":
            sources.setdefault(f["source"]["unit"], []).append(f["id"])
    path = _socket_path()
    consumers = {F17: [Reader()], "f18-mrc-request": [Reader()]}
    spec = [(u, _emit_round0(sources), {}) for u in sorted(record["units"]) if u not in (hub_unit, record["adapterUnit"])]
    hub, units = _hub(record, path, FakeLink(4), spec, local_consumers=consumers, producers=(_hub_producer(sources[hub_unit]),))
    result = hub.run(max_steps=5)
    for u in units:
        u.join(5)
    first = {}
    for d in result.deliveries:
        first.setdefault(d["flowId"], d["step"])
    delayed = {"f14-authorization", "f15b-configuration-state-proposer", F17}
    assert all(first[f] == 1 for f in delayed) and all(first[f] == 0 for f in first if f not in delayed)
    assert set(first) == {f["id"] for f in record["flows"] if f["route"] == "hub"} and result.invalid == []


def test_wp10_origin_is_bound_late_at_the_first_frame_and_sent_before_any_round():
    path = _socket_path()
    reader = Reader()
    hub, units = _hub(SMALL, path, FakeLink(4, empty=(0, 1)), _small_units(path), local_consumers={F17: [reader]})
    result = hub.run(max_steps=5)
    for u in units:
        u.join(5)
    assert result.episode_origin_ns == T0 + 2 * STEP and reader.origins == [T0 + 2 * STEP]  # ticks 0 and 1 had no frame
    assert all(u.origin == T0 + 2 * STEP and u.order[0] == "origin" for u in units)  # before every round
    assert min(d["deliveredAtNs"] for d in result.deliveries) >= T0 + 2 * STEP
    with pytest.raises(HubProtocolError, match="differs from the bound"):
        hub._bind_origin(T0)


def test_wp10_a_disconnected_producer_gives_lost_verdicts_and_an_invalid_run():
    result, units, reader = _run_small(frames=6, uc={"disconnect_after": 1})
    lost = {(x["flowId"], x["reason"].split(" ")[0]) for x in result.lost}
    assert {("f-c-a", "producer"), (F17, "producer")} <= lost
    assert reader.lost == 1  # the local F17 consumer, once
    assert "f-c-a" in next(u for u in units if u.unit == "ua").lost  # the remote consumer of f-c-a
    assert any(x["unit"] == "uc" for x in result.invalid)


def test_wp10_no_f17_within_the_startup_deadline_is_lost_once():
    path = _socket_path()
    reader = Reader()
    flows = {"ua": ["f-a-b"], "ub": ["f-b-c"], "uc": ["f-c-a"]}  # uc never sends F17
    spec = [(u, _emit_round0(flows), {}) for u in ("ua", "ub", "uc")]
    hub, units = _hub(SMALL, path, FakeLink(6), spec, deadlines={F17: 2 * STEP}, local_consumers={F17: [reader]})
    result = hub.run(max_steps=7)
    for u in units:
        u.join(5)
    assert [(x["flowId"], x["step"]) for x in result.lost] == [(F17, 2)] and reader.lost == 1
    assert result.invalid == []  # a missing first F17 is a verdict, not an invalid hub


def test_wp10_an_f17_in_time_is_not_lost():
    result, _, reader = _run_small(frames=6)
    assert result.lost == [] and reader.lost == 0 and reader.messages


@pytest.mark.parametrize("deadlines", [{}, {F17: -1}, {F17: 1.5}, {"f-unknown": 1, F17: 1}])
def test_wp10_the_startup_deadline_has_no_default(deadlines):
    with pytest.raises(ValueError):
        Hub(SMALL, link=FakeLink(1), units_socket_path=_socket_path(), command_source=lambda s, m: (0, 0, {}), wait_bound_s=1,
            hold_bound_s=1, startup_deadlines_ns=deadlines, connect_timeout_s=1, local_consumers={F17: [Reader()]})


@pytest.mark.parametrize("name", ["wait_bound_s", "hold_bound_s", "connect_timeout_s"])
@pytest.mark.parametrize("value", [None, 0, -1, float("inf")])
def test_wp10_bounds_are_required_and_positive(name, value):
    kwargs = dict(wait_bound_s=1, hold_bound_s=1, connect_timeout_s=1)
    kwargs[name] = value
    with pytest.raises(ValueError):
        Hub(SMALL, link=FakeLink(1), units_socket_path=_socket_path(), command_source=lambda s, m: (0, 0, {}),
            startup_deadlines_ns={F17: 1}, local_consumers={F17: [Reader()]}, **kwargs)


def test_wp10_a_flow_to_the_hub_unit_needs_a_local_consumer():
    with pytest.raises(ValueError, match="no local consumer"):
        Hub(SMALL, link=FakeLink(1), units_socket_path=_socket_path(), command_source=lambda s, m: (0, 0, {}), wait_bound_s=1,
            hold_bound_s=1, startup_deadlines_ns={F17: 1}, connect_timeout_s=1)


class FakeFrames:
    def __init__(self):
        self.closed = 0

    def take(self, item, wait_s):
        raise AssertionError("no camera items in this test")

    def close(self):
        self.closed += 1


def test_wp10_a_missed_wait_bound_is_an_invalid_run_and_the_frame_receiver_is_closed():
    path = _socket_path()
    frames = FakeFrames()
    hub, units = _hub(SMALL, path, FakeLink(5), _small_units(path, ub={"silent_at": 1}), local_consumers={F17: [Reader()]},
                      wait=0.3, frames=frames, frame_wait_s=1)
    with pytest.raises(HubInvalidRun, match="ub missed the consumer wait bound at step 1"):
        hub.run(max_steps=6)
    assert frames.closed == 1 and hub.result.invalid[-1]["unit"] == "ub"


def test_wp10_the_frame_receiver_is_closed_on_success_too():
    path = _socket_path()
    frames = FakeFrames()
    hub, units = _hub(SMALL, path, FakeLink(3), _small_units(path), local_consumers={F17: [Reader()]}, frames=frames, frame_wait_s=1)
    hub.run(max_steps=4)
    assert frames.closed == 1


def test_wp10_the_step_hold_is_bounded():
    path = _socket_path()
    hub, units = _hub(SMALL, path, FakeLink(1), [], local_consumers={F17: [Reader()]}, hold=0.3)
    flag = []
    threading.Timer(0.05, lambda: flag.append(1)).start()
    hub.hold(lambda: bool(flag))  # released by the condition
    started = time.monotonic()
    with pytest.raises(HubInvalidRun, match="step hold exceeded"):
        hub.hold(lambda: False)
    assert 0.25 <= time.monotonic() - started <= 0.6
    hub.units.close()


# ---- end to end with the pinned 3.10 adapter and the WP-06 frame receiver ----------------------------


ADAPTER_ONLY = {"schema": SCHEMA, "arm": "test", "hubUnit": "u2", "adapterUnit": "u1",
                "units": {"u1": ["carla-client"], "u2": ["loop-gateway", "camera-imaging-stage"]},
                "flows": [_flow("f01-camera-raw", _e("carla-client", "u1"), [_e("camera-imaging-stage", "u2")], route="adapter-link")]}


def test_wp10_end_to_end_the_hub_ticks_the_adapter_and_verifies_every_frame(tmp_path):
    link_path, frames_path = _socket_path(), _socket_path()
    fmt = {"schema": "xverse-compat.camera-frame-format/1", "width": 800, "height": 600, "encoding": "bgra8"}  # test-only
    (tmp_path / "fmt.json").write_text(json.dumps(fmt))
    link = SocketAdapterLink(link_path, DESCRIPTORS)
    receiver = FrameReceiver(frames_path, fmt)
    proc = subprocess.Popen(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                             "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + link_path, "--source",
                             f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), "--frames", "unix:" + frames_path,
                             "--frame-format", str(tmp_path / "fmt.json")], cwd=ROOT / "src", stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    link.start(accept_timeout_s=30)
    receiver.start(accept_timeout_s=30)
    camera = Reader()
    hub = Hub(ADAPTER_ONLY, link=link, units_socket_path=_socket_path(), command_source=lambda s, m: (0.0, 0.0, {}), wait_bound_s=1,
              hold_bound_s=1, startup_deadlines_ns={}, connect_timeout_s=1, frames=receiver, frame_wait_s=10,
              local_consumers={"f01-camera-raw": [camera]})
    result = hub.run(max_steps=10)
    assert proc.wait(timeout=30) == 0 and result.end_reason == "adapter-done" and result.steps == 4
    assert [f["status"] for f in result.frames] == ["verified"] * 4 and camera.origins == [10_000_000_000]
    assert [m["frame"].status for m in camera.messages] == ["verified"] * 4
    assert receiver.path.exists() is False  # FrameReceiver.close() ran (it unlinks its socket)
    link.kill()


# ---- finding 4 repairs -------------------------------------------------------------------------------


def _raw_unit(path, unit, read=False):
    """A unit that connects, says hello and then never reads (or reads and never answers)."""

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + 5
    while True:
        try:
            sock.connect(path)
            break
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)
    sock.sendall(json.dumps({"type": "hello", "protocol": PROTOCOL, "unit": unit}).encode() + b"\n")
    return sock


def test_wp10_m1_a_unit_that_never_reads_cannot_block_send_or_close_beyond_the_bound():
    path = _socket_path()
    links = UnitLinks(path, ["ux"], send_timeout_s=0.2)
    holder = {}
    threading.Thread(target=lambda: holder.setdefault("sock", _raw_unit(path, "ux")), daemon=True).start()
    links.accept_all(5)
    big = {"type": "round", "padding": "x" * 60_000}
    results, worst = [], 0.0
    for _ in range(200):  # the kernel buffer fills: the first send that cannot complete returns False within the bound
        started = time.monotonic()
        results.append(links.send("ux", big))
        worst = max(worst, time.monotonic() - started)
        if not results[-1]:
            break
    assert results[-1] is False and worst <= 0.4 and "send bound exceeded" in links.failed["ux"]
    links2_path = _socket_path()
    links2 = UnitLinks(links2_path, ["uy"], send_timeout_s=0.2)
    threading.Thread(target=lambda: holder.setdefault("sock2", _raw_unit(links2_path, "uy")), daemon=True).start()
    links2.accept_all(5)
    conn = links2._conns["uy"]
    conn.setblocking(False)
    try:
        while True:  # fill the peer's buffer without closing the unit
            conn.send(b"x" * 65536)
    except BlockingIOError:
        pass
    conn.setblocking(True)
    started = time.monotonic()
    links2.close(timeout_s=0.3)  # ``end`` cannot be written: the close still returns within its bound
    assert time.monotonic() - started <= 0.6 and not Path(links2_path).exists()
    links.close(timeout_s=0.3)


def test_wp10_m1_a_hub_with_a_non_reading_unit_ends_within_its_bounds():
    path = _socket_path()
    topo = dict(SMALL, units={"u1": ["carla-client"], "u2": ["loop-gateway", "objective-source"], "ua": ["a"]},
                flows=[_flow("f-hub-a", _e("objective-source", "u2"), [_e("a", "ua")])])
    hub = Hub(topo, link=FakeLink(5), units_socket_path=path, command_source=lambda s, m: (0.0, 0.0, {}), wait_bound_s=0.3,
              hold_bound_s=0.3, startup_deadlines_ns={}, connect_timeout_s=5, local_producers=(_hub_producer(["f-hub-a"]),))
    holder = {}  # keep the socket open: a silent unit, not a disconnected one
    threading.Thread(target=lambda: holder.setdefault("sock", _raw_unit(path, "ua")), daemon=True).start()
    started = time.monotonic()
    with pytest.raises(HubInvalidRun, match="missed the consumer wait bound"):
        hub.run(max_steps=6)
    assert time.monotonic() - started <= 2.0 and not Path(path).exists()


def test_wp10_m2_a_lost_flow_is_a_barrier_for_a_message_queued_ahead():
    path = _socket_path()
    reader = Reader()

    def uc_produce(unit, step, rnd, sim_ns, deliveries):
        if step == 0 and rnd == 0:  # an F17 queued three steps ahead, then the producer disconnects
            return [unit.message(F17, sim_ns, sim_ns + 3 * STEP)]
        return []
    spec = [("ua", _emit_round0({}), {}), ("ub", _emit_round0({}), {}), ("uc", uc_produce, {"disconnect_after": 0})]
    hub, units = _hub(SMALL, path, FakeLink(6), spec, local_consumers={F17: [reader]})
    result = hub.run(max_steps=7)
    for u in units:
        u.join(5)
    assert reader.lost == 1 and reader.messages == []  # never delivered after the verdict (decisions.md "Lost-flow rule")
    assert not any(d["flowId"] == F17 for d in result.deliveries)
    assert [(d["flowId"], d["sequence"], d["reason"]) for d in result.discarded] == [(F17, 0, "pending at the lost verdict")]
    assert result.discarded[0]["payloadSha256"] and result.lost[0]["flowId"] in {F17, "f-c-a"}


def test_wp10_m2_after_a_startup_deadline_loss_a_late_f17_is_discarded():
    path = _socket_path()
    reader = Reader()

    def uc_produce(unit, step, rnd, sim_ns, deliveries):
        return [unit.message(F17, sim_ns, sim_ns)] if rnd == 0 and step >= 3 else []
    spec = [("ua", _emit_round0({}), {}), ("ub", _emit_round0({}), {}), ("uc", uc_produce, {})]
    hub, units = _hub(SMALL, path, FakeLink(6), spec, deadlines={F17: STEP}, local_consumers={F17: [reader]})
    result = hub.run(max_steps=7)
    for u in units:
        u.join(5)
    assert [(x["flowId"], x["step"]) for x in result.lost] == [(F17, 1)] and reader.messages == []
    assert {d["reason"] for d in result.discarded} == {"admitted after the lost verdict"} and len(result.discarded) == 3


def _forwarder(forward):
    """Produce on ``forward[flow_in]`` for every delivery received on ``flow_in``, in any round (chaining)."""

    def produce(unit, step, rnd, sim_ns, deliveries):
        out = [unit.message(forward[d["flowId"]], sim_ns, sim_ns) for d in deliveries if d["flowId"] in forward]
        return out
    return produce


def test_wp10_l1_zero_delay_chains_run_in_rounds_and_a_declared_delay_ends_them():
    path = _socket_path()
    spec = [("ua", _forwarder({"f-hub-a": "f-a-b"}), {}), ("ub", _forwarder({"f-a-b": "f-b-c"}), {}),
            ("uc", _forwarder({"f-b-c": "f-c-a"}), {})]
    hub, units = _hub(SMALL, path, FakeLink(3), spec, deadlines={F17: 100 * STEP}, local_consumers={F17: [Reader()]},
                      producers=(_hub_producer(["f-hub-a"]),))
    result = hub.run(max_steps=4)
    for u in units:
        u.join(5)
    rounds = {(d["flowId"], d["step"]): d["round"] for d in result.deliveries}
    assert rounds[("f-hub-a", 0)] == 0 and rounds[("f-a-b", 0)] == 1 and rounds[("f-b-c", 0)] == 2
    assert rounds[("f-c-a", 1)] == 0 and result.max_rounds == 3  # the delay point ends the chain at the step


def test_wp10_l1_an_undeclared_zero_delay_cycle_hits_the_round_cap():
    cyclic = json.loads(json.dumps(SMALL))
    next(f for f in cyclic["flows"] if f["id"] == "f-c-a")["hubDelaySteps"] = 0  # the cycle breaker removed
    path = _socket_path()
    spec = [("ua", _forwarder({"f-hub-a": "f-a-b", "f-c-a": "f-a-b"}), {}), ("ub", _forwarder({"f-a-b": "f-b-c"}), {}),
            ("uc", _forwarder({"f-b-c": "f-c-a"}), {})]
    hub, units = _hub(cyclic, path, FakeLink(3), spec, deadlines={F17: 100 * STEP}, local_consumers={F17: [Reader()]},
                      producers=(_hub_producer(["f-hub-a"]),))
    with pytest.raises(HubInvalidRun, match="more than 6 delivery rounds"):
        hub.run(max_steps=4)


def test_wp10_l2_the_adapter_link_belongs_to_the_caller():
    result, units, reader = _run_small(frames=3)
    path = _socket_path()
    link = FakeLink(2)
    hub, units = _hub(SMALL, path, link, _small_units(path), local_consumers={F17: [Reader()]})
    hub.run(max_steps=3)
    assert link.owner_calls == []  # the hub never stops or kills the link; the caller does


def test_wp10_l3_a_malformed_outputs_field_is_a_protocol_error_of_that_unit():
    path = _socket_path()
    reader = Reader()

    spec = [("ua", _emit_round0({}), {}), ("ub", _emit_round0({}), {}),
            ("uc", lambda unit, step, rnd, sim_ns, d: 5 if step == 1 else [], {})]
    hub, units = _hub(SMALL, path, FakeLink(4), spec, local_consumers={F17: [reader]})
    result = hub.run(max_steps=5)
    assert any(x["unit"] == "uc" and "not a list" in x["reason"] for x in result.invalid) and reader.lost == 1


def test_wp10_l4_an_outbound_line_above_the_limit_is_refused_at_the_hub():
    path = _socket_path()

    def huge(step, sim_ns, items):
        return [{"flowId": "f-hub-a", "sequence": step, "originNs": sim_ns, "deliverAtNs": sim_ns, "payload": "x" * (MAX_LINE + 1)}]
    hub, units = _hub(SMALL, path, FakeLink(3), _small_units(path), local_consumers={F17: [Reader()]}, producers=(huge,))
    with pytest.raises(HubProtocolError, match="above 65536"):
        hub.run(max_steps=4)


def test_wp10_l5_a_tick_without_vehicle_motion_is_flagged_and_gives_no_step():
    path = _socket_path()
    hub, units = _hub(SMALL, path, FakeLink(4, no_motion=(1,)), _small_units(path), local_consumers={F17: [Reader()]})
    result = hub.run(max_steps=5)
    assert result.boundary_gaps == [{"tick": 1, "items": ["radar-adas"], "reason": "no vehicle-motion item: no step boundary"}]
    assert result.steps == 3 and T0 + STEP not in {d["deliveredAtNs"] for d in result.deliveries}


def test_wp10_l7_a_refused_construction_closes_the_frame_receiver_and_close_without_run_releases_all():
    frames = FakeFrames()
    with pytest.raises(ValueError):
        Hub(SMALL, link=FakeLink(1), units_socket_path=_socket_path(), command_source=lambda s, m: (0, 0, {}), wait_bound_s=None,
            hold_bound_s=1, startup_deadlines_ns={F17: 1}, connect_timeout_s=1, frames=frames, frame_wait_s=1,
            local_consumers={F17: [Reader()]})
    assert frames.closed == 1
    frames2, path = FakeFrames(), _socket_path()
    hub = Hub(SMALL, link=FakeLink(1), units_socket_path=path, command_source=lambda s, m: (0, 0, {}), wait_bound_s=1,
              hold_bound_s=1, startup_deadlines_ns={F17: 1}, connect_timeout_s=1, frames=frames2, frame_wait_s=1,
              local_consumers={F17: [Reader()]})
    assert Path(path).exists()
    hub.close()
    hub.close()  # idempotent
    assert frames2.closed == 1 and not Path(path).exists()
