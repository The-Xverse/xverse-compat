"""Implementation review 2 repairs: N1, N2 and LOW items L-a to L-f, L-h and L-i."""

from __future__ import annotations

import copy
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from xverse_compat.carla_client import CarlaAdapterProcess, CarlaProtocolError, parse_outbound
from xverse_compat_carla import codes as C
from xverse_compat_carla.descriptors import load_descriptors
from xverse_compat_carla.protocol import run
from xverse_compat_carla.sources import FakeSource, LiveSource

from .support import DESCRIPTORS, FIXTURES, ROOT, require_env
from .test_review1 import _FakeWorld

D = load_descriptors(DESCRIPTORS)
NOMINAL = json.loads((FIXTURES / "nominal.json").read_text())
HELLO = {"type": "hello", "protocol": "xverse-compat.carla-items/1", "carlaVersion": None, "python": "3.10.12", "source": "fake",
         "flows": ["camera", "radar-adas", "radar-vc", "vehicle-motion"]}
CAMERA = {"width": 2, "height": 1, "fovDeg": 90.0, "rawSha256": "0" * 64, "rawLength": 8}


def _item(flow, value):
    return json.dumps({"type": "item", "flowId": flow, "sequence": 0, "originNs": 0, "frame": 1, "value": value})


def _adapter(args, stdin=b""):
    python = require_env()
    return subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(python), "-s", "-m", "xverse_compat_carla.main",
                           *args], cwd=ROOT / "src", input=stdin, capture_output=True, timeout=60)


def _fixture(tmp_path, frames):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"settings": NOMINAL["settings"], "frames": frames}))
    return path


def _serve(path, lines):
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in lines))
    out, err = io.StringIO(), io.StringIO()
    code = run(FakeSource(path), D, stdin, out, err)
    return code, [json.loads(line) for line in out.getvalue().splitlines()], err.getvalue()


@pytest.mark.parametrize("line", [
    _item("groundTruth", {"actors": [{"id": 7, "x": 1.0}]}),  # FR-005: ground truth never travels as an item
    _item("camera", {"actors": []}),
    _item("camera", dict(CAMERA, rawLength=9)),
    _item("camera", dict(CAMERA, rawSha256="G" * 64)),
    _item("radar-adas", {"detections": [[0.0, 0.0, 1.0]], "count": 1}),
    _item("radar-vc", {"detections": [], "count": 1}),
    _item("vehicle-motion", {"speedMps": -1.0, "accelForwardMps2": 0.0}),
    _item("vehicle-motion", {"speedMps": 1.0, "accelForwardMps2": 0.0, "extra": 1}),
    json.dumps({"type": "ack", "commandId": 12345, "result": "echoed", "echoFrame": 1, "responded": None}),
    json.dumps({"type": "ack", "commandId": "", "result": "echoed", "echoFrame": 1, "responded": None}),
    json.dumps({"type": "refusal", "code": "XVERSE-COMPAT-CARLA-INVENTED", "flowId": None, "frame": None}),
    json.dumps({"type": "refusal", "code": C.RANGE, "flowId": "groundTruth", "frame": 1}),
    json.dumps(dict(HELLO, python="3.13.13")),
    json.dumps(dict(HELLO, flows=["camera", "groundTruth"])),
    json.dumps(dict(HELLO, carlaVersion="0.9.15")),
    json.dumps(dict(HELLO, source="live")),
])
def test_n1_outbound_schemas_are_exact(line):
    with pytest.raises(CarlaProtocolError):
        parse_outbound(line)


def test_n1_valid_messages_and_announced_flows():
    assert parse_outbound(json.dumps(HELLO))["type"] == "hello"
    assert parse_outbound(json.dumps(dict(HELLO, source="live", carlaVersion="0.9.15")))["source"] == "live"
    assert parse_outbound(_item("camera", CAMERA))["flowId"] == "camera"
    assert parse_outbound(_item("radar-vc", {"detections": [[0.0, 0.1, 2.0, -1.5]], "count": 1}))["value"]["count"] == 1
    with pytest.raises(CarlaProtocolError):
        parse_outbound(_item("camera", CAMERA), ("vehicle-motion",))  # a flow not announced in hello


def test_n2_live_ground_truth_export_is_refused_before_binding(tmp_path):
    out = _adapter(["--source", "live:127.0.0.1:2000:1:2:3", "--descriptors", str(DESCRIPTORS), "--ground-truth", str(tmp_path / "gt.jsonl")])
    assert out.returncode == 3 and out.stdout == b"" and b"fake-source only" in out.stderr
    assert not (tmp_path / "gt.jsonl").exists()


