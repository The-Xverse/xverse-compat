"""Owned live scenario (Phase 7 successor, carla-items/2): spawn the declared ego vehicle and sensors.

The adapter that spawns these actors also owns ``world.tick()`` and the actuator, and destroys them at
close. Every actor carries a ``role_name`` beginning with ``xverse-lite-`` so the restore guard can find
leftovers after a killed run. ``carla`` is passed in (duck-typed), never imported here.

Schema ``xverse-compat.carla-live-scenario/2`` (Phase 8 WP-02, design record
``docs/engineering/phase8/review-wp02.md`` finding 1) adds an optional stationary ``target`` vehicle in the
ego lane, at a declared along-lane distance ahead of the ego spawn point. It is a scenario actor: its hold
control is written once at spawn, and runtime commands reach the ego only. WP-02b (design record
``docs/engineering/phase8/review-wp02b.md`` finding 1) adds an optional ``target.adjacentLane``: the target is
then placed on the centre of the driving lane beside the ego lane at that distance, an out-of-corridor
negative example (the ego never steers, AD-28). Without ``adjacentLane`` the placement is exactly WP-02's.
"""

from __future__ import annotations

import math

ROLE_PREFIX = "xverse-lite-"
SCHEMA_1 = "xverse-compat.carla-live-scenario/1"
SCHEMA_2 = "xverse-compat.carla-live-scenario/2"
TARGET_ROLE = ROLE_PREFIX + "target"
TARGET_HOLD = "brake-and-hand-brake"
SCENARIO_2_MEMBERS = {"schema", "egoBlueprint", "spawnPointIndex", "map", "note", "target"}
SCENARIO_2_REQUIRED = {"schema", "egoBlueprint", "spawnPointIndex", "map"}  # ``note`` and ``target`` are optional
#: The lane is walked from the ego spawn waypoint to the target in steps of at most this length, and every
#: waypoint on the way must be a single continuation outside a junction (review-wp02 finding 4, LOW-1).
WALK_STEP_M = 1.0
#: Instrument guard on the walk (at most 1000 steps), not a protocol value: far beyond the 120 m straight lane
#: of spawn point 1 (K-9) and the 100 m radar range (K-10).
MAX_DISTANCE_M = 1000.0
TARGET_MEMBERS = {"blueprint", "roleName", "distanceAheadM", "hold"}  # all required
TARGET_OPTIONAL = {"adjacentLane"}  # WP-02b; absent means the WP-02 in-lane placement
ADJACENT_MEMBERS = {"side", "direction"}  # both required, no default
ADJACENT_SIDES = ("left", "right")  # relative to the ego lane's direction of travel (get_left_lane / get_right_lane)
ADJACENT_DIRECTIONS = ("same", "opposite")  # that lane's direction of travel relative to the ego lane (lane-id signs)
CAMERA_MOUNT = (1.5, 0.0, 2.4)
RADAR_MOUNT = (2.0, 0.0, 1.0)


