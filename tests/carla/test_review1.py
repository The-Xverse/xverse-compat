"""Implementation review 1 repairs: M1, M2, M4 and LOW items L1, L5 and L8 (adapter-side, in process or subprocess)."""

from __future__ import annotations

import io
import json
import subprocess
import time
from types import SimpleNamespace

import pytest

from xverse_compat.carla_client import CarlaAdapterProcess
from xverse_compat_carla import codes as C
from xverse_compat_carla.actuation import CommandTracker
from xverse_compat_carla.descriptors import load_descriptors
from xverse_compat_carla.protocol import run
from xverse_compat_carla.sources import FakeSource, LiveSource

from .support import DESCRIPTORS, FIXTURES, ROOT, require_env

D = load_descriptors(DESCRIPTORS)


def _serve(lines, source=None, fixture="nominal.json"):
    stdin = io.StringIO("".join(json.dumps(m) + "\n" if isinstance(m, dict) else m for m in lines))
    out, err = io.StringIO(), io.StringIO()
    code = run(source or FakeSource(FIXTURES / fixture), D, stdin, out, err)
    return code, [json.loads(line) for line in out.getvalue().splitlines()], err.getvalue()


def test_m1_second_start_is_refused_and_does_not_tick():
    code, messages, _ = _serve([{"type": "start"}, {"type": "start"}])
    assert code == 0
    assert [m["type"] for m in messages] == ["hello", "refusal", "status"]
    assert messages[1]["code"] == C.COMMAND and messages[2]["state"] == "done"


def test_m2_commands_taken_at_an_exhausting_tick_are_acknowledged():
    lines = [{"type": "start"}] + [{"type": "tick"}] * 4 + [{"type": "command", "commandId": "late", "brake": 0.5, "deadlineFrames": 1}, {"type": "tick"}]
    code, messages, _ = _serve(lines)
    acks = [m for m in messages if m["type"] == "ack"]
    assert code == 0 and acks == [{"type": "ack", "commandId": "late", "result": "unacknowledged", "echoFrame": None, "responded": None}]


def test_m2_and_l8_exit_3_paths_acknowledge_commands():
    class Broken(FakeSource):
        def tick(self):
            raise RuntimeError("client lost")

    lines = [{"type": "start"}, {"type": "command", "commandId": "c", "brake": 0.5, "deadlineFrames": 1}, {"type": "tick"}]
    code, messages, err = _serve(lines, source=Broken(FIXTURES / "nominal.json"))
    assert code == 3 and [m["type"] for m in messages] == ["hello", "refusal", "ack", "status"]
    assert messages[1]["code"] == C.SOURCE and messages[2]["result"] == "unacknowledged" and "client lost" in err
    lines = [{"type": "start"}, {"type": "tick"}, {"type": "tick"}, {"type": "command", "commandId": "e", "brake": 0.5, "deadlineFrames": 2}, {"type": "tick"}]
    code, messages, _ = _serve(lines, fixture="episode.json")
    assert code == 3 and [m for m in messages if m["type"] == "ack"][0]["commandId"] == "e"


@pytest.mark.parametrize("lines", [["not json\n"], [{"type": "start"}, '{"type":"command","commandId":"x","brake":NaN,"deadlineFrames":1}\n'],
                                   [{"type": "tick"}], [{"type": "start"}, "x" * 70000 + "\n"]])
def test_l8_exit_2_paths_emit_only_hello(lines):
    code, messages, err = _serve(lines)
    assert code == 2 and [m["type"] for m in messages] == ["hello"] and C.PROTOCOL in err


def test_l1_open_window_keeps_an_observed_echo_at_stop_and_partial_motion():
    tracker = CommandTracker(D)
    tracker.submit({"commandId": "a", "brake": 0.4, "deadlineFrames": 2})
    tracker.opened(tracker.take_pending(), 10)
    assert tracker.observe(10, 0.4, None) == []
    assert tracker.close() == [{"type": "ack", "commandId": "a", "result": "echoed", "echoFrame": 10, "responded": None}]
    tracker.submit({"commandId": "b", "brake": 0.4, "deadlineFrames": 2})
    tracker.opened(tracker.take_pending(), 20)
    tracker.observe(20, 0.0, None)
    assert tracker.observe(21, 0.0, 0.1) == [{"type": "ack", "commandId": "b", "result": "unacknowledged", "echoFrame": None, "responded": False}]


def test_l5_platform_timestamp_canary_raises_and_is_never_read():
    fd = FakeSource(FIXTURES / "nominal.json").tick()
    for obj in (fd.camera, fd.radar, fd.motion):
        with pytest.raises(AssertionError):
            obj.platform_timestamp
    code, messages, _ = _serve([{"type": "start"}] + [{"type": "tick"}] * 4)
    assert code == 0 and sum(1 for m in messages if m["type"] == "item") == 16