def test_l_a_invalid_utf8_on_stdin_exits_2_under_env_i():
    out = _adapter(["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)], b'{"type":"start"}\n\xff\n')
    lines = out.stdout.decode().splitlines()
    assert out.returncode == 2 and [json.loads(line)["type"] for line in lines] == ["hello"] and C.PROTOCOL.encode() in out.stderr


@pytest.mark.parametrize("case", ["descriptor", "fixture", "ground-truth"])
def test_l_b_construction_failures_exit_3_with_one_stderr_line(tmp_path, case):
    bad_descriptor = tmp_path / "bad.json"
    bad_descriptor.write_text(json.dumps({"schema": "x"}))
    args = {"descriptor": ["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(bad_descriptor)],
            "fixture": ["--source", f"fake:{tmp_path / 'missing.json'}", "--descriptors", str(DESCRIPTORS)],
            "ground-truth": ["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS),
                             "--ground-truth", str(tmp_path / "missing-dir" / "gt.jsonl")]}[case]
    out = _adapter(args)
    assert out.returncode == 3 and out.stdout == b"" and b"Traceback" not in out.stderr
    assert len(out.stderr.decode().strip().splitlines()) == 1 and C.SOURCE.encode() in out.stderr


def test_l_b_non_integer_fixture_frame_is_a_source_error(tmp_path):
    frame = copy.deepcopy(NOMINAL["frames"][0])
    frame["frame"] = "100"
    code, messages, err = _serve(_fixture(tmp_path, [frame]), [{"type": "start"}, {"type": "command", "commandId": "c", "brake": 0.5,
                                                                                    "deadlineFrames": 1}, {"type": "tick"}])
    assert code == 3 and [m["type"] for m in messages] == ["hello", "refusal", "ack", "status"] and messages[1]["code"] == C.SOURCE


def test_l_d_settings_are_restored_when_a_sensor_stop_fails():
    world = _FakeWorld()
    source = LiveSource(SimpleNamespace(get_world=lambda: world), 1, 2, 3, D, carla_module=SimpleNamespace())

    def fail():
        raise RuntimeError("stop failed")

    world.sensors[2].stop = fail
    with pytest.raises(RuntimeError):
        source.close()
    assert world.settings.synchronous_mode is False


def test_l_e_a_refused_motion_sample_does_not_feed_responded(tmp_path):
    first, second = copy.deepcopy(NOMINAL["frames"][0]), copy.deepcopy(NOMINAL["frames"][1])
    first["elapsedSeconds"] = None  # motion TIMESTAMP refusal, despite a strong deceleration
    first["motion"]["acceleration"] = [-5.0, 0.0, 0.0]
    code, messages, _ = _serve(_fixture(tmp_path, [first, second]), [{"type": "start"}, {"type": "command", "commandId": "c", "brake": 0.5,
                                                                                           "deadlineFrames": 2}, {"type": "tick"}, {"type": "tick"}])
    refusals = [m for m in messages if m["type"] == "refusal"]
    acks = [m for m in messages if m["type"] == "ack"]
    assert code == 0 and [r["code"] for r in refusals] == [C.TIMESTAMP]
    assert acks == [{"type": "ack", "commandId": "c", "result": "echoed", "echoFrame": first["frame"], "responded": False}]


def test_l_f_episode_is_checked_before_the_value(tmp_path):
    first, second = copy.deepcopy(NOMINAL["frames"][0]), copy.deepcopy(NOMINAL["frames"][1])
    second["radar"]["timestamp"] = first["radar"]["timestamp"] - 1.0  # episode reset ...
    second["radar"]["detections"] = [[0.0, 0.0, 500.0, 0.0]]  # ... in a sample that is also out of range
    code, messages, _ = _serve(_fixture(tmp_path, [first, second]), [{"type": "start"}, {"type": "tick"}, {"type": "tick"}])
    assert code == 3 and [m["code"] for m in messages if m["type"] == "refusal"] == [C.EPISODE]


def test_l_h_client_reports_an_adapter_that_ends_before_hello(tmp_path):
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{tmp_path / 'missing.json'}")
    with pytest.raises(CarlaProtocolError, match="not hello"):
        proc.start()


def test_l_h_stop_after_the_adapter_ended_on_its_own():
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / 'nominal.json'}")
    proc.start()
    while proc.tick().done is None:
        pass
    proc.wait()
    with pytest.raises(CarlaProtocolError, match="without done"):
        proc.stop()  # no BrokenPipeError: the adapter has exited; its stdout is closed


@pytest.mark.parametrize("change", ["ego", "camera-type", "radar-attribute"])
def test_l_i_bind_checks_ego_and_sensor_descriptors(change):
    world = _FakeWorld()
    if change == "ego":
        world.vehicle.type_id = "walker.pedestrian.0001"
    elif change == "camera-type":
        world.sensors[2].type_id = "sensor.camera.depth"
    else:
        world.sensors[3].attributes["range"] = "50"
    with pytest.raises(C.CarlaRefusal) as refused:
        LiveSource(SimpleNamespace(get_world=lambda: world), 1, 2, 3, D, carla_module=SimpleNamespace())
    assert refused.value.code == C.SETTINGS and world.settings.synchronous_mode is False
