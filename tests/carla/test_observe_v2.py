"""Phase 8 WP-01: the evaluation observer v2 (GA-07) on owned fakes (review-wp01 finding 1).

``carla`` is a fake module in ``sys.modules``; the fake world and actors raise on every mutating call, so
a completed run shows that the observer never ticks, sets settings, applies control, spawns or destroys.
"""

from __future__ import annotations

import ast
from fnmatch import fnmatchcase
import json
import math
from pathlib import Path
import signal
import sys
from types import ModuleType, SimpleNamespace

import pytest

from xverse_compat.carla_client import FLOWS as CLIENT_FLOWS, PROTOCOL_ID, PROTOCOL_ID_2, CarlaProtocolError, parse_outbound
from xverse_compat_carla import observe
from xverse_compat_carla.protocol import FLOWS as ADAPTER_FLOWS
from xverse_compat_carla.timeconv import seconds_to_ns

from .support import ROOT

SRC = ROOT / "src"
RUNTIME_ENTRIES = ("xverse_compat_carla.main", "xverse_compat.live.driver", "xverse_compat.live.stimulus", "xverse_compat.live.loop")
MUTATORS = ("tick", "apply_settings", "spawn_actor", "try_spawn_actor", "destroy", "apply_control", "set_autopilot",
            "set_target_velocity", "set_transform", "enable_constant_velocity")


class Mutation(AssertionError):
    """A passive observer called a mutating CARLA method."""


class _Passive:
    def __getattr__(self, name):
        if name in MUTATORS:
            raise Mutation(f"observer called {name}")
        raise AttributeError(name)


def _v(x=0.0, y=0.0, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


class Actor(_Passive):
    def __init__(self, actor_id, role, type_id="vehicle.tesla.model3", control=(0.0, 1.0, 0.0)):
        self.id, self.type_id, self.attributes, self.is_alive = actor_id, type_id, {"role_name": role}, True
        self._control = SimpleNamespace(throttle=control[0], brake=control[1], steer=control[2])

    def get_control(self):
        return self._control


class State:
    def __init__(self, location=(1.0, 2.0, 0.5), rotation=(0.0, 90.0, 0.0), velocity=(0.0, 3.0, 0.0), accel=(0.0, -2.0, 0.0)):
        yaw = math.radians(rotation[1])
        forward = _v(math.cos(yaw), math.sin(yaw), 0.0)
        self._tf = SimpleNamespace(location=_v(*location), rotation=SimpleNamespace(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]),
                                   get_forward_vector=lambda: forward)
        self._v, self._a = _v(*velocity), _v(*accel)

    def get_transform(self):
        return self._tf

    def get_velocity(self):
        return self._v

    def get_acceleration(self):
        return self._a


class Snapshot:
    def __init__(self, frame, elapsed, states, delta=0.05):
        self.frame, self.timestamp, self._states = frame, SimpleNamespace(elapsed_seconds=elapsed, delta_seconds=delta), states

    def find(self, actor_id):
        return self._states.get(actor_id)


class ActorList(list):
    """``carla.ActorList``: ``filter`` matches ``type_id`` wildcards."""

    def filter(self, pattern):
        return ActorList(a for a in self if fnmatchcase(a.type_id, pattern))


class World(_Passive):
    """Serves scripted frames; a ``RuntimeError`` entry is a tick timeout. After the script it raises SIGTERM's handler."""

    def __init__(self, script, actors, handlers, fail_actors_after=None):
        self.script, self.actors, self.handlers, self.listings = list(script), actors, handlers, 0
        self.fail_actors_after = fail_actors_after

    def get_map(self):
        return SimpleNamespace(name="Carla/Maps/Town10HD_Opt")

    def get_actors(self):
        self.listings += 1
        if self.fail_actors_after is not None and self.listings > self.fail_actors_after:
            raise RuntimeError("time-out of 10000ms while waiting for the simulator")
        return ActorList(self.actors)

    def wait_for_tick(self, seconds):
        if not self.script:
            self.handlers[signal.SIGTERM]()
            raise RuntimeError("no further frame")
        item = self.script.pop(0)
        if item is RuntimeError:
            raise RuntimeError("time-out while waiting for the simulator")
        return item(self) if callable(item) else item


