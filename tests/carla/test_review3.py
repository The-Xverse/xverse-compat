"""Implementation review 3 repairs: M1, LOW items L1 to L5 and the nits."""

from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from xverse_compat.carla_client import CarlaAdapterProcess, CarlaProtocolError, parse_outbound
from xverse_compat_carla import codes as C
from xverse_compat_carla.groundtruth import GroundTruthExporter
from xverse_compat_carla.protocol import ProtocolViolation, parse_inbound, run
from xverse_compat_carla.sources import FakeSource

from .support import DESCRIPTORS, FIXTURES, require_env
from .test_review2 import D, NOMINAL, _adapter, _fixture, _serve


def _proc():
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / 'nominal.json'}")
    proc.start()
    return proc


def _inject(proc, *messages):
    for message in messages:
        proc._lines.put(json.dumps(message) + "\n")
    proc._lines.queue.rotate(len(messages))  # the injected lines are read first


ACK = {"type": "ack", "commandId": "x", "result": "echoed", "echoFrame": 1, "responded": None}
MOTION = {"type": "item", "flowId": "vehicle-motion", "sequence": 0, "originNs": 0, "frame": 1,
          "value": {"speedMps": 1.0, "accelForwardMps2": 0.0}}


@pytest.mark.parametrize("case", ["ordering", "unexpected-status", "pacing"])
def test_m1_every_client_side_violation_kills_the_child(case):
    proc = _proc()
    if case == "pacing":
        proc._awaiting = True
        with pytest.raises(CarlaProtocolError, match="pacing"):
            proc.tick()
    else:
        _inject(proc, *([ACK, MOTION] if case == "ordering" else [{"type": "status", "state": "running", "frame": None}]))
        with pytest.raises(CarlaProtocolError):
            proc.read_until_done()
    assert proc._proc.poll() is not None


def test_l3_client_requires_increasing_ticked_frames():
    proc = _proc()
    first = proc.tick()
    _inject(proc, {"type": "status", "state": "ticked", "frame": first.frame})
    with pytest.raises(CarlaProtocolError, match="does not increase"):
        proc.tick()
    assert proc._proc.poll() is not None


@pytest.mark.parametrize("message", [
    {"type": "ack", "commandId": "x", "result": "echoed", "echoFrame": None, "responded": None},
    {"type": "ack", "commandId": "x", "result": "unacknowledged", "echoFrame": 7, "responded": None},
    {"type": "ack", "commandId": "x", "result": "echoed", "echoFrame": -1, "responded": None},
    {"type": "refusal", "code": C.FRAME, "flowId": "camera", "frame": -1},
    {"type": "status", "state": "ticked", "frame": None},
])
def test_l1_and_nits_outbound_tightening(message):
    with pytest.raises(CarlaProtocolError):
        parse_outbound(json.dumps(message))


def test_nit_inbound_limit_excludes_the_terminator():
    line = '{"type":"tick"}'
    assert parse_inbound(line + " " * (65536 - len(line)) + "\n")["type"] == "tick"
    with pytest.raises(ProtocolViolation):
        parse_inbound(line + " " * (65537 - len(line)) + "\n")


def test_l2_float_image_size_is_refused_and_motion_overflow_is_a_range_refusal(tmp_path):
    first, second = copy.deepcopy(NOMINAL["frames"][0]), copy.deepcopy(NOMINAL["frames"][1])
    first["camera"]["width"] = 800.0
    second["motion"]["velocity"] = [1e308, 1e308, 0.0]
    code, messages, _ = _serve(_fixture(tmp_path, [first, second]), [{"type": "start"}, {"type": "tick"}, {"type": "tick"}])
    refusals = [(m["code"], m["flowId"]) for m in messages if m["type"] == "refusal"]
    assert code == 0 and refusals == [(C.SIZE, "camera"), (C.RANGE, "vehicle-motion")]
    for line in messages:
        if line["type"] == "item":
            parse_outbound(json.dumps(line))  # every emitted item satisfies the client schema


def _bare(frame, elapsed):
    return {"frame": frame, "elapsedSeconds": elapsed, "camera": None, "radar": None, "motion": None, "controlEcho": "follow"}


def test_l3_source_frame_going_back_is_a_source_error(tmp_path):
    lines = [{"type": "start"}, {"type": "tick"}, {"type": "command", "commandId": "c", "brake": 0.5, "deadlineFrames": 1}, {"type": "tick"}]
    code, messages, err = _serve(_fixture(tmp_path, [_bare(10, 0.5), _bare(3, 0.6)]), lines)
    assert code == 3 and [m["type"] for m in messages] == ["hello", "status", "refusal", "ack", "status"]
    assert messages[2]["code"] == C.SOURCE and messages[3]["result"] == "unacknowledged" and "does not increase" in err


def test_l3_elapsed_decrease_without_flows_is_an_episode_reset(tmp_path):
    code, messages, _ = _serve(_fixture(tmp_path, [_bare(10, 0.5), _bare(11, 0.1)]), [{"type": "start"}, {"type": "tick"}, {"type": "tick"}])
    assert code == 3 and [m.get("code") for m in messages if m["type"] == "refusal"] == [C.EPISODE]


