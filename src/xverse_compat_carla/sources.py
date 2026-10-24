"""Frame sources: ``FakeSource`` (owned fixtures, design §9.3) and ``LiveSource`` (declared-unverified, §9.4).

A source provides ``settings()``, ``apply(commands)`` and ``tick() -> FrameData | None``. The fake source
maps fixture fields onto objects with the CARLA attribute names; any access to ``platform_timestamp``
raises (canary for the never-read rule). ``LiveSource`` imports ``carla`` lazily, never spawns actors
and is exercised only against an owned fake ``carla`` module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .codes import SETTINGS, CarlaRefusal


@dataclass
class FrameData:
    """One tick's data."""

    frame: int
    elapsed_seconds: Any
    camera: Any = None
    radar: Any = None
    motion: Any = None
    echo_brake: Any = None
    actors: Any = None  # None: not collected; the exporter refuses it (review 4 N2)


class _Canary(SimpleNamespace):
    """Fake CARLA object whose ``platform_timestamp`` must never be read (review L5)."""

    @property
    def platform_timestamp(self):
        raise AssertionError("platform_timestamp must never be read")


def _vec(values):
    """Return a vector-like object."""

    x, y, z = values
    return SimpleNamespace(x=x, y=y, z=z)


class FakeSource:
    """Replay an owned fixture (contract rule 8)."""

    def __init__(self, fixture_path) -> None:
        """Load the fixture."""

        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self._settings = SimpleNamespace(synchronous_mode=data["settings"]["synchronous"],
                                         fixed_delta_seconds=data["settings"]["fixedDeltaSeconds"])
        self._frames = list(data["frames"])
        self._index = 0
        self._brake = 0.0

    def settings(self):
        """Return the fixture world settings."""

        return self._settings

    def apply(self, commands) -> None:
        """Apply brake commands (the ``follow`` echo reflects the last one)."""

        for cmd in commands:
            self._brake = cmd["brake"]
            self.throttle = cmd.get("throttle", 0.0)  # protocol 2 (recorded only; the fake has no dynamics)

    def tick(self):
        """Advance to the next fixture frame; ``None`` when exhausted."""

        if self._index >= len(self._frames):
            return None
        raw = self._frames[self._index]
        self._index += 1
        frame = raw["frame"]
        cam = raw.get("camera")
        camera = None if cam is None else _Canary(
            frame=cam.get("frame", frame), timestamp=cam.get("timestamp"), width=cam["width"], height=cam["height"],
            fov=cam["fov"], raw_data=bytes([cam.get("rawFill", 0)]) * cam["rawLength"])
        rad = raw.get("radar")
        radar = None
        if rad is not None:
            detections = [SimpleNamespace(altitude=d[0], azimuth=d[1], depth=d[2], velocity=d[3]) if isinstance(d, list)
                          else SimpleNamespace(**d) for d in rad.get("detections", [])]
            radar = _Measurement(detections, rad.get("frame", frame), rad.get("timestamp"))
        mot = raw.get("motion")
        motion = None if mot is None else _Canary(
            get_velocity=lambda m=mot: _vec(m["velocity"]), get_acceleration=lambda m=mot: _vec(m["acceleration"]),
            get_transform=lambda m=mot: SimpleNamespace(get_forward_vector=lambda: _vec(m["forward"])))
        echo = raw.get("controlEcho", "follow")
        echo_brake = self._brake if echo == "follow" else echo.get("brake")
        return FrameData(frame=frame, elapsed_seconds=raw.get("elapsedSeconds"), camera=camera, radar=radar,
                         motion=motion, echo_brake=echo_brake,
                         actors=list(raw["actors"]) if "actors" in raw else None)

    def close(self) -> None:
        """Nothing to release."""


class _Measurement(list):
    """Radar measurement: an iterable of detections with ``frame`` and ``timestamp``."""

    def __init__(self, detections, frame, timestamp) -> None:
        super().__init__(detections)
        self.frame = frame
        self.timestamp = timestamp

    @property
    def platform_timestamp(self):
        raise AssertionError("platform_timestamp must never be read")


def _check_sensor(name: str, sensor, d) -> None:
    """Refuse (``SETTINGS``) a sensor whose blueprint or attributes differ from the descriptors (review 2 L-i).

    CARLA reports ``type_id`` and string-valued ``attributes`` of a spawned sensor.
    """

    if name == "camera":
        expected = (d.camera_blueprint, {"image_size_x": d.width, "image_size_y": d.height, "fov": d.fov_deg})
    else:
        expected = (d.radar_blueprint, {"range": d.range_m, "horizontal_fov": d.horizontal_fov_deg, "vertical_fov": d.vertical_fov_deg})
    blueprint, attributes = expected
    if sensor is None or getattr(sensor, "type_id", None) != blueprint:
        raise CarlaRefusal(SETTINGS, f"{name} sensor is missing or is not {blueprint}")
    actual = getattr(sensor, "attributes", {}) or {}
    for key, value in attributes.items():
        try:
            matches = abs(float(actual[key]) - float(value)) <= 1e-6
        except (KeyError, TypeError, ValueError):
            matches = False
        if not matches:
            raise CarlaRefusal(SETTINGS, f"{name} attribute {key} differs from the descriptor")