def _transform(carla, xyz):
    return carla.Transform(carla.Location(x=xyz[0], y=xyz[1], z=xyz[2]))


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def target_of(scenario):
    """Validate the scenario's schema and return its declared ``target`` or ``None`` (fail-closed).

    Schema 1, or no ``schema`` member, admits no target. Schema 2 admits exactly ``SCENARIO_2_MEMBERS``; an
    absent ``target`` means no target, and a present one needs every ``TARGET_MEMBERS`` entry: there is no
    default distance. The one optional target member, ``adjacentLane`` (WP-02b), needs exactly
    ``ADJACENT_MEMBERS``: there is no default side or direction.
    """

    if not isinstance(scenario, dict):
        raise ValueError("the live scenario must be a JSON object")
    schema = scenario.get("schema", SCHEMA_1)
    if schema == SCHEMA_1:
        if "target" in scenario:
            raise ValueError(f"a target needs schema {SCHEMA_2}")
        return None
    if schema != SCHEMA_2:
        raise ValueError(f"unknown live-scenario schema {schema!r}")
    unknown = set(scenario) - SCENARIO_2_MEMBERS
    if unknown:
        raise ValueError(f"unknown live-scenario members {sorted(unknown)}")
    missing = SCENARIO_2_REQUIRED - set(scenario)
    if missing:
        raise ValueError(f"missing live-scenario members {sorted(missing)}")
    if not isinstance(scenario["egoBlueprint"], str) or not scenario["egoBlueprint"].startswith("vehicle."):
        raise ValueError("egoBlueprint must be a vehicle.* blueprint")
    if type(scenario["spawnPointIndex"]) is not int or scenario["spawnPointIndex"] < 0:
        raise ValueError("spawnPointIndex must be a non-negative int")
    if not isinstance(scenario["map"], str) or not scenario["map"]:
        raise ValueError("map must be a non-empty string")
    if "note" in scenario and not isinstance(scenario["note"], str):
        raise ValueError("note must be a string")
    if "target" not in scenario:
        return None
    target = scenario["target"]
    if not isinstance(target, dict):
        raise ValueError("target must be an object (omit it for no target)")
    if not TARGET_MEMBERS <= set(target) <= TARGET_MEMBERS | TARGET_OPTIONAL:
        raise ValueError(f"target members must be exactly {sorted(TARGET_MEMBERS)}, optionally with {sorted(TARGET_OPTIONAL)}; "
                         f"got {sorted(target)}")
    if not isinstance(target["blueprint"], str) or not target["blueprint"].startswith("vehicle."):
        raise ValueError("target blueprint must be a vehicle.* blueprint")
    if target["roleName"] != TARGET_ROLE:
        raise ValueError(f"target roleName must be {TARGET_ROLE}")
    distance = target["distanceAheadM"]
    if not _finite(distance) or distance <= 0 or distance > MAX_DISTANCE_M:
        raise ValueError(f"target distanceAheadM must be a finite number in (0, {MAX_DISTANCE_M:g}]; got {distance!r}")
    if target["hold"] != TARGET_HOLD:
        raise ValueError(f"target hold must be {TARGET_HOLD!r}")
    if "adjacentLane" in target:
        adjacent = target["adjacentLane"]
        if not isinstance(adjacent, dict):
            raise ValueError("target adjacentLane must be an object (omit it for the in-lane placement)")
        if set(adjacent) != ADJACENT_MEMBERS:
            raise ValueError(f"target adjacentLane members must be exactly {sorted(ADJACENT_MEMBERS)}; got {sorted(adjacent)}")
        if adjacent["side"] not in ADJACENT_SIDES:
            raise ValueError(f"target adjacentLane side must be one of {list(ADJACENT_SIDES)}; got {adjacent['side']!r}")
        if adjacent["direction"] not in ADJACENT_DIRECTIONS:
            raise ValueError(f"target adjacentLane direction must be one of {list(ADJACENT_DIRECTIONS)}; got {adjacent['direction']!r}")
    return target


def adjacent_lane(waypoint, adjacent, carla):
    """Return the waypoint on the driving lane beside ego-lane ``waypoint`` declared by ``adjacent`` (fail-closed).

    The immediate neighbour on the declared side must exist, be a ``carla.LaneType.Driving`` lane of the same
    road, travel in the declared direction (judged by the signs of the two OpenDRIVE lane ids, both non-zero
    ints) and lie outside a junction. ``lane_change`` is not consulted: the ego never steers (AD-28).
    """

    side, direction = adjacent["side"], adjacent["direction"]
    neighbour = waypoint.get_left_lane() if side == "left" else waypoint.get_right_lane()
    if neighbour is None:
        raise ValueError(f"no lane {side} of the ego lane at the target position")
    if neighbour.lane_type != carla.LaneType.Driving:
        raise ValueError(f"the lane {side} of the ego lane at the target position is not a driving lane: {neighbour.lane_type}")
    if neighbour.road_id != waypoint.road_id:
        raise ValueError(f"the lane {side} of the ego lane is on road {neighbour.road_id!r}, not the ego's road {waypoint.road_id!r}")
    ids = (waypoint.lane_id, neighbour.lane_id)
    if not all(type(i) is int and i != 0 for i in ids):
        raise ValueError(f"lane ids must be non-zero ints; got ego {ids[0]!r}, {side} {ids[1]!r}")
    found = "same" if (ids[0] > 0) == (ids[1] > 0) else "opposite"
    if found != direction:
        raise ValueError(f"the lane {side} of the ego lane travels in the {found} direction (lane ids {ids[0]}, {ids[1]}); "
                         f"declared {direction}")
    if neighbour.is_junction:
        raise ValueError(f"the lane {side} of the ego lane lies in a junction at the target position")
    return neighbour


