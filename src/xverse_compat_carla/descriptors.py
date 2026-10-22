"""Sensor and settings descriptors (``carla-sensors.json``; detailed design §2)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from .codes import SETTINGS, CarlaRefusal

SCHEMA = "xverse-compat.carla-sensors/1"


@dataclass(frozen=True)
class SensorDescriptors:
    """Validated descriptor values."""

    fixed_delta_seconds: float
    camera_blueprint: str
    width: int
    height: int
    fov_deg: float
    radar_blueprint: str
    range_m: float
    horizontal_fov_deg: float
    vertical_fov_deg: float
    max_velocity_mps: float
    max_detections: int
    echo_tolerance: float
    deadline_frames: int
    response_accel_mps2: float
    sensor_wait_ms: int


def _num(value, name: str, low: float, high: float, *, integer: bool = False):
    """Return a checked number or raise ``SETTINGS``."""

    if type(value) is bool or not isinstance(value, (int, float)) or (integer and type(value) is not int) or not math.isfinite(value):
        raise CarlaRefusal(SETTINGS, f"{name} is not a finite {'integer' if integer else 'number'}")
    if not (low <= value <= high):
        raise CarlaRefusal(SETTINGS, f"{name} is outside [{low}, {high}]")
    return value


def from_mapping(data: dict) -> SensorDescriptors:
    """Validate a descriptor mapping (refuses with ``SETTINGS``)."""

    try:
        if data["schema"] != SCHEMA or data["settings"]["synchronous"] is not True:
            raise CarlaRefusal(SETTINGS, "unknown schema or asynchronous settings")
        settings, cam, radar, act = data["settings"], data["camera"], data["radar"], data["actuation"]
        delta = _num(settings["fixedDeltaSeconds"], "fixedDeltaSeconds", 1e-6, 1.0)
        return SensorDescriptors(
            fixed_delta_seconds=float(delta),
            camera_blueprint=str(cam["blueprint"]),
            width=_num(cam["width"], "width", 1, 16384, integer=True),
            height=_num(cam["height"], "height", 1, 16384, integer=True),
            fov_deg=float(_num(cam["fovDeg"], "fovDeg", 1e-6, 360.0)),
            radar_blueprint=str(radar["blueprint"]),
            range_m=float(_num(radar["rangeM"], "rangeM", 1e-6, 9999.999)),
            horizontal_fov_deg=float(_num(radar["horizontalFovDeg"], "horizontalFovDeg", 1e-6, 360.0)),
            vertical_fov_deg=float(_num(radar["verticalFovDeg"], "verticalFovDeg", 1e-6, 360.0)),
            max_velocity_mps=float(_num(radar["maxVelocityMps"], "maxVelocityMps", 1e-6, 9999.999)),
            max_detections=_num(radar["maxDetections"], "maxDetections", 1, 500, integer=True),
            echo_tolerance=float(_num(act["echoTolerance"], "echoTolerance", 0.0, 1.0)),
            deadline_frames=_num(act["deadlineFrames"], "deadlineFrames", 1, 1000, integer=True),
            response_accel_mps2=float(_num(act["responseAccelMps2"], "responseAccelMps2", -1000.0, 0.0)),
            sensor_wait_ms=_num(data["sensorWaitMs"], "sensorWaitMs", 1, 60000, integer=True),
        )
    except (KeyError, TypeError) as error:
        raise CarlaRefusal(SETTINGS, f"descriptor member missing or malformed: {error}") from error


def load_descriptors(path) -> SensorDescriptors:
    """Load and validate ``carla-sensors.json``."""

    return from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))