@pytest.fixture
def fake_carla(monkeypatch):
    """Install a fake ``carla`` and capture the observer's signal handlers (pytest's own stay in place)."""

    handlers = {}
    monkeypatch.setattr(observe.signal, "signal", lambda signum, handler: handlers.__setitem__(signum, lambda: handler(signum, None)))
    state = SimpleNamespace(world=None, handlers=handlers, connect_error=None)

    def client(host, port):
        if state.connect_error is not None:
            raise state.connect_error
        return SimpleNamespace(set_timeout=lambda s: None, get_world=lambda: state.world)

    module = ModuleType("carla")
    module.Client = client
    monkeypatch.setitem(sys.modules, "carla", module)
    return state


def _rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def _scene(fake_carla, script, actors, **kw):
    fake_carla.world = World(script, actors, fake_carla.handlers, **kw)
    return fake_carla.world


def _run(tmp_path, roles, duration=60.0):
    out = tmp_path / "ground-truth.jsonl"
    args = [arg for role in roles for arg in ("--track", role)]
    return observe.main(args + ["--duration-s", str(duration), "--out", str(out)]), out


# ---- v1 compatibility --------------------------------------------------------------------------------


def test_wp01_v1_role_schema_is_unchanged(fake_carla, tmp_path):
    ego = Actor(7, "xverse-lite-ego")
    _scene(fake_carla, [Snapshot(10, 0.5, {7: State()})], [ego, Actor(8, "xverse-lite-target")])
    out = tmp_path / "observer.jsonl"
    assert observe.main(["--role", "xverse-lite-ego", "--duration-s", "60", "--out", str(out)]) == 0
    header, record, footer = _rows(out)
    assert set(header) == {"header", "evaluationOnly", "role", "map", "startedWallNs", "startedMonotonicNs"}
    assert header["evaluationOnly"] is True and header["role"] == "xverse-lite-ego"
    assert set(record) == {"monotonicNs", "frame", "elapsedS", "deltaS", "ego"} and record["frame"] == 10
    assert record["ego"] == {"id": 7, "location": [1.0, 2.0, 0.5], "velocity": [0.0, 3.0, 0.0], "acceleration": [0.0, -2.0, 0.0],
                             "speedMps": 3.0, "accelForwardMps2": -2.0, "cachedControl": {"throttle": 0.0, "brake": 1.0, "steer": 0.0}}
    assert set(footer) == {"footer", "frames", "tickTimeouts", "stoppedBy", "endedMonotonicNs"}
    assert footer["frames"] == 1 and footer["stoppedBy"] == "SIGTERM"


def test_wp01_v1_existing_output_is_still_truncated(fake_carla, tmp_path):
    out = tmp_path / "observer.jsonl"
    out.write_text("stale\n")
    _scene(fake_carla, [], [])
    assert observe.main(["--role", "ego_vehicle", "--duration-s", "60", "--out", str(out)]) == 0
    assert "stale" not in out.read_text()


# ---- v2 schema and clock -----------------------------------------------------------------------------


def test_wp01_v2_header_labels_ground_truth_and_declares_clock_and_passivity(fake_carla, tmp_path):
    _scene(fake_carla, [], [])
    code, out = _run(tmp_path, ["xverse-lite-ego", "xverse-lite-target"])
    assert code == 0
    header, footer = _rows(out)
    assert header["schema"] == footer["schema"] == observe.SCHEMA == "xverse-compat.evaluation-observer/2"
    assert header["evaluationOnly"] is True and header["groundTruth"] is True and "EVALUATION-ONLY GROUND TRUTH" in header["label"]
    assert header["roles"] == ["xverse-lite-ego", "xverse-lite-target"]
    assert header["clock"]["canonical"] == "simulation" and header["clock"]["key"] == "frame"
    assert header["passive"] == {"ticks": False, "appliesSettings": False, "appliesControl": False, "spawnsOrDestroys": False}
    assert footer == {**footer, "frames": 0, "tickTimeouts": 1, "observedFrames": {"xverse-lite-ego": 0, "xverse-lite-target": 0},
                      "stoppedBy": "SIGTERM", "error": None}


