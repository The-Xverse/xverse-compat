"""Phase 8 WP-02 and WP-02b: the stationary target spawn on owned fakes (review-wp02 and review-wp02b finding 1).

Reuses the Phase 7 fake world; its map gains waypoints and, for WP-02b, lanes beside the ego lane. Every lane
id, road id, lane type and lane-centre coordinate here is a labelled test value, not a map fact. Nothing here
starts CARLA.
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
#: WP-02b fake: ``carla.LaneType`` with test tokens. ``CARLA`` above has no ``LaneType``, so a WP-02 placement that
#: touched it would fail.
CARLA_LANES = SimpleNamespace(**vars(CARLA), LaneType=SimpleNamespace(Driving="Driving"))
TARGET = {"blueprint": "vehicle.tesla.model3", "roleName": "xverse-lite-target", "distanceAheadM": 40.0, "hold": "brake-and-hand-brake"}
#: Test values: the fake ego lane is lane -1 of road 7, centred on y 5.0; its neighbours are declared per test.
EGO_LANE_ID, ROAD_ID = -1, 7
LEFT_SAME = {"lane_id": -2, "y": 1.5}
LEFT_OPPOSITE = {"lane_id": 1, "y": 1.5, "yaw": 180.0}
RIGHT_SAME = {"lane_id": -2, "y": 8.5}


def _scenario(**target):
    return {"schema": S.SCHEMA_2, "egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1, "map": "Carla/Maps/Town10HD_Opt",
            "note": "test", "target": {**TARGET, **target}}


def _loc(x, y, z):
    return SimpleNamespace(x=x, y=y, z=z)


class _Waypoint:
    """A straight lane along +x at road height 0.0, with an optional junction span, branch point and lane end."""

    def __init__(self, x, lane_map):
        self.x, self.map = x, lane_map
        self.is_junction = lane_map.junction is not None and lane_map.junction[0] <= x < lane_map.junction[1]
        self.transform = SimpleNamespace(location=_loc(x, 5.0, 0.0), rotation=SimpleNamespace(pitch=0.0, yaw=0.0, roll=0.0))
        self.lane_id, self.road_id, self.lane_type = lane_map.ego_lane_id, ROAD_ID, "Driving"

    def _beside(self, side):
        self.map.sides_asked.append(side)
        spec = self.map.lanes.get(side)
        if spec is None:
            return None
        return SimpleNamespace(lane_id=spec["lane_id"], road_id=spec.get("road_id", ROAD_ID), lane_type=spec.get("lane_type", "Driving"),
                               is_junction=spec.get("junction", False),
                               transform=SimpleNamespace(location=_loc(self.x, spec["y"], spec.get("z", 0.0)),
                                                         rotation=SimpleNamespace(pitch=0.0, yaw=spec.get("yaw", 0.0), roll=0.0)))

    def get_left_lane(self):
        return self._beside("left")

    def get_right_lane(self):
        return self._beside("right")

    def next(self, distance):
        self.map.asked.append(distance)
        nx = self.x + distance
        if self.map.end_at is not None and nx > self.map.end_at:
            return []
        branches = 2 if self.map.branch_at is not None and self.x < self.map.branch_at <= nx else 1
        return [_Waypoint(nx, self.map) for _ in range(branches)]


class _LaneMap:
    def __init__(self, junction=None, branch_at=None, end_at=None, on_lane=True, lanes=None, ego_lane_id=EGO_LANE_ID):
        self.junction, self.branch_at, self.end_at, self.on_lane, self.asked = junction, branch_at, end_at, on_lane, []
        self.lanes, self.ego_lane_id, self.sides_asked = lanes or {}, ego_lane_id, []
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
    ({k: v for k, v in _scenario().items() if k != "egoBlueprint"}, "missing live-scenario members"),
    ({k: v for k, v in _scenario().items() if k != "spawnPointIndex"}, "missing live-scenario members"),
    ({k: v for k, v in _scenario().items() if k != "map"}, "missing live-scenario members"),
    ({**_scenario(), "egoBlueprint": "walker.pedestrian.0001"}, "egoBlueprint"),
    ({**_scenario(), "egoBlueprint": None}, "egoBlueprint"),
    ({**_scenario(), "spawnPointIndex": True}, "spawnPointIndex"),
    ({**_scenario(), "spawnPointIndex": "1"}, "spawnPointIndex"),
    ({**_scenario(), "spawnPointIndex": -1}, "spawnPointIndex"),
    ({**_scenario(), "spawnPointIndex": 1.0}, "spawnPointIndex"),
    ({**_scenario(), "map": 42}, "map must be"),
    ({**_scenario(), "map": ""}, "map must be"),
    ({**_scenario(), "note": {"text": "x"}}, "note must be"),
    ({k: v for k, v in _scenario().items() if k not in ("egoBlueprint", "target")}, "missing live-scenario members"),
    ({**_scenario(), "target": None}, "must be an object"),
    ({**_scenario(), "target": [TARGET]}, "must be an object"),
    ({**_scenario(), "target": {k: v for k, v in TARGET.items() if k != "distanceAheadM"}}, "members must be exactly"),
    ({**_scenario(), "target": {**TARGET, "speedMps": 0.0}}, "members must be exactly"),
    (_scenario(distanceAheadM=0), "distanceAheadM"),
    (_scenario(distanceAheadM=-5.0), "distanceAheadM"),
    (_scenario(distanceAheadM=True), "distanceAheadM"),
    (_scenario(distanceAheadM=math.nan), "distanceAheadM"),
    (_scenario(distanceAheadM=math.inf), "distanceAheadM"),
    (_scenario(distanceAheadM=S.MAX_DISTANCE_M + 0.5), "distanceAheadM"),
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
    assert lane_map.asked == [S.WALK_STEP_M] * 40 and S.WALK_STEP_M == 1.0  # walked in 1 m steps
    assert (at.location.x, at.location.y) == (50.0, 5.0)  # one waypoint 40 m ahead along the lane
    assert at.location.z == pytest.approx(0.6)  # the map's own spawn-point lift above its waypoint, not an invented one
    assert (at.rotation.pitch, at.rotation.yaw, at.rotation.roll) == (0.0, 0.0, 0.0)  # lane heading


def test_wp02_the_walk_ends_exactly_at_a_fractional_distance():
    lane_map = _LaneMap()
    at = target_transform(lane_map, lane_map.points[1], 40.5, CARLA)
    assert len(lane_map.asked) == 41 and lane_map.asked[-1] == 0.5 and at.location.x == 50.5


@pytest.mark.parametrize("lane_map, message", [
    (_LaneMap(end_at=30.0), "0 lane continuations at step 21 of 40"),  # the lane ends before the target
    (_LaneMap(branch_at=50.0), "2 lane continuations at step 40 of 40"),  # a branch at the target
    (_LaneMap(branch_at=25.0), "2 lane continuations at step 15 of 40"),  # a branch between ego and target
    (_LaneMap(junction=(48.0, 60.0)), "junction at step 38 of 40"),  # the target in a junction
    (_LaneMap(junction=(20.0, 30.0)), "junction at step 10 of 40"),  # a junction between ego and target (LOW-1)
    (_LaneMap(junction=(5.0, 15.0)), "ego spawn waypoint lies in a junction"),
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


def test_wp02_close_destroys_every_actor_even_when_one_destroy_fails():
    world = _TargetWorld()
    world.attributes_ok = True
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA, scenario=_scenario())
    target = world.actors[3]

    def refuse():
        raise RuntimeError("destroy failed")
    target.destroy = refuse
    with pytest.raises(RuntimeError, match="owned actors not destroyed: .*xverse-lite-target: RuntimeError: destroy failed"):
        source.close()
    assert world.actors == [target]  # camera, radar and ego destroyed after the target's failure (LOW-5)
    assert len(source.destroy_failed) == 1 and world.settings.synchronous_mode is False  # settings restored


# ---- restore guard -----------------------------------------------------------------------------------


def _killed_run_world(lane_map=None, scenario=None, carla=CARLA):
    """The world a SIGKILLed adapter leaves: owned ego and target alive, synchronous, a registry on disk."""

    world = _TargetWorld(lane_map)
    world.attributes_ok = True
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=carla, scenario=scenario or _scenario())
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


def _adjacent_world():
    return _killed_run_world(_LaneMap(lanes={"left": LEFT_SAME}), _scenario(adjacentLane={"side": "left", "direction": "same"}), CARLA_LANES)


@pytest.mark.parametrize("make", [_killed_run_world, _adjacent_world], ids=["in-lane", "adjacent-lane"])
def test_wp02_restore_guard_holds_and_destroys_the_target_by_registry(make):
    world, registry = make()
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


# ---- WP-02b: adjacent-lane (out-of-corridor) placement ------------------------------------------------


def _adjacent(side="left", direction="same"):
    return _scenario(adjacentLane={"side": side, "direction": direction})


def test_wp02b_without_adjacent_lane_the_placement_is_exactly_wp02():
    lane_map = _LaneMap(lanes={"left": LEFT_SAME, "right": RIGHT_SAME})  # neighbours exist but are never asked for
    at = target_transform(lane_map, lane_map.points[1], 40.0, CARLA)  # CARLA has no LaneType: it is not touched
    assert (at.location.x, at.location.y, at.rotation.yaw) == (50.0, 5.0, 0.0) and at.location.z == pytest.approx(0.6)
    assert lane_map.asked == [S.WALK_STEP_M] * 40 and lane_map.sides_asked == []
    world = _TargetWorld(_LaneMap(lanes={"left": LEFT_SAME}))
    target = spawn(world, CARLA, D, _scenario())[3]
    assert (target.transform.location.x, target.transform.location.y) == (50.0, 5.0) and world.lane_map.sides_asked == []
    assert "adjacentLane" not in target_of(_scenario())


@pytest.mark.parametrize("adjacent, message", [
    (None, "adjacentLane must be an object"),
    ("left", "adjacentLane must be an object"),
    ([{"side": "left", "direction": "same"}], "adjacentLane must be an object"),
    ({}, "adjacentLane members must be exactly"),
    ({"side": "left"}, "adjacentLane members must be exactly"),
    ({"direction": "same"}, "adjacentLane members must be exactly"),
    ({"side": "left", "direction": "same", "laneId": -2}, "adjacentLane members must be exactly"),
    ({"side": "Left", "direction": "same"}, "side must be one of"),
    ({"side": "up", "direction": "same"}, "side must be one of"),
    ({"side": None, "direction": "same"}, "side must be one of"),
    ({"side": "left", "direction": "reverse"}, "direction must be one of"),
    ({"side": "left", "direction": True}, "direction must be one of"),
    ({"side": "left", "direction": None}, "direction must be one of"),
])
def test_wp02b_invalid_adjacent_lane_is_refused_before_anything_is_spawned(adjacent, message):
    scenario = _scenario(adjacentLane=adjacent)
    with pytest.raises(ValueError, match=message):
        target_of(scenario)
    world = _TargetWorld(_LaneMap(lanes={"left": LEFT_SAME}))
    with pytest.raises(ValueError):
        spawn(world, CARLA_LANES, D, scenario)
    assert world.actors == [] and world.lane_map.asked == [] and world.lane_map.sides_asked == []


def test_wp02b_adjacent_lane_is_the_only_optional_target_member():
    for extra in ({"lateralOffsetM": 3.5}, {"adjacentLane": {"side": "left", "direction": "same"}, "lateralOffsetM": 3.5}):
        with pytest.raises(ValueError, match="members must be exactly"):
            target_of(_scenario(**extra))
    with pytest.raises(ValueError, match="needs schema"):  # still schema 2 only
        target_of({"egoBlueprint": "vehicle.audi.etron", "spawnPointIndex": 1, "target": _adjacent()["target"]})


@pytest.mark.parametrize("side, direction, lane, yaw", [
    ("left", "same", LEFT_SAME, 0.0),
    ("right", "same", RIGHT_SAME, 0.0),
    ("left", "opposite", LEFT_OPPOSITE, 180.0),  # an opposite lane keeps its own heading
    ("right", "opposite", {"lane_id": 1, "y": 8.5, "yaw": 180.0}, 180.0),
])
def test_wp02b_target_is_placed_on_the_declared_adjacent_lane(side, direction, lane, yaw):
    lane_map = _LaneMap(lanes={side: lane})
    at = target_transform(lane_map, lane_map.points[1], 40.0, CARLA_LANES, {"side": side, "direction": direction})
    assert lane_map.asked == [S.WALK_STEP_M] * 40 and lane_map.sides_asked == [side]  # the WP-02 walk, then one lateral query
    assert (at.location.x, at.location.y) == (50.0, lane["y"])  # the adjacent lane's centre beside the walk's end
    assert at.location.z == pytest.approx(0.6)  # the map's own spawn-point lift, as in WP-02
    assert (at.rotation.pitch, at.rotation.yaw, at.rotation.roll) == (0.0, yaw, 0.0)  # that lane's own heading


@pytest.mark.parametrize("lane_map, adjacent, message", [
    (_LaneMap(), ("left", "same"), "no lane left of the ego lane"),
    (_LaneMap(lanes={"left": LEFT_SAME}), ("right", "same"), "no lane right of the ego lane"),
    (_LaneMap(lanes={"right": {**RIGHT_SAME, "lane_type": "Shoulder"}}), ("right", "same"), "not a driving lane: Shoulder"),
    (_LaneMap(lanes={"right": {**RIGHT_SAME, "lane_type": "Sidewalk"}}), ("right", "same"), "not a driving lane: Sidewalk"),
    (_LaneMap(lanes={"right": {**RIGHT_SAME, "lane_type": "Parking"}}), ("right", "same"), "not a driving lane: Parking"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "road_id": 8}}), ("left", "same"), "on road 8, not the ego's road 7"),
    (_LaneMap(lanes={"left": LEFT_OPPOSITE}), ("left", "same"), "travels in the opposite direction .* declared same"),
    (_LaneMap(lanes={"left": LEFT_SAME}), ("left", "opposite"), "travels in the same direction .* declared opposite"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "lane_id": 0}}), ("left", "same"), "lane ids must be non-zero ints"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "lane_id": -2.0}}), ("left", "same"), "lane ids must be non-zero ints"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "lane_id": True}}), ("left", "same"), "lane ids must be non-zero ints"),
    (_LaneMap(lanes={"left": LEFT_SAME}, ego_lane_id=0), ("left", "same"), "lane ids must be non-zero ints"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "junction": True}}), ("left", "same"), "lies in a junction at the target position"),
    (_LaneMap(lanes={"left": {**LEFT_SAME, "y": math.nan}}), ("left", "same"), "non-finite target placement"),
])
def test_wp02b_missing_or_mismatched_adjacent_lane_is_refused_before_anything_is_spawned(lane_map, adjacent, message):
    world = _TargetWorld(lane_map)
    with pytest.raises(ValueError, match=message):
        spawn(world, CARLA_LANES, D, _adjacent(*adjacent))
    assert world.actors == []


@pytest.mark.parametrize("lane_map, message", [
    (_LaneMap(end_at=30.0, lanes={"left": LEFT_SAME}), "0 lane continuations at step 21 of 40"),
    (_LaneMap(branch_at=25.0, lanes={"left": LEFT_SAME}), "2 lane continuations at step 15 of 40"),
    (_LaneMap(junction=(20.0, 30.0), lanes={"left": LEFT_SAME}), "junction at step 10 of 40"),
    (_LaneMap(junction=(48.0, 60.0), lanes={"left": LEFT_SAME}), "junction at step 38 of 40"),
    (_LaneMap(junction=(5.0, 15.0), lanes={"left": LEFT_SAME}), "ego spawn waypoint lies in a junction"),
])
def test_wp02b_the_ego_lane_walk_still_refuses_with_an_adjacent_lane(lane_map, message):
    world = _TargetWorld(lane_map)
    with pytest.raises(ValueError, match=message):
        spawn(world, CARLA_LANES, D, _adjacent())
    assert world.actors == [] and lane_map.sides_asked == []  # refused on the walk, before the lateral query


def test_wp02b_adjacent_target_is_spawned_last_owned_registered_and_never_commanded(tmp_path):
    world = _TargetWorld(_LaneMap(lanes={"left": LEFT_SAME}))
    world.attributes_ok = True
    registry = tmp_path / "owned.json"
    source = LiveSource(SimpleNamespace(get_world=lambda: world), -1, -1, -1, D, carla_module=CARLA_LANES,
                        scenario=_adjacent(), registry=str(registry))
    ego, camera, radar, target = world.actors
    assert source._vehicle is ego and target.attributes["role_name"] == S.TARGET_ROLE and TRACK_ROLE.match(S.TARGET_ROLE)
    assert (target.transform.location.x, target.transform.location.y) == (50.0, LEFT_SAME["y"]) and target.parent is None
    assert [(c.throttle, c.brake, c.steer, c.hand_brake) for c in target.controls] == [(0.0, 1.0, 0.0, True)]
    entries = json.loads(registry.read_text())["actors"]
    assert {"id": target.id, "typeId": "vehicle.tesla.model3", "roleName": "xverse-lite-target"} in entries and len(entries) == 4
    source.apply([{"brake": 0.0, "throttle": 0.6}])
    assert len(target.controls) == 1 and [c.steer for c in ego.controls] == [0.0]  # the ego never steers (AD-28)
    source.close()
    assert world.actors == [] and len(target.controls) == 1


def test_wp02b_restore_guard_holds_and_destroys_an_adjacent_target_by_listing():
    world, _ = _adjacent_world()
    target = world.actors[3]
    record = restore(world, CARLA_LANES)
    assert target.id in record["held"] and target.controls[-1].hand_brake is True
    assert "xverse-lite-target" in {d["roleName"] for d in record["destroyed"]} and record["remaining"] == [] and record["restored"]