class LiveSource:
    """Declared-unverified live source (design §9.4); never run against a server in this phase."""

    def __init__(self, client, ego_id: int, camera_id: int, radar_id: int, d, carla_module=None, *, scenario=None, registry=None) -> None:
        """Bind to existing actors of ``client``'s world, or, with ``scenario`` (Phase 7 successor), spawn the
        declared ego vehicle and sensors itself, own them, and destroy them at ``close()``."""

        if carla_module is None:
            import carla as carla_module  # noqa: PLC0415 - lazy: only the live path needs the client
        self._carla = carla_module
        self._d = d
        self._spawned = []
        self._world = client.get_world()
        self._ego_id = ego_id
        self._saved = self._world.get_settings()
        settings = self._world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = d.fixed_delta_seconds
        self._world.apply_settings(settings)
        self._sensors = []
        try:
            if scenario is not None:
                from .scenario import spawn  # noqa: PLC0415

                self._spawned = spawn(self._world, carla_module, d, scenario)  # ego, camera, radar[, target] (WP-02)
                if registry is not None:  # owned-actor registry for the restore guard (live finding 06)
                    import json  # noqa: PLC0415

                    with open(registry, "w", encoding="utf-8") as stream:
                        json.dump({"actors": [{"id": a.id, "typeId": a.type_id, "roleName": a.attributes.get("role_name")}
                                              for a in self._spawned]}, stream)
                self._world.tick()  # the spawned actors exist from the next frame
                ego_id, camera_id, radar_id = (actor.id for actor in self._spawned[:3])  # a target is owned, never bound
                self._ego_id = ego_id
            self._vehicle = self._world.get_actor(ego_id)
            if self._vehicle is None or not str(getattr(self._vehicle, "type_id", "")).startswith("vehicle."):
                raise CarlaRefusal(SETTINGS, f"actor {ego_id} is not a vehicle")  # review 2 L-i
            self._queues = {"camera": queue.Queue(), "radar": queue.Queue()}
            for name, actor_id in (("camera", camera_id), ("radar", radar_id)):
                sensor = self._world.get_actor(actor_id)
                _check_sensor(name, sensor, d)
                sensor.listen(self._queues[name].put)
                self._sensors.append(sensor)
        except Exception:
            self.close()  # review L3: never leave the world in synchronous mode after a failed bind
            raise

    def settings(self):
        """Return the applied world settings."""

        return self._world.get_settings()

    def apply(self, commands) -> None:
        """Apply brake commands to the ego vehicle."""

        for cmd in commands:  # steer is held at 0: the Lite actuation path carries no steering
            self._vehicle.apply_control(self._carla.VehicleControl(throttle=cmd.get("throttle", 0.0), brake=cmd["brake"], steer=0.0))

    def _wait(self, name: str, frame: int, deadline: float):
        """Return ``name``'s data for ``frame`` before the per-tick ``deadline``; ``None`` if absent."""

        while True:
            remaining = deadline - time.monotonic()
            try:
                # after the shared deadline only already-queued data is taken (finding 8)
                data = self._queues[name].get(timeout=remaining) if remaining > 0 else self._queues[name].get_nowait()
            except queue.Empty:
                return None
            if data.frame == frame:
                return data
            if data.frame > frame:
                return None

    def tick(self):
        """Advance the world one step and gather that frame's data."""

        frame = self._world.tick()
        deadline = time.monotonic() + self._d.sensor_wait_ms / 1000.0  # one shared wait per tick (rule 7a)
        snapshot = self._world.get_snapshot()
        motion = snapshot.find(self._ego_id) if snapshot.frame == frame else None  # stale snapshot: absent
        return FrameData(frame=frame, elapsed_seconds=snapshot.timestamp.elapsed_seconds, camera=self._wait("camera", frame, deadline),
                         radar=self._wait("radar", frame, deadline), motion=motion, echo_brake=self._vehicle.get_control().brake,
                         actors=None)  # actors are not collected live: an export refuses None (review 3 L5)

    def close(self) -> None:
        """Stop the sensor callbacks and restore the saved world settings (live ground-truth actors are not
        collected in this phase: a stated limit)."""

        try:
            for sensor in getattr(self, "_sensors", []):
                sensor.stop()
            vehicle = getattr(self, "_vehicle", None)
            if vehicle is not None:  # release the actuator (review 1 R-7): hold an owned ego, free a bound vehicle
                owned = bool(getattr(self, "_spawned", []))
                try:  # best effort: a failed release must not mask the original error or skip the restore
                    vehicle.apply_control(self._carla.VehicleControl(throttle=0.0, brake=1.0 if owned else 0.0, steer=0.0, hand_brake=owned))
                except Exception:  # noqa: BLE001 - the restore guard holds owned egos again after the run
                    pass
        finally:  # review 2 L-d: the saved settings are restored even if a stop fails
            try:
                for actor in reversed(getattr(self, "_spawned", [])):  # owned scenario actors: target, sensors, then the ego
                    actor.destroy()
            finally:
                self._world.apply_settings(self._saved)
                if not getattr(self._saved, "synchronous_mode", False):
                    try:  # a synchronous world applies new settings on the next tick (live finding 02)
                        self._world.tick(2.0)
                    except Exception:  # noqa: BLE001 - the restore guard verifies the result afterwards
                        pass