def test_wp01_v2_records_every_declared_role_per_simulation_frame(fake_carla, tmp_path):
    ego, target = Actor(7, "xverse-lite-ego"), Actor(9, "xverse-lite-target", control=(0.0, 0.0, 0.0))
    camera = Actor(8, "xverse-lite-camera", type_id="sensor.camera.rgb")
    states = {7: State(), 9: State(location=(1.0, 40.0, 0.5), velocity=(0.0, 0.0, 0.0), accel=(0.0, 0.0, 0.0)), 8: State(location=(1.0, 3.5, 2.9))}
    _scene(fake_carla, [Snapshot(100, 5.05, states), Snapshot(101, 5.1, states)], [ego, camera, target, Actor(3, "hero")])
    code, out = _run(tmp_path, ["xverse-lite-ego", "xverse-lite-target", "xverse-lite-camera"])
    assert code == 0
    header, first, second, footer = _rows(out)
    assert [first["frame"], second["frame"]] == [100, 101]
    assert first["simElapsedS"] == 5.05 and first["simElapsedNs"] == seconds_to_ns(5.05) == 5_050_000_000 and first["simDeltaS"] == 0.05
    assert isinstance(first["observerMonotonicNs"], int)
    assert list(first["roles"]) == header["roles"]
    assert first["roles"]["xverse-lite-ego"] == {
        "status": "observed", "id": 7, "typeId": "vehicle.tesla.model3", "location": [1.0, 2.0, 0.5], "rotationDeg": [0.0, 90.0, 0.0],
        "velocity": [0.0, 3.0, 0.0], "acceleration": [0.0, -2.0, 0.0], "speedMps": 3.0, "accelForwardMps2": -2.0,
        "cachedControl": {"throttle": 0.0, "brake": 1.0, "steer": 0.0}}
    assert first["roles"]["xverse-lite-target"]["location"] == [1.0, 40.0, 0.5] and first["roles"]["xverse-lite-target"]["speedMps"] == 0.0
    assert "cachedControl" not in first["roles"]["xverse-lite-camera"]  # control is a vehicle member only
    assert footer["frames"] == 2 and footer["observedFrames"] == dict.fromkeys(header["roles"], 2)
    assert fake_carla.world.listings == 1  # resolved once while every role stays alive


def test_wp01_v2_absent_ambiguous_not_in_snapshot_and_non_finite_are_never_guessed(fake_carla, tmp_path):
    ego, target = Actor(7, "xverse-lite-ego"), Actor(9, "xverse-lite-target")
    dup_a, dup_b = Actor(12, "xverse-lite-dup"), Actor(11, "xverse-lite-dup")
    states = {7: State(velocity=(math.nan, 0.0, 0.0)), 11: State(), 12: State()}  # target 9 is missing from the snapshot
    _scene(fake_carla, [Snapshot(5, 0.25, states)], [ego, target, dup_a, dup_b])
    code, out = _run(tmp_path, ["xverse-lite-ego", "xverse-lite-target", "xverse-lite-dup", "xverse-lite-gone"])
    assert code == 0
    roles = _rows(out)[1]["roles"]
    assert roles == {"xverse-lite-ego": {"status": "non-finite", "id": 7}, "xverse-lite-target": {"status": "not-in-snapshot", "id": 9},
                     "xverse-lite-dup": {"status": "ambiguous", "ids": [11, 12]}, "xverse-lite-gone": {"status": "absent"}}
    assert "NaN" not in out.read_text()
    assert _rows(out)[-1]["observedFrames"] == dict.fromkeys(roles, 0)


