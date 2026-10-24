"""Owned live scenario (Phase 7 successor, carla-items/2): spawn the declared ego vehicle and sensors.

The adapter that spawns these actors also owns ``world.tick()`` and the actuator, and destroys them at
close. Every actor carries a ``role_name`` beginning with ``xverse-lite-`` so the restore guard can find
leftovers after a killed run. ``carla`` is passed in (duck-typed), never imported here.

Schema ``xverse-compat.carla-live-scenario/2`` (Phase 8 WP-02, design record
``docs/engineering/phase8/review-wp02.md`` finding 1) adds an optional stationary ``target`` vehicle in the
ego lane, at a declared along-lane distance ahead of the ego spawn point. It is a scenario actor: its hold
control is written once at spawn, and runtime commands reach the ego only.
"""

from __future__ import annotations

import math

ROLE_PREFIX = "xverse-lite-"
SCHEMA_1 = "xverse-compat.carla-live-scenario/1"
SCHEMA_2 = "xverse-compat.carla-live-scenario/2"
TARGET_ROLE = ROLE_PREFIX + "target"
TARGET_HOLD = "brake-and-hand-brake"
SCENARIO_2_MEMBERS = {"schema", "egoBlueprint", "spawnPointIndex", "map", "note", "target"}
TARGET_MEMBERS = {"blueprint", "roleName", "distanceAheadM", "hold"}
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
    default distance.
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
    if "target" not in scenario:
        return None
    target = scenario["target"]
    if not isinstance(target, dict):
        raise ValueError("target must be an object (omit it for no target)")
    if set(target) != TARGET_MEMBERS:
        raise ValueError(f"target members must be exactly {sorted(TARGET_MEMBERS)}; got {sorted(target)}")
    if not isinstance(target["blueprint"], str) or not target["blueprint"].startswith("vehicle."):
        raise ValueError("target blueprint must be a vehicle.* blueprint")
    if target["roleName"] != TARGET_ROLE:
        raise ValueError(f"target roleName must be {TARGET_ROLE}")
    distance = target["distanceAheadM"]
    if not _finite(distance) or distance <= 0:
        raise ValueError(f"target distanceAheadM must be a finite number > 0; got {distance!r}")
    if target["hold"] != TARGET_HOLD:
        raise ValueError(f"target hold must be {TARGET_HOLD!r}")
    return target


def target_transform(world_map, point, distance, carla):
    """Return the transform ``distance`` metres ahead of spawn ``point`` along its lane (fail-closed).

    Exactly one waypoint must lie ahead (no lane end, no branch), outside a junction. The rotation is the
    lane heading; the height is lifted by the map's own spawn-point lift above its waypoint.
    """

    start = world_map.get_waypoint(point.location)
    if start is None:
        raise ValueError("the ego spawn point is not on a driving lane")
    ahead = list(start.next(distance))
    if len(ahead) != 1:
        raise ValueError(f"{len(ahead)} lane waypoints {distance} m ahead of the ego spawn point; exactly one is required")
    waypoint = ahead[0]
    if waypoint.is_junction:
        raise ValueError("the target waypoint lies in a junction")
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
    target_at = None if target is None else target_transform(world_map, points[index], target["distanceAheadM"], carla)
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
