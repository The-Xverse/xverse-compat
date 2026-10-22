"""Frame sources: ``FakeSource`` (owned fixtures, design §9.3) and ``LiveSource`` (declared-unverified, §9.4).

A source provides ``settings()``, ``apply(commands)`` and ``tick() -> FrameData | None``. The fake source
maps fixture fields onto objects with the CARLA attribute names; any access to ``platform_timestamp``
raises (canary for the never-read rule). ``LiveSource`` imports ``carla`` lazily, never spawns actors
and is exercised only against an owned fake ``carla`` module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import queue
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


@dataclass
class FrameData:
    """One tick's data."""

    frame: int
    elapsed_seconds: Any
    camera: Any = None
    radar: Any = None
    motion: Any = None
    echo_brake: Any = None
    actors: list = field(default_factory=list)


class _Timestamp(SimpleNamespace):
    """Snapshot timestamp whose ``platform_timestamp`` must never be read."""

    @property
    def platform_timestamp(self):  # pragma: no cover - reaching it is the defect the canary detects
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

    def tick(self):
        """Advance to the next fixture frame; ``None`` when exhausted."""

        if self._index >= len(self._frames):
            return None
        raw = self._frames[self._index]
        self._index += 1
        frame = raw["frame"]
        cam = raw.get("camera")
        camera = None if cam is None else SimpleNamespace(
            frame=cam.get("frame", frame), timestamp=cam.get("timestamp"), width=cam["width"], height=cam["height"],
            fov=cam["fov"], raw_data=bytes([cam.get("rawFill", 0)]) * cam["rawLength"])
        rad = raw.get("radar")
        radar = None
        if rad is not None:
            detections = [SimpleNamespace(altitude=d[0], azimuth=d[1], depth=d[2], velocity=d[3]) if isinstance(d, list)
                          else SimpleNamespace(**d) for d in rad.get("detections", [])]
            radar = _Measurement(detections, rad.get("frame", frame), rad.get("timestamp"))
        mot = raw.get("motion")
        motion = None if mot is None else SimpleNamespace(
            get_velocity=lambda m=mot: _vec(m["velocity"]), get_acceleration=lambda m=mot: _vec(m["acceleration"]),
            get_transform=lambda m=mot: SimpleNamespace(get_forward_vector=lambda: _vec(m["forward"])))
        echo = raw.get("controlEcho", "follow")
        echo_brake = self._brake if echo == "follow" else echo.get("brake")
        return FrameData(frame=frame, elapsed_seconds=raw.get("elapsedSeconds"), camera=camera, radar=radar,
                         motion=motion, echo_brake=echo_brake, actors=list(raw.get("actors", [])))

    def close(self) -> None:
        """Nothing to release."""


class _Measurement(list):
    """Radar measurement: an iterable of detections with ``frame`` and ``timestamp``."""

    def __init__(self, detections, frame, timestamp) -> None:
        super().__init__(detections)
        self.frame = frame
        self.timestamp = timestamp


class LiveSource:
    """Declared-unverified live source (design §9.4); never run against a server in this phase."""

    def __init__(self, client, ego_id: int, camera_id: int, radar_id: int, d, carla_module=None) -> None:
        """Bind to existing actors of ``client``'s world (no spawning)."""

        if carla_module is None:
            import carla as carla_module  # noqa: PLC0415 - lazy: only the live path needs the client
        self._carla = carla_module
        self._d = d
        self._world = client.get_world()
        self._ego_id = ego_id
        self._saved = self._world.get_settings()
        settings = self._world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = d.fixed_delta_seconds
        self._world.apply_settings(settings)
        self._queues = {"camera": queue.Queue(), "radar": queue.Queue()}
        for name, actor_id in (("camera", camera_id), ("radar", radar_id)):
            self._world.get_actor(actor_id).listen(self._queues[name].put)
        self._vehicle = self._world.get_actor(ego_id)

    def settings(self):
        """Return the applied world settings."""

        return self._world.get_settings()

    def apply(self, commands) -> None:
        """Apply brake commands to the ego vehicle."""

        for cmd in commands:
            self._vehicle.apply_control(self._carla.VehicleControl(brake=cmd["brake"]))

    def _wait(self, name: str, frame: int, deadline: float):
        """Return ``name``'s data for ``frame`` before the per-tick ``deadline``; ``None`` if absent."""

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                data = self._queues[name].get(timeout=remaining)
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
                         radar=self._wait("radar", frame, deadline), motion=motion, echo_brake=self._vehicle.get_control().brake)

    def close(self) -> None:
        """Restore the saved world settings."""

        self._world.apply_settings(self._saved)