def test_wp01_v2_resolves_a_role_again_after_its_actor_dies_or_appears(fake_carla, tmp_path):
    first, second = Actor(7, "xverse-lite-target"), Actor(21, "xverse-lite-target")
    actors = []

    def spawn_first(world):
        actors.append(first)
        return Snapshot(2, 0.1, {7: State()})

    def replace(world):
        first.is_alive = False
        actors[:] = [second]
        return Snapshot(3, 0.15, {21: State()})

    world = _scene(fake_carla, [Snapshot(1, 0.05, {}), spawn_first, replace], actors)
    code, out = _run(tmp_path, ["xverse-lite-target"])
    rows = _rows(out)[1:-1]
    assert code == 0 and [r["roles"]["xverse-lite-target"].get("id") for r in rows] == [None, 7, 21] and world.listings == 3


# ---- passivity ---------------------------------------------------------------------------------------


def test_wp01_v2_never_mutates_the_world_or_any_actor(fake_carla, tmp_path):
    actors = [Actor(7, "xverse-lite-ego"), Actor(9, "xverse-lite-target")]
    _scene(fake_carla, [Snapshot(n, n * 0.05, {7: State(), 9: State()}) for n in range(1, 6)], actors)
    code, out = _run(tmp_path, ["xverse-lite-ego", "xverse-lite-target"])
    assert code == 0 and _rows(out)[-1]["error"] is None  # a Mutation would have ended the run as an error
    for name in MUTATORS:
        with pytest.raises(Mutation):
            getattr(fake_carla.world, name)


def test_wp01_observer_source_calls_no_mutating_carla_method():
    names = {node.attr for node in ast.walk(ast.parse((SRC / "xverse_compat_carla" / "observe.py").read_text())) if isinstance(node, ast.Attribute)}
    assert not names & set(MUTATORS)


# ---- failure behaviour -------------------------------------------------------------------------------


def test_wp01_v2_connection_failure_exits_3_without_a_file(fake_carla, tmp_path, capsys):
    fake_carla.connect_error = RuntimeError("connection refused")
    code, out = _run(tmp_path, ["xverse-lite-ego"])
    assert code == 3 and not out.exists() and "CARLA connection failed" in capsys.readouterr().err


def test_wp01_v2_refuses_an_existing_output_path_and_leaves_it_untouched(fake_carla, tmp_path, capsys):
    _scene(fake_carla, [Snapshot(1, 0.05, {})], [])
    out = tmp_path / "ground-truth.jsonl"
    out.write_text("runtime-owned\n")
    code, _ = _run(tmp_path, ["xverse-lite-ego"])
    assert code == 3 and out.read_text() == "runtime-owned\n" and "output path refused" in capsys.readouterr().err
    assert observe.main(["--track", "xverse-lite-ego", "--duration-s", "1", "--out", "/dev/stdout"]) == 3


def test_wp01_v2_error_after_the_header_writes_an_error_footer_and_exits_3(fake_carla, tmp_path, capsys):
    ego = Actor(7, "xverse-lite-ego")

    def ego_dies(world):  # forces a second listing, which fails as a lost server would
        ego.is_alive = False
        return Snapshot(2, 0.1, {7: State()})

    _scene(fake_carla, [Snapshot(1, 0.05, {7: State()}), ego_dies], [ego], fail_actors_after=1)
    code, out = _run(tmp_path, ["xverse-lite-ego"])
    rows = _rows(out)
    assert code == 3 and len(rows) == 3 and rows[-1]["stoppedBy"] == "error" and rows[-1]["frames"] == 2
    assert "time-out of 10000ms" in rows[-1]["error"] and "observe: RuntimeError" in capsys.readouterr().err


def test_wp01_v2_invalid_simulation_clock_is_an_error(fake_carla, tmp_path):
    _scene(fake_carla, [Snapshot(1, math.inf, {})], [])
    code, out = _run(tmp_path, ["xverse-lite-ego"])
    assert code == 3 and _rows(out)[-1]["stoppedBy"] == "error" and len(_rows(out)) == 2


def test_wp01_v2_tick_timeouts_are_counted_and_the_duration_bound_holds(fake_carla, tmp_path):
    _scene(fake_carla, [RuntimeError, Snapshot(4, 0.2, {}), RuntimeError], [])
    code, out = _run(tmp_path, ["xverse-lite-ego"])
    footer = _rows(out)[-1]
    assert code == 0 and footer["frames"] == 1 and footer["tickTimeouts"] == 3 and footer["stoppedBy"] == "SIGTERM"
    _scene(fake_carla, [Snapshot(1, 0.05, {})], [])
    zero = tmp_path / "zero.jsonl"
    assert observe.main(["--track", "xverse-lite-ego", "--duration-s", "0", "--out", str(zero)]) == 0
    assert _rows(zero)[-1]["stoppedBy"] == "duration" and _rows(zero)[-1]["frames"] == 0


