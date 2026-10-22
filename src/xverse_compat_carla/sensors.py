"""Duck-typed readers for camera, radar and motion (data model "Values"; design §3, §9.6)."""

from __future__ import annotations

import hashlib
import math

from .codes import FRAME, RANGE, SIZE, TIMESTAMP, CarlaRefusal
from .descriptors import SensorDescriptors

ANGLE_TOLERANCE = 1e-9
FOV_TOLERANCE = 1e-6


def _finite(value) -> bool:
    """Return whether ``value`` is a finite int or float (not bool)."""

    return type(value) in (int, float) and math.isfinite(value)


def sensor_origin(data, tick_frame: int, flow_id: str):
    """Return ``(frame, timestamp)`` of sensor ``data``; the frame must equal the tick frame."""

    stamp = getattr(data, "timestamp", None)  # TIMESTAMP before FRAME (design §9.10, review L4)
    if not _finite(stamp) or stamp < 0:
        raise CarlaRefusal(TIMESTAMP, "sensor timestamp missing or invalid", flow_id, tick_frame)
    frame = getattr(data, "frame", None)
    if frame != tick_frame:
        raise CarlaRefusal(FRAME, "sensor frame differs from the tick frame", flow_id, tick_frame)
    return frame, stamp


def camera_value(image, d: SensorDescriptors, flow_id: str = "camera", frame=None) -> dict:
    """Return ``{width, height, fovDeg, rawSha256, rawLength}``; no pixel bytes."""

    width, height, fov = getattr(image, "width", None), getattr(image, "height", None), getattr(image, "fov", None)
    if width != d.width or height != d.height or not _finite(fov) or abs(fov - d.fov_deg) > FOV_TOLERANCE:
        raise CarlaRefusal(SIZE, "image geometry differs from the descriptor", flow_id, frame)
    raw = bytes(getattr(image, "raw_data", b""))
    if len(raw) != 4 * width * height:
        raise CarlaRefusal(SIZE, "raw_data length is not 4*width*height", flow_id, frame)
    return {"width": width, "height": height, "fovDeg": float(fov), "rawSha256": hashlib.sha256(raw).hexdigest(), "rawLength": len(raw)}


def radar_value(measurement, d: SensorDescriptors, flow_id: str = "radar", frame=None) -> dict:
    """Return ``{detections: [[alt, az, depth, vel], ...], count}`` with fixed quantization."""

    detections = list(measurement)
    if len(detections) > d.max_detections:
        raise CarlaRefusal(RANGE, "too many detections", flow_id, frame)
    half_h = math.radians(d.horizontal_fov_deg) / 2 + ANGLE_TOLERANCE
    half_v = math.radians(d.vertical_fov_deg) / 2 + ANGLE_TOLERANCE
    rows = []
    for det in detections:
        alt, az, depth, vel = (getattr(det, name, None) for name in ("altitude", "azimuth", "depth", "velocity"))
        if not all(_finite(v) for v in (alt, az, depth, vel)):
            raise CarlaRefusal(RANGE, "non-finite detection", flow_id, frame)
        if not (0 <= depth <= d.range_m) or abs(vel) > d.max_velocity_mps or abs(az) > half_h or abs(alt) > half_v:
            raise CarlaRefusal(RANGE, "detection outside the declared bounds", flow_id, frame)
        rows.append([round(alt, 6), round(az, 6), round(depth, 3), round(vel, 3)])
    return {"detections": rows, "count": len(rows)}


def _vec(value):
    """Return ``(x, y, z)`` of a vector-like object as finite floats or raise."""

    out = tuple(getattr(value, axis, None) for axis in ("x", "y", "z"))
    if not all(_finite(v) for v in out):
        raise ValueError("non-finite vector")
    return out


def motion_value(actor_snapshot, flow_id: str = "vehicle-motion", frame=None) -> dict:
    """Return ``{speedMps, accelForwardMps2}`` projected on the forward vector."""

    try:
        v = _vec(actor_snapshot.get_velocity())
        a = _vec(actor_snapshot.get_acceleration())
        f = _vec(actor_snapshot.get_transform().get_forward_vector())
    except (ValueError, AttributeError) as error:
        raise CarlaRefusal(RANGE, f"motion unavailable: {error}", flow_id, frame) from error
    norm = math.sqrt(sum(c * c for c in f))
    if norm == 0:
        raise CarlaRefusal(RANGE, "zero forward vector", flow_id, frame)
    speed = math.sqrt(sum(c * c for c in v))
    accel = sum(ai * fi for ai, fi in zip(a, f)) / norm
    return {"speedMps": round(speed, 6), "accelForwardMps2": round(accel, 6)}