class _FakeWorld:
    def __init__(self):
        self.settings = SimpleNamespace(synchronous_mode=False, fixed_delta_seconds=None)
        self.applied, self.frame = [], 41
        self.sensors = {2: _FakeSensor(), 3: _FakeSensor()}
        self.vehicle = SimpleNamespace(get_control=lambda: SimpleNamespace(brake=0.25), apply_control=lambda c: self.applied.append(c.brake))
        self.snapshot_lag = False

    def get_settings(self):
        return SimpleNamespace(**vars(self.settings))

    def apply_settings(self, settings):
        self.settings = SimpleNamespace(**vars(settings))

    def get_actor(self, actor_id):
        return self.vehicle if actor_id == 1 else self.sensors[actor_id]

    def tick(self):
        self.frame += 1
        for sensor in self.sensors.values():
            sensor.emit(SimpleNamespace(frame=self.frame - 1, timestamp=0.0))  # a late frame, filtered out
            sensor.emit(SimpleNamespace(frame=self.frame, timestamp=1.0))
        return self.frame

    def get_snapshot(self):
        frame = self.frame - 1 if self.snapshot_lag else self.frame
        return SimpleNamespace(frame=frame, timestamp=SimpleNamespace(elapsed_seconds=2.0), find=lambda i: "motion")


class _FakeSensor:
    def __init__(self):
        self.callback, self.stopped = None, False

    def listen(self, cb):
        self.callback = cb

    def emit(self, data):
        self.callback(data)

    def stop(self):
        self.stopped = True


def test_m4_live_source_against_an_owned_fake_carla_module():
    world = _FakeWorld()
    client = SimpleNamespace(get_world=lambda: world)
    fake_carla = SimpleNamespace(VehicleControl=lambda brake: SimpleNamespace(brake=brake))
    source = LiveSource(client, 1, 2, 3, D, carla_module=fake_carla)
    assert world.settings.synchronous_mode is True and world.settings.fixed_delta_seconds == 0.05
    source.apply([{"brake": 0.7}])
    fd = source.tick()
    assert (fd.frame, fd.camera.frame, fd.radar.frame, fd.motion, fd.echo_brake, world.applied) == (42, 42, 42, "motion", 0.25, [0.7])
    world.snapshot_lag = True
    assert source.tick().motion is None  # a stale snapshot counts as absent
    world.sensors[2].emit = lambda data: None  # camera silent: one shared per-tick deadline
    world.snapshot_lag = False
    started = time.monotonic()
    fd = source.tick()
    assert fd.camera is None and fd.radar is not None and time.monotonic() - started < D.sensor_wait_ms / 1000.0 * 1.8
    source.close()
    assert world.settings.synchronous_mode is False and all(s.stopped for s in world.sensors.values())


def test_m4_live_source_restores_settings_when_binding_fails():
    world = _FakeWorld()
    world.sensors = {}
    client = SimpleNamespace(get_world=lambda: world)
    with pytest.raises(KeyError):
        LiveSource(client, 1, 2, 3, D, carla_module=SimpleNamespace())
    assert world.settings.synchronous_mode is False


def test_m3_client_refuses_a_done_with_forbidden_modules():
    from xverse_compat.carla_client import CarlaProtocolError, parse_outbound

    with pytest.raises(CarlaProtocolError):
        parse_outbound(json.dumps({"type": "status", "state": "done", "frame": 1}))  # field required
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / 'nominal.json'}")
    assert proc.timeout_s == pytest.approx(5.2)
    proc.start()
    proc._lines.put(json.dumps({"type": "status", "state": "done", "frame": 1, "forbiddenModulesLoaded": ["xverse_compat"]}) + "\n")
    proc._lines.queue.rotate(1)  # the injected line is read first
    with pytest.raises(CarlaProtocolError, match="forbidden"):
        proc.read_until_done()


def test_l7_items_after_an_ack_are_refused():
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / 'nominal.json'}")
    proc.start()
    for line in ({"type": "ack", "commandId": "x", "result": "echoed", "echoFrame": 1, "responded": None},
                 {"type": "item", "flowId": "camera", "sequence": 0, "originNs": 0, "frame": 1, "value": {}}):
        proc._lines.put(json.dumps(line) + "\n")
    proc._lines.queue.rotate(2)
    from xverse_compat.carla_client import CarlaProtocolError

    with pytest.raises(CarlaProtocolError, match="after an ack"):
        proc.read_until_done()


def test_l8_v01_wheel_hash_matches_the_selection_pin():
    record = json.loads((ROOT / "docs/engineering/thesis-lite-phase4b/env-record.json").read_text())
    selection = json.loads((ROOT / "xdl/selection/aeb-sim-selection.json").read_text())
    pin = next(p for p in selection["pins"] if p["id"] == "carla-python-client")
    assert pin["digest"] == "sha256:" + record["wheelSha256"] and pin["availability"] == "present"