@pytest.mark.parametrize("argv", [
    ["--role", "xverse-lite-ego", "--track", "xverse-lite-ego"],
    [],
    ["--track", "xverse-lite-ego", "--track", "xverse-lite-ego"],
    ["--track", "ego_vehicle"],
    ["--track", "xverse-lite-"],
    ["--track", "xverse-lite-Ego"],
])
def test_wp01_v2_argument_errors_exit_2_before_any_connection_or_file(fake_carla, tmp_path, argv):
    fake_carla.connect_error = AssertionError("connected")
    out = tmp_path / "gt.jsonl"
    with pytest.raises(SystemExit) as exit_info:
        observe.main(argv + ["--duration-s", "1", "--out", str(out)])
    assert exit_info.value.code == 2 and not out.exists()


# ---- never reaches a runtime unit (FR-021, DYN-002) --------------------------------------------------


def _module_path(name):
    base = SRC.joinpath(*name.split("."))
    return base.with_suffix(".py") if base.with_suffix(".py").is_file() else base / "__init__.py"


def _imports(name):
    """Return the in-repository modules that module ``name`` imports (absolute and relative)."""

    path = _module_path(name)
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1] + ([node.module] if node.module else []))
            targets = [base] + [f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        found |= {t for t in targets if t.split(".")[0] in ("xverse_compat", "xverse_compat_carla") and _module_path(t).is_file()}
    return found


def _closure(entry):
    seen, todo = set(), [entry]
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(_imports(name))
    return seen


def test_wp01_no_runtime_unit_imports_the_observer():
    for entry in RUNTIME_ENTRIES:
        closure = _closure(entry)
        assert entry in closure and "xverse_compat_carla.observe" not in closure, entry
    assert "xverse_compat_carla.observe" not in _closure("xverse_compat_carla.main")  # the adapter itself


def test_wp01_no_module_imports_the_observer():
    modules = [".".join(p.relative_to(SRC).with_suffix("").parts) for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]
    importers = [m.replace(".__init__", "") for m in modules if "xverse_compat_carla.observe" in _imports(m.replace(".__init__", ""))]
    assert importers == []


def test_wp01_observer_imports_no_transport_and_nothing_forbidden():
    tree = ast.parse((SRC / "xverse_compat_carla" / "observe.py").read_text())
    top = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    relative = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level}
    absolute = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and not node.level}
    assert top == {"argparse", "json", "math", "os", "re", "signal", "site", "sys", "time", "carla"}
    assert relative == {"timeconv"} and absolute == {"__future__"}


def test_wp01_runtime_intake_refuses_every_observer_line(fake_carla, tmp_path, capsys):
    actors = [Actor(7, "xverse-lite-ego"), Actor(9, "xverse-lite-target")]
    _scene(fake_carla, [Snapshot(1, 0.05, {7: State(), 9: State()})], actors)
    code, out = _run(tmp_path, ["xverse-lite-ego", "xverse-lite-target"])
    assert code == 0 and capsys.readouterr().out == ""  # nothing on standard output
    lines = out.read_text().splitlines()
    assert len(lines) == 3
    for line in lines:
        for protocol_id in (PROTOCOL_ID, PROTOCOL_ID_2):
            with pytest.raises(CarlaProtocolError):
                parse_outbound(line, protocol_id=protocol_id)


def test_wp01_runtime_flows_carry_no_ground_truth():
    assert ADAPTER_FLOWS == CLIENT_FLOWS == ("camera", "radar-adas", "radar-vc", "vehicle-motion")
    for path in (ROOT / "xdl").rglob("*.json"):
        text = path.read_text()
        assert "evaluation-observer" not in text and "xverse_compat_carla.observe" not in text, path
