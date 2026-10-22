"""Phase 7 successor (carla-items/2, owned live scenario, restore guard, Lite loop units) on owned fakes.

Live behaviour against a CARLA server is verified only by the recorded live runs, not by these tests.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace

import pytest

from xverse_compat.carla_client import CarlaProtocolError, SocketAdapterLink, parse_outbound
from xverse_compat.live import stimulus
from xverse_compat.live.driver import VcuCommands
from xverse_compat.live.loop import LiteVehicleLoop, profile_source
from xverse_compat_carla import codes as C
from xverse_compat_carla.actuation import CommandTracker
from xverse_compat_carla.descriptors import load_descriptors
from xverse_compat_carla.protocol import ProtocolViolation, UnknownInbound, parse_inbound, run
from xverse_compat_carla.restore import restore
from xverse_compat_carla.scenario import ROLE_PREFIX, spawn
from xverse_compat_carla.sources import FakeSource, LiveSource

from ..carla.support import DESCRIPTORS, FIXTURES, ROOT, require_env

D = load_descriptors(DESCRIPTORS)


def _socket_path(tmp_path_factory=None) -> str:
    path = f"/run/user/{os.getuid()}/xverse-lite/test-{os.getpid()}-{time.monotonic_ns()}.sock"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def _adapter(socket_path: str, *extra: str) -> subprocess.Popen:
    return subprocess.Popen(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                             "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + socket_path, "--source",
                             f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), *extra],
                            cwd=ROOT / "src", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def test_protocol_2_commands_require_a_throttle_in_range():
    tracker = CommandTracker(D, protocol=2)
    tracker.submit({"commandId": "a", "brake": 0.0, "throttle": 0.5, "deadlineFrames": 1})
    assert tracker.take_pending() == [{"commandId": "a", "brake": 0.0, "throttle": 0.5, "deadlineFrames": 1}]
    for bad in (None, -0.1, 1.5, float("nan"), True):
        with pytest.raises(C.CarlaRefusal):
            tracker.submit({"commandId": f"b{bad}", "brake": 0.0, "throttle": bad, "deadlineFrames": 1})
    with pytest.raises(UnknownInbound):  # a protocol 1 command member set is refused under protocol 2
        parse_inbound(json.dumps({"type": "command", "commandId": "x", "brake": 0.1, "deadlineFrames": 1}), 2)
    with pytest.raises(UnknownInbound):  # and vice versa: protocol 1 is unchanged
        parse_inbound(json.dumps({"type": "command", "commandId": "x", "brake": 0.1, "throttle": 0.1, "deadlineFrames": 1}), 1)


def test_protocol_2_hello_id_and_fake_throttle_record():
    stdin = io.StringIO(json.dumps({"type": "start"}) + "\n" + json.dumps({"type": "command", "commandId": "c", "brake": 0.0,
                        "throttle": 0.4, "deadlineFrames": 1}) + "\n" + json.dumps({"type": "tick"}) + "\n")
    out = io.StringIO()
    source = FakeSource(FIXTURES / "nominal.json")
    assert run(source, D, stdin, out, io.StringIO(), protocol=2) == 0
    hello = json.loads(out.getvalue().splitlines()[0])
    assert hello["protocol"] == "xverse-compat.carla-items/2" and source.throttle == 0.4
    with pytest.raises(CarlaProtocolError):  # the protocol-1 client refuses a protocol-2 hello
        parse_outbound(json.dumps(dict(hello, python="3.10.12")))


def test_socket_link_round_trip_on_the_pinned_interpreter():
    path = _socket_path()
    link = SocketAdapterLink(path, DESCRIPTORS)
    proc = _adapter(path)
    hello = link.start(accept_timeout_s=30)
    assert hello["protocol"] == "xverse-compat.carla-items/2" and oct(os.stat(path).st_mode & 0o777) == "0o600"
    link.command("c1", 0.0, 1, throttle=0.5)
    step = link.tick()
    assert [i["flowId"] for i in step.items] == ["camera", "radar-adas", "radar-vc", "vehicle-motion"] and step.acks[0]["result"] == "echoed"
    _, final = link.stop()
    assert final.done["forbiddenModulesLoaded"] == [] and proc.wait(timeout=10) == 0 and not Path(path).exists()


def test_socket_link_accept_timeout_is_a_protocol_error():
    link = SocketAdapterLink(_socket_path(), DESCRIPTORS)
    with pytest.raises(CarlaProtocolError, match="did not connect"):
        link.start(accept_timeout_s=0.2)
    link.kill()


def test_adapter_linger_only_after_success_and_stderr_redirect(tmp_path):
    err = tmp_path / "adapter.err"
    start = time.monotonic()
    proc = subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                           "xverse_compat_carla.main", "--source", f"fake:{tmp_path / 'missing.json'}", "--descriptors", str(DESCRIPTORS),
                           "--linger", "--marker", str(tmp_path / "m"), "--stderr", str(err)], cwd=ROOT / "src", capture_output=True, timeout=30)
    assert proc.returncode == 3 and time.monotonic() - start < 20  # a failed adapter does not linger
    assert proc.stderr == b"" and C.SOURCE in err.read_text() and json.loads((tmp_path / "m").read_text())["code"] == 3


class _Blueprint:
    def __init__(self, bp_id):
        self.id, self.attributes = bp_id, {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class _Actor:
    def __init__(self, world, bp, transform, parent):
        self.world, self.id, self.type_id, self.attributes = world, world.next_id(), bp.id, dict(bp.attributes)
        self.parent, self.destroyed, self.stopped, self.callback = parent, False, False, None
        self.controls = []

    def destroy(self):
        self.destroyed = True
        self.world.actors.remove(self)

    def listen(self, callback):
        self.callback = callback

    def stop(self):
        self.stopped = True

    def apply_control(self, control):
        self.controls.append(control)

    def get_control(self):
        return SimpleNamespace(brake=self.controls[-1].brake if self.controls else 0.0)


class _World:
    def __init__(self, fail_at=None):
        self.actors, self._id, self.fail_at = [], 0, fail_at
        self.settings = SimpleNamespace(synchronous_mode=False, fixed_delta_seconds=None)
        self.pending, self.ticks = None, 0

    def next_id(self):
        self._id += 1
        return self._id

    def get_blueprint_library(self):
        return SimpleNamespace(find=_Blueprint)

    def get_map(self):
        return SimpleNamespace(get_spawn_points=lambda: ["sp0", "sp1"])

    def spawn_actor(self, bp, transform, attach_to=None):
        if self.fail_at == bp.id:
            raise RuntimeError("spawn failed")
        actor = _Actor(self, bp, transform, attach_to)
        self.actors.append(actor)
        return actor

    def get_actor(self, actor_id):
        return next((a for a in self.actors if a.id == actor_id), None)

    def get_actors(self):
        return list(self.actors)

    def get_settings(self):
        return SimpleNamespace(**vars(self.settings))

    def apply_settings(self, settings):  # as CARLA: a synchronous world applies settings on the next tick
        if self.settings.synchronous_mode:
            self.pending = SimpleNamespace(**vars(settings))
        else:
            self.settings = SimpleNamespace(**vars(settings))

    def tick(self, timeout=None):
        self.ticks += 1
        if self.pending is not None:
            self.settings, self.pending = self.pending, None
        return self.ticks

    def wait_for_tick(self, timeout=None):
        return self.tick()


CARLA = SimpleNamespace(Transform=lambda location: location, Location=lambda **xyz: xyz, VehicleControl=lambda **c: SimpleNamespace(**c))


def test_owned_scenario_spawns_destroys_and_actuates_throttle():
    world = _World()
    world.attributes_ok = True
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA,
                        scenario={"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1})
    ego, camera, radar = world.actors
    assert ego.type_id == "vehicle.audi.etron" and ego.attributes["role_name"] == ROLE_PREFIX + "ego"
    assert camera.attributes["image_size_x"] == "800" and radar.attributes["range"] == "100.0" and camera.parent is ego
    source.apply([{"brake": 0.0, "throttle": 0.6}])
    assert (ego.controls[-1].throttle, ego.controls[-1].brake, ego.controls[-1].steer) == (0.6, 0.0, 0.0)
    source.close()
    assert world.actors == [] and camera.stopped and world.settings.synchronous_mode is False


def test_scenario_spawn_failure_destroys_partial_actors_and_restores_settings():
    world = _World(fail_at="sensor.other.radar")
    with pytest.raises(RuntimeError):
        LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA,
                   scenario={"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 0})
    assert world.actors == [] and world.settings.synchronous_mode is False
    with pytest.raises(ValueError):
        spawn(_World(), CARLA, D, {"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 5})


def test_restore_guard_commits_settings_before_destroying_owned_actors():
    world = _World()
    for role in ("xverse-lite-ego", "xverse-lite-camera", "ego_vehicle"):
        bp = _Blueprint("vehicle.x")
        bp.set_attribute("role_name", role)
        world.spawn_actor(bp, None)
    world.settings = SimpleNamespace(synchronous_mode=True, fixed_delta_seconds=0.05)
    record = restore(world)
    assert record["before"]["synchronousMode"] is True and record["after"]["synchronousMode"] is False
    assert {d["roleName"] for d in record["destroyed"]} == {"xverse-lite-ego", "xverse-lite-camera"} and record["remaining"] == []
    assert record["restored"] is True and [a.attributes["role_name"] for a in world.actors] == ["ego_vehicle"]  # foreign actors untouched


class _Session:
    def __init__(self):
        self.subs = {}

    def declare_subscriber(self, key, callback):
        self.subs[key] = callback
        return key


def _sample(value):
    return SimpleNamespace(payload=SimpleNamespace(to_bytes=lambda: str(value).encode()))


def test_vcu_commands_staleness_rule_and_clamping():
    session = _Session()
    commands = VcuCommands(session, stale_ms=50)
    throttle, brake, meta = commands(0.0, None)
    assert (throttle, brake, meta["stale"]) == (0.0, 0.0, True)  # nothing received yet
    session.subs["vcu/control/throttle_cmd"](_sample(1.4))
    session.subs["vcu/control/brake_cmd"](_sample(0.3))
    throttle, brake, meta = commands(0.0, None)
    assert (throttle, brake, meta["stale"], meta["throttleClamped"]) == (1.0, 0.3, False, True)
    time.sleep(0.08)
    throttle, brake, meta = commands(0.0, None)
    assert (throttle, brake, meta["stale"]) == (0.0, 0.3, True) and commands.stale_ticks == 2  # drop throttle, hold brake


def test_stimulus_profile_segments():
    assert stimulus.pedals(0.0)[:2] == (0.0, 0.0) and stimulus.pedals(3.0)[:2] == (0.6, 0.0) and stimulus.pedals(8.0)[:2] == (0.0, 0.8)
    assert stimulus.pedals(10.5)[2] == len(stimulus.PROFILE)


def test_lite_loop_routes_items_through_flow_receivers_on_a_fake_adapter():
    path = _socket_path()
    link = SocketAdapterLink(path, DESCRIPTORS)
    proc = _adapter(path)
    link.start(accept_timeout_s=30)
    record = io.StringIO()
    motions = []
    loop = LiteVehicleLoop(link, profile_source([{"untilS": 10.0, "throttle": 0.5, "brake": 0.0}]), record=record, tick_period_s=0.0,
                           max_ticks=10, wall_deadline=time.monotonic() + 30, on_motion=lambda m, s: motions.append(s))
    result = loop.run()
    assert result.end_reason == "adapter-done" and result.ticks == 5 and result.verdicts == {"delivered": 8}
    rows = [json.loads(line) for line in record.getvalue().splitlines()]
    assert [r["kind"] for r in rows] == ["tick"] * 4 + ["done"] and rows[0]["simS"] == 0.0 and motions[1] == pytest.approx(0.05)
    assert proc.wait(timeout=10) == 0
    link.kill()
