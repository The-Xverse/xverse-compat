"""Owned live scenario (Phase 7 successor, carla-items/2): spawn the declared ego vehicle and sensors.

The adapter that spawns these actors also owns ``world.tick()`` and the actuator, and destroys them at
close. Every actor carries a ``role_name`` beginning with ``xverse-lite-`` so the restore guard can find
leftovers after a killed run. ``carla`` is passed in (duck-typed), never imported here.
"""

from __future__ import annotations

ROLE_PREFIX = "xverse-lite-"
CAMERA_MOUNT = (1.5, 0.0, 2.4)
RADAR_MOUNT = (2.0, 0.0, 1.0)


def _transform(carla, xyz):
    return carla.Transform(carla.Location(x=xyz[0], y=xyz[1], z=xyz[2]))


def spawn(world, carla, d, scenario) -> list:
    """Spawn ``[ego, camera, radar]`` per ``scenario`` and the sensor descriptors; destroy partial spawns on error.

    ``scenario``: ``{"egoBlueprint": str, "spawnPointIndex": int}``.
    """

    library = world.get_blueprint_library()
    points = world.get_map().get_spawn_points()
    index = scenario["spawnPointIndex"]
    if type(index) is not int or not 0 <= index < len(points):
        raise ValueError(f"spawnPointIndex {index!r} outside the map's {len(points)} spawn points")
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
    except Exception:
        for actor in reversed(actors):
            actor.destroy()
        raise
    return actors
