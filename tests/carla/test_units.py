"""V02, V03, V05 and settings: the 3.10 package's units, exercised in-process on owned fakes."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from xverse_compat_carla import codes as C
from xverse_compat_carla.actuation import CommandTracker
from xverse_compat_carla.descriptors import from_mapping, load_descriptors
from xverse_compat_carla.items import ItemBuilder
from xverse_compat_carla.sensors import camera_value, motion_value, radar_value, sensor_origin
from xverse_compat_carla.settings import check_settings
from xverse_compat_carla.sources import FakeSource

from .support import DESCRIPTORS, FIXTURES

D = load_descriptors(DESCRIPTORS)


def _image(**over):
    base = dict(frame=5, timestamp=1.0, width=800, height=600, fov=90.0, raw_data=bytes(800 * 600 * 4))
    base.update(over)
    return SimpleNamespace(**base)


def test_descriptor_constraints():
    data = json.loads(DESCRIPTORS.read_text())
    for path, value in ((("radar", "maxDetections"), 501), (("radar", "rangeM"), 10000.0), (("camera", "fovDeg"), 361.0),
                        (("settings", "fixedDeltaSeconds"), 0), (("radar", "maxDetections"), True)):
        bad = json.loads(json.dumps(data))
        bad[path[0]][path[1]] = value
        with pytest.raises(C.CarlaRefusal) as caught:
            from_mapping(bad)
        assert caught.value.code == C.SETTINGS


def test_settings_check():
    check_settings(SimpleNamespace(synchronous_mode=True, fixed_delta_seconds=0.05), D)
    for settings in (SimpleNamespace(synchronous_mode=False, fixed_delta_seconds=0.05), SimpleNamespace(synchronous_mode=True, fixed_delta_seconds=0.1),
                     SimpleNamespace(synchronous_mode=True)):
        with pytest.raises(C.CarlaRefusal) as caught:
            check_settings(settings, D)
        assert caught.value.code == C.SETTINGS


def test_camera_value_has_no_pixels_and_checks_geometry():
    value = camera_value(_image(), D)
    assert set(value) == {"width", "height", "fovDeg", "rawSha256", "rawLength"} and value["rawLength"] == 1_920_000
    for bad in (_image(width=640), _image(fov=91.0), _image(raw_data=b"\0" * 10)):
        with pytest.raises(C.CarlaRefusal) as caught:
            camera_value(bad, D)
        assert caught.value.code == C.SIZE


def test_radar_quantization_bounds_and_line_bound():
    det = lambda a, z, d, v: SimpleNamespace(altitude=a, azimuth=z, depth=d, velocity=v)
    assert radar_value([det(0.0123456789, -0.1, 42.123456, -3.25)], D)["detections"] == [[0.012346, -0.1, 42.123, -3.25]]
    for bad in ([det(0, 0, 101.0, 0)], [det(0, 0, 1, 101.0)], [det(0, 0.27, 1, 0)], [det(float("nan"), 0, 1, 0)], [det(0, 0, 1, 0)] * 501):
        with pytest.raises(C.CarlaRefusal) as caught:
            radar_value(bad, D)
        assert caught.value.code == C.RANGE
    worst = radar_value([det(-0.087266, -0.261799, 99.999, -99.999)] * 500, D)
    line = json.dumps({"type": "item", "flowId": "radar-adas", "sequence": 10**9, "originNs": 10**18, "frame": 10**9, "value": worst},
                      separators=(",", ":"))
    assert len(line.encode()) < 65536


def test_motion_projection_and_refusal():
    snap = lambda v, a, f: SimpleNamespace(get_velocity=lambda: SimpleNamespace(x=v[0], y=v[1], z=v[2]),
                                           get_acceleration=lambda: SimpleNamespace(x=a[0], y=a[1], z=a[2]),
                                           get_transform=lambda: SimpleNamespace(get_forward_vector=lambda: SimpleNamespace(x=f[0], y=f[1], z=f[2])))
    assert motion_value(snap((3, 4, 0), (-2, 0, 0), (2, 0, 0))) == {"speedMps": 5.0, "accelForwardMps2": -2.0}
    with pytest.raises(C.CarlaRefusal):
        motion_value(snap((3, 4, 0), (0, 0, 0), (0, 0, 0)))


def test_sensor_origin_frame_and_timestamp_rules():
    assert sensor_origin(_image(), 5, "camera") == (5, 1.0)
    with pytest.raises(C.CarlaRefusal) as caught:
        sensor_origin(_image(frame=4), 5, "camera")
    assert caught.value.code == C.FRAME
    for stamp in (None, float("inf"), -1.0, True):
        with pytest.raises(C.CarlaRefusal) as caught:
            sensor_origin(_image(timestamp=stamp), 5, "camera")
        assert caught.value.code == C.TIMESTAMP


def test_items_consecutive_counters_frame_and_episode():
    builder = ItemBuilder(["a"])
    assert builder.emit("a", 10, 1.0, {})["sequence"] == 0
    with pytest.raises(C.CarlaRefusal) as caught:
        builder.emit("a", 10, 1.1, {})
    assert caught.value.code == C.FRAME
    assert builder.emit("a", 12, 1.1, {})["sequence"] == 1  # the refusal consumed no number
    with pytest.raises(C.CarlaRefusal) as caught:
        builder.emit("a", 13, 0.5, {})
    assert caught.value.code == C.EPISODE
    assert builder.emit("a", 14, 1.2, {})["originNs"] == 1_200_000_000


def test_command_window_echo_responded_and_refusals():
    tracker = CommandTracker(D)
    for bad in ({"commandId": "", "brake": 0.5, "deadlineFrames": 1}, {"commandId": "x", "brake": 1.5, "deadlineFrames": 1},
                {"commandId": "x", "brake": 0.5, "deadlineFrames": 3}, {"commandId": "x", "brake": True, "deadlineFrames": 1}):
        with pytest.raises(C.CarlaRefusal):
            tracker.submit(bad)
    tracker.submit({"commandId": "c1", "brake": 0.8, "deadlineFrames": 2})
    with pytest.raises(C.CarlaRefusal):
        tracker.submit({"commandId": "c1", "brake": 0.8, "deadlineFrames": 2})
    tracker.opened(tracker.take_pending(), 10)
    assert tracker.observe(10, 0.0, 0.0) == []
    ack = tracker.observe(11, 0.8, -1.0)
    assert ack == [{"type": "ack", "commandId": "c1", "result": "echoed", "echoFrame": 11, "responded": True}]
    tracker.submit({"commandId": "c2", "brake": 0.4, "deadlineFrames": 2})
    tracker.opened(tracker.take_pending(), 12)
    assert tracker.observe(12, 0.0, None) == [] and tracker.observe(13, 0.0, None)[0]["result"] == "unacknowledged"
    tracker.submit({"commandId": "c3", "brake": 0.1, "deadlineFrames": 1})
    assert tracker.close() == [{"type": "ack", "commandId": "c3", "result": "unacknowledged", "echoFrame": None, "responded": None}]


def test_fake_source_mapping_and_platform_timestamp_canary():
    source = FakeSource(FIXTURES / "nominal.json")
    fd = source.tick()
    assert fd.frame == 100 and fd.camera.raw_data == bytes([0]) * (800 * 600 * 4) and fd.radar.frame == 100
    assert fd.motion.get_transform().get_forward_vector().x == 1.0 and fd.echo_brake == 0.0
    source.apply([{"brake": 0.6}])
    assert source.tick().echo_brake == 0.6