def test_l4_valid_lines_before_invalid_utf8_are_served():
    out = _adapter(["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)],
                   b'{"type":"start"}\n{"type":"tick"}\n\xff\n')
    kinds = [json.loads(line)["type"] for line in out.stdout.decode().splitlines()]
    assert out.returncode == 2 and kinds[0] == "hello" and kinds[-1] == "status" and "item" in kinds


def test_l5_uncollected_actors_are_refused_by_the_exporter(tmp_path):
    class Uncollected(FakeSource):
        def tick(self):
            fd = super().tick()
            if fd is not None:
                fd.actors = None
            return fd

    stdin = io.StringIO(json.dumps({"type": "start"}) + "\n" + json.dumps({"type": "tick"}) + "\n")
    out, err = io.StringIO(), io.StringIO()
    export = tmp_path / "gt.jsonl"
    code = run(Uncollected(FIXTURES / "nominal.json"), D, stdin, out, err, ground_truth=export)
    messages = [json.loads(line) for line in out.getvalue().splitlines()]
    assert code == 3 and messages[-2] == {"type": "refusal", "code": C.SOURCE, "flowId": None, "frame": NOMINAL["frames"][0]["frame"]}
    assert export.read_text() == ""
    with pytest.raises(ValueError):
        GroundTruthExporter(tmp_path / "x.jsonl").write(1, 0, None)


def test_review4_l1_negative_elapsed_is_timestamp_only(tmp_path):
    first, second = copy.deepcopy(NOMINAL["frames"][0]), copy.deepcopy(NOMINAL["frames"][1])
    second["elapsedSeconds"] = -1.0
    code, messages, _ = _serve(_fixture(tmp_path, [first, second]), [{"type": "start"}, {"type": "tick"}, {"type": "tick"}])
    assert code == 0 and [m["code"] for m in messages if m["type"] == "refusal"] == [C.TIMESTAMP]


def test_review4_l3_settings_exception_is_a_source_refusal():
    class Lost(FakeSource):
        def settings(self):
            raise RuntimeError("server lost")

    stdin = io.StringIO(json.dumps({"type": "start"}) + "\n")
    out, err = io.StringIO(), io.StringIO()
    code = run(Lost(FIXTURES / "nominal.json"), D, stdin, out, err)
    messages = [json.loads(line) for line in out.getvalue().splitlines()]
    assert code == 3 and [m["type"] for m in messages] == ["hello", "refusal", "status"] and messages[1]["code"] == C.SOURCE
    assert len(err.getvalue().strip().splitlines()) == 1


@pytest.mark.parametrize("run_code", [0, 2])
def test_review4_l3_close_failure_is_one_line_and_exit_3(monkeypatch, capsys, run_code):
    from xverse_compat_carla import main as entry

    closed = []

    class Failing(FakeSource):
        def close(self):
            closed.append(True)
            raise RuntimeError("apply_settings failed")

    monkeypatch.setattr(entry, "FakeSource", Failing)
    monkeypatch.setattr(entry, "run", lambda *a, **k: run_code)
    code = entry.main(["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)])
    assert closed == [True] and code == (run_code or 3)
    assert len(capsys.readouterr().err.strip().splitlines()) == (0 if run_code == 2 else 1)  # exit 2 already wrote its line (review 5 L1)


def test_review5_n1_uncaught_run_exception_is_one_line_and_exit_3(monkeypatch, capsys):
    from xverse_compat_carla import main as entry

    closed = []

    class Tracked(FakeSource):
        def close(self):
            closed.append(True)

    def broken(*args, **kwargs):
        raise BrokenPipeError("stdout closed")

    monkeypatch.setattr(entry, "FakeSource", Tracked)
    monkeypatch.setattr(entry, "run", broken)
    code = entry.main(["--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)])
    err = capsys.readouterr().err.strip().splitlines()
    assert code == 3 and closed == [True] and len(err) == 1 and "BrokenPipeError" in err[0]


def test_review5_n2_bool_elapsed_is_not_exported(tmp_path):
    frame = copy.deepcopy(NOMINAL["frames"][0])
    frame["elapsedSeconds"] = True
    stdin = io.StringIO(json.dumps({"type": "start"}) + "\n" + json.dumps({"type": "tick"}) + "\n")
    out, err = io.StringIO(), io.StringIO()
    export = tmp_path / "gt.jsonl"
    code = run(FakeSource(_fixture(tmp_path, [frame])), D, stdin, out, err, ground_truth=export)
    refusals = [json.loads(line)["code"] for line in out.getvalue().splitlines() if json.loads(line)["type"] == "refusal"]
    assert code == 0 and refusals == [C.TIMESTAMP] and export.read_text() == ""


def test_review5_n3_wait_kills_the_child_on_timeout():
    import subprocess

    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / 'nominal.json'}", timeout_s=0.2)
    proc._proc = subprocess.Popen(["sleep", "30"])
    with pytest.raises(subprocess.TimeoutExpired):
        proc.wait()
    assert proc._proc.poll() is not None


def test_review4_n2_missing_fixture_actors_are_not_an_empty_scene(tmp_path):
    frame = copy.deepcopy(NOMINAL["frames"][0])
    del frame["actors"]
    assert FakeSource(_fixture(tmp_path, [frame])).tick().actors is None


def test_review6_m1_broken_stdout_exits_3_with_one_stderr_line():
    import subprocess

    from .support import ROOT

    import os

    read_end, write_end = os.pipe()
    os.close(read_end)  # the platform side has gone away before the adapter writes anything (deterministic; check 7 L2)
    proc = subprocess.Popen(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                             "xverse_compat_carla.main", "--source", f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS)],
                            cwd=ROOT / "src", stdin=subprocess.PIPE, stdout=write_end, stderr=subprocess.PIPE)
    os.close(write_end)
    try:
        proc.stdin.write(b'{"type":"start"}\n{"type":"tick"}\n')
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode().strip().splitlines()
    assert proc.wait(timeout=60) == 3
    assert len(err) == 1 and err[0].startswith(C.SOURCE) and "BrokenPipeError" in err[0]
