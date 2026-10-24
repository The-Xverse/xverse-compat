"""Phase 8 WP-02: the stationary target spawn on owned fakes (review-wp02 finding 1).

Reuses the Phase 7 fake world; its map gains waypoints. Nothing here starts CARLA.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from xverse_compat_carla import scenario as S
from xverse_compat_carla.observe import TRACK_ROLE
from xverse_compat_carla.restore import restore
from xverse_compat_carla.scenario import ROLE_PREFIX, spawn, target_of, target_transform
from xverse_compat_carla.sources import LiveSource

from ..carla.support import ROOT
from .test_phase7_live import CARLA as CARLA7, D, _World

CARLA = SimpleNamespace(Transform=lambda location, rotation=None: SimpleNamespace(location=location, rotation=rotation),
                        Location=lambda **xyz: SimpleNamespace(**xyz), Rotation=lambda **r: SimpleNamespace(**r),
                        VehicleControl=CARLA7.VehicleControl)
TARGET = {"blueprint": "vehicle.tesla.model3", "roleName": "xverse-lite-target", "distanceAheadM": 40.0, "hold": "brake-and-hand-brake"}


def _scenario(**target):
    return {"schema": S.SCHEMA_2, "egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1, "map": "Carla/Maps/Town10HD_Opt",
            "note": "test", "target": {**TARGET, **target}}


def _loc(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


class _Waypoint:
    """A straight lane along +x at road height 0.0; ``next`` returns ``branches`` waypoints."""

    def __init__(self, x, lane_map):
        self.x, self.map = x, lane_map
        self.is_junction = lane_map.junction_from is not None and x >= lane_map.junction_from
        self.transform = SimpleNamespace(location=_loc(x, 5.0, 0.0), rotation=SimpleNamespace(pitch=0.0, yaw=0.0, roll=0.0))

    def next(self, distance):
        self.map.asked.append(distance)
        return [_Waypoint(self.x + distance, self.map) for _ in range(self.map.branches)]


class _LaneMap:
    def __init__(self, branches=1, junction_from=None, on_lane=True):
        self.branches, self.junction_from, self.on_lane, self.asked = branches, junction_from, on_lane, []
        self.points = [SimpleNamespace(location=_loc(0.0, 0.0, 0.3)), SimpleNamespace(location=_loc(10.0, 5.0, 0.6))]

    def get_spawn_points(self):
        return self.points

    def get_waypoint(self, location):
        return _Waypoint(location.x, self) if self.on_lane else None


class _TargetWorld(_World):
    def __init__(self, lane_map=None, fail_at=None, hold_fails=False):
        super().__init__(fail_at=fail_at)
        self.lane_map, self.hold_fails = lane_map or _LaneMap(), hold_fails

    def get_map(self):
        return self.lane_map

    def spawn_actor(self, bp, transform, attach_to=None):
        actor = super().spawn_actor(bp, transform, attach_to)
        actor.transform = transform
        if self.hold_fails and bp.id.startswith("vehicle.tesla"):
            def refuse(control):
                raise RuntimeError("apply_control failed")
            actor.apply_control = refuse
        return actor


# ---- schema ------------------------------------------------------------------------------------------


def test_wp02_schema_1_and_no_schema_keep_the_phase7_scenario():
    assert target_of({"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1}) is None
    shipped = json.loads((ROOT / "xdl/descriptors/aeb-sim/live-scenario.json").read_text())
    assert shipped["schema"] == S.SCHEMA_1 and target_of(shipped) is None  # the harness and the soak are unchanged
    assert target_of({k: v for k, v in _scenario().items() if k != "target"}) is None  # schema 2 without a target


@pytest.mark.parametrize("scenario, message", [
    ({"schema": S.SCHEMA_1, "egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1, "target": TARGET}, "needs schema"),
    ({"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1, "target": TARGET}, "needs schema"),
    ({**_scenario(), "schema": "xverse-compat.carla-live-scenario/3"}, "unknown live-scenario schema"),
    ({**_scenario(), "weather": "ClearNoon"}, "unknown live-scenario members"),
    ({**_scenario(), "target": None}, "must be an object"),
    ({**_scenario(), "target": [TARGET]}, "must be an object"),
    ({**_scenario(), "target": {k: v for k, v in TARGET.items() if k != "distanceAheadM"}}, "members must be exactly"),
    ({**_scenario(), "target": {**TARGET, "speedMps": 0.0}}, "members must be exactly"),
    (_scenario(distanceAheadM=0), "distanceAheadM"),
    (_scenario(distanceAheadM=-5.0), "distanceAheadM"),
    (_scenario(distanceAheadM=True), "distanceAheadM"),
    (_scenario(distanceAheadM=math.nan), "distanceAheadM"),
    (_scenario(distanceAheadM=math.inf), "distanceAheadM"),
    (_scenario(distanceAheadM="40"), "distanceAheadM"),
    (_scenario(distanceAheadM=None), "distanceAheadM"),
    (_scenario(blueprint="walker.pedestrian.0001"), "vehicle"),
    (_scenario(blueprint=7), "vehicle"),
    (_scenario(roleName="xverse-lite-ego"), "roleName"),
    (_scenario(roleName="target"), "roleName"),
    (_scenario(hold="physics-off"), "hold"),
    ("not an object", "JSON object"),
])
def test_wp02_invalid_scenarios_are_refused_before_anything_is_spawned(scenario, message):
    with pytest.raises(ValueError, match=message):
        target_of(scenario)
    world = _TargetWorld()
    with pytest.raises(ValueError):
        spawn(world, CARLA, D, scenario)
    assert world.actors == [] and world.lane_map.asked == []


def test_wp02_the_target_role_is_trackable_by_the_wp01_observer():
    assert S.TARGET_ROLE == ROLE_PREFIX + "target" == "xverse-lite-target" and TRACK_ROLE.match(S.TARGET_ROLE)


# ---- placement ---------------------------------------------------------------------------------------


def test_wp02_target_is_placed_in_the_ego_lane_at_the_declared_distance():
    lane_map = _LaneMap()
    at = target_transform(lane_map, lane_map.points[1], 40.0, CARLA)
    assert lane_map.asked == [40.0]
    assert (at.location.x, at.location.y) == (50.0, 5.0)  # one waypoint 40 m ahead along the lane
    assert at.location.z == pytest.approx(0.6)  # the map's own spawn-point lift above its waypoint, not an invented one
    assert (at.rotation.pitch, at.rotation.yaw, at.rotation.roll) == (0.0, 0.0, 0.0)  # lane heading


@pytest.mark.parametrize("lane_map, message", [
    (_LaneMap(branches=0), "0 lane waypoints"),
    (_LaneMap(branches=2), "2 lane waypoints"),
    (_LaneMap(junction_from=30.0), "junction"),
    (_LaneMap(on_lane=False), "not on a driving lane"),
])
def test_wp02_ambiguous_or_missing_placement_is_refused_before_anything_is_spawned(lane_map, message):
    world = _TargetWorld(lane_map)
    with pytest.raises(ValueError, match=message):
        spawn(world, CARLA, D, _scenario())
    assert world.actors == []


# ---- spawn and ownership -----------------------------------------------------------------------------


def test_wp02_spawn_adds_the_target_last_with_one_hold_at_spawn():
    world = _TargetWorld()
    actors = spawn(world, CARLA, D, _scenario())
    ego, camera, radar, target = actors
    assert [a.attributes["role_name"] for a in actors] == ["xverse-lite-ego", "xverse-lite-camera", "xverse-lite-radar", "xverse-lite-target"]
    assert target.type_id == "vehicle.tesla.model3" and target.parent is None and target.transform.location.x == 50.0
    assert [(c.throttle, c.brake, c.steer, c.hand_brake) for c in target.controls] == [(0.0, 1.0, 0.0, True)]
    assert ego.controls == []  # the scenario never writes the ego


@pytest.mark.parametrize("failure", [{"fail_at": "vehicle.tesla.model3"}, {"hold_fails": True}])
def test_wp02_target_spawn_or_hold_failure_destroys_every_partial_spawn(failure):
    world = _TargetWorld(**failure)
    with pytest.raises(RuntimeError):
        spawn(world, CARLA, D, _scenario())
    assert world.actors == []


def test_wp02_live_source_binds_the_ego_registers_the_target_and_writes_the_ego_only(tmp_path):
    world = _TargetWorld()
    world.attributes_ok = True
    registry = tmp_path / "owned.json"
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA,
                        scenario=_scenario(), registry=str(registry))
    ego, camera, radar, target = world.actors
    assert source._vehicle is ego and source._ego_id == ego.id
    entries = json.loads(registry.read_text())["actors"]
    assert {"id": target.id, "typeId": "vehicle.tesla.model3", "roleName": "xverse-lite-target"} in entries and len(entries) == 4
    source.apply([{"brake": 0.0, "throttle": 0.6}, {"brake": 1.0, "throttle": 0.0}])
    assert len(target.controls) == 1 and [c.throttle for c in ego.controls] == [0.6, 0.0]  # runtime commands: ego only
    destroyed = []
    for actor in world.actors:
        original = actor.destroy
        actor.destroy = lambda a=actor, o=original: (destroyed.append(a.attributes["role_name"]), o())[-1]
    source.close()
    assert world.actors == [] and destroyed[0] == "xverse-lite-target" and destroyed[-1] == "xverse-lite-ego"
    assert len(target.controls) == 1  # the close holds the ego, never the target


# ---- restore guard -----------------------------------------------------------------------------------


def _killed_run_world():
    """The world a SIGKILLed adapter leaves: owned ego and target alive, synchronous, a registry on disk."""

    world = _TargetWorld()
    world.attributes_ok = True
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA, scenario=_scenario())
    registry = {"actors": [{"id": a.id, "typeId": a.type_id, "roleName": a.attributes["role_name"]} for a in source._spawned]}
    world.settings = SimpleNamespace(synchronous_mode=True, fixed_delta_seconds=0.05)
    return world, registry


def test_wp02_restore_guard_holds_and_destroys_the_target_by_listing():
    world, _ = _killed_run_world()
    target = world.actors[3]
    record = restore(world, CARLA)
    assert target.id in record["held"] and target.controls[-1].hand_brake is True
    assert "xverse-lite-target" in {d["roleName"] for d in record["destroyed"]} and record["remaining"] == [] and record["restored"]
    assert any(v["id"] == target.id for v in record["standstill"]["vehicles"])


def test_wp02_restore_guard_holds_and_destroys_the_target_by_registry():
    world, registry = _killed_run_world()
    target = world.actors[3]

    class Response:
        def __init__(self, error=False):
            self.error = error

        def has_error(self):
            return self.error

    class Client:
        def apply_batch_sync(self, commands, do_tick):
            out = []
            for kind, actor_id, *rest in commands:
                actor = world.get_actor(actor_id)
                if actor is None:
                    out.append(Response(True))
                    continue
                actor.apply_control(rest[0]) if kind == "control" else actor.destroy()
                out.append(Response())
            return out

    carla = SimpleNamespace(VehicleControl=CARLA.VehicleControl, command=SimpleNamespace(
        ApplyVehicleControl=lambda i, c: ("control", i, c), DestroyActor=lambda i: ("destroy", i)))
    record = restore(world, carla, None, Client(), registry)
    assert target.id in record["held"] and {"id": target.id, "typeId": "vehicle.tesla.model3", "roleName": "xverse-lite-target",
                                            "via": "registry"} in record["destroyed"]
    assert record["remaining"] == [] and record["restored"] is True and world.actors == []