def target_transform(world_map, point, distance, carla, adjacent=None):
    """Return the transform ``distance`` metres ahead of spawn ``point`` along its lane (fail-closed).

    The lane is walked in steps of at most ``WALK_STEP_M``: each step must have exactly one continuation (no
    lane end, no branch) and no waypoint from the spawn waypoint to the target may lie in a junction. The
    rotation is the lane heading; the height is lifted by the map's own spawn-point lift above its waypoint.
    ``get_waypoint`` projects the spawn point onto the nearest driving lane: the lateral placement is a live
    check (R-4). With ``adjacent`` (WP-02b), the target is the walk's last waypoint's neighbour on the declared
    lane (``adjacent_lane``), with that lane's own heading and the same lift; the walk itself is unchanged.
    """

    start = world_map.get_waypoint(point.location)
    if start is None:
        raise ValueError("the ego spawn point is not on a driving lane")
    if start.is_junction:
        raise ValueError("the ego spawn waypoint lies in a junction")
    steps = math.ceil(distance / WALK_STEP_M)
    waypoint = start
    for i in range(steps):
        step = WALK_STEP_M if i < steps - 1 else distance - WALK_STEP_M * (steps - 1)
        ahead = list(waypoint.next(step))
        if len(ahead) != 1:
            raise ValueError(f"{len(ahead)} lane continuations at step {i + 1} of {steps} towards the target; exactly one is required")
        waypoint = ahead[0]
        if waypoint.is_junction:
            raise ValueError(f"the lane enters a junction at step {i + 1} of {steps} towards the target")
    if adjacent is not None:
        waypoint = adjacent_lane(waypoint, adjacent, carla)
    lift = point.location.z - start.transform.location.z
    location, rotation = waypoint.transform.location, waypoint.transform.rotation
    if not all(_finite(v) for v in (lift, location.x, location.y, location.z, rotation.pitch, rotation.yaw, rotation.roll)):
        raise ValueError("non-finite target placement")
    return carla.Transform(carla.Location(x=location.x, y=location.y, z=location.z + lift),
                           carla.Rotation(pitch=rotation.pitch, yaw=rotation.yaw, roll=rotation.roll))


def spawn(world, carla, d, scenario) -> list:
    """Spawn ``[ego, camera, radar]`` (and ``target`` last, schema 2) per ``scenario`` and the sensor descriptors;
    destroy partial spawns on error.

    ``scenario``: ``{"egoBlueprint": str, "spawnPointIndex": int}``, optionally with ``schema`` and, for schema
    2, ``target`` (``target_of``). The target placement is computed before anything is spawned.
    """

    target = target_of(scenario)
    library = world.get_blueprint_library()
    world_map = world.get_map()
    points = world_map.get_spawn_points()
    index = scenario["spawnPointIndex"]
    if type(index) is not int or not 0 <= index < len(points):
        raise ValueError(f"spawnPointIndex {index!r} outside the map's {len(points)} spawn points")
    target_at = None if target is None else target_transform(world_map, points[index], target["distanceAheadM"], carla,
                                                             target.get("adjacentLane"))
    actors = []
    try:
        ego_bp = library.find(scenario["egoBlueprint"])
        ego_bp.set_attribute("role_name", ROLE_PREFIX + "ego")
        actors.append(world.spawn_actor(ego_bp, points[index]))
        camera_bp = library.find(d.camera_blueprint)
        for key, value in (("image_size_x", d.width), ("image_size_y", d.height), ("fov", d.fov_deg), ("role_name", ROLE_PREFIX + "camera")):
            camera_bp.set_attribute(key, str(value))
        actors.append(world.spawn_actor(camera_bp, _transform(carla, CAMERA_MOUNT), attach_to=actors[0]))
        radar_bp = library.find(d.radar_blueprint)
        for key, value in (("range", d.range_m), ("horizontal_fov", d.horizontal_fov_deg), ("vertical_fov", d.vertical_fov_deg),
                           ("role_name", ROLE_PREFIX + "radar")):
            radar_bp.set_attribute(key, str(value))
        actors.append(world.spawn_actor(radar_bp, _transform(carla, RADAR_MOUNT), attach_to=actors[0]))
        if target is not None:
            target_bp = library.find(target["blueprint"])
            target_bp.set_attribute("role_name", TARGET_ROLE)
            actors.append(world.spawn_actor(target_bp, target_at))
            # the one write to the target: a hold at spawn (finding 1, option A); runtime commands reach the ego only
            actors[-1].apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0, hand_brake=True))
    except Exception:
        for actor in reversed(actors):
            actor.destroy()
        raise
    return actors
