"""V04, V06 and termination: the 3.10 adapter process in fake mode through ``CarlaAdapterProcess``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from xverse_compat.carla_client import CarlaAdapterProcess, CarlaProtocolError, parse_outbound

from .support import DESCRIPTORS, FIXTURES, require_env


def _children() -> set[int]:
    pids = set()
    for task in Path(f"/proc/{os.getpid()}/task").iterdir():
        text = (task / "children").read_text().split()
        pids.update(int(p) for p in text)
    return pids


def _start(name, **kw):
    proc = CarlaAdapterProcess(require_env(), DESCRIPTORS, f"fake:{FIXTURES / name}", **kw)
    hello = proc.start()
    return proc, hello


def test_v06_nominal_items_through_the_platform_receiver():
    from xverse.flows import FlowItem, FlowReceiver, TickClock
    from xverse.flows.binding import FlowBinding, FlowPolicy
    from xverse.flows.timebase import TimeMapping

    before = _children()
    proc, hello = _start("nominal.json")
    assert hello["python"].startswith("3.10.") and hello["source"] == "fake" and hello["carlaVersion"] is None
    assert hello["flows"] == ["camera", "radar-adas", "radar-vc", "vehicle-motion"]
    domain = "carla-simulation"
    binding = FlowBinding("camera", "cam-out", "ecu-in", "camera-frames", "ordered", FlowPolicy("fifo", "best-effort", 8, "reject", 0, 0),
                          "best_effort", "per_route_fifo", "loopback", domain, domain, TimeMapping(domain, domain, 0, 0), 100_000_000, 200_000_000)
    clock = TickClock({})
    receiver = FlowReceiver(binding, clock)
    receiver.activate()
    seen = []
    for expected_frame in range(100, 104):
        result = proc.tick()
        assert result.frame == expected_frame and result.refusals == [] and result.done is None
        assert [i["flowId"] for i in result.items] == ["camera", "radar-adas", "radar-vc", "vehicle-motion"]
        camera = result.items[0]
        clock.at(camera["originNs"] + 5_000_000)
        verdict = receiver.receive(FlowItem("camera", camera["sequence"], camera["originNs"]))
        receiver.poll()
        seen.append((camera["sequence"], verdict.verdict, verdict.age_ns))
    assert seen == [(0, "delivered", 5_000_000), (1, "delivered", 5_000_000), (2, "delivered", 5_000_000), (3, "delivered", 5_000_000)]
    last = proc.tick()
    assert last.done is not None and last.done["forbiddenModulesLoaded"] == []
    assert proc.wait() == 0
    assert _children() <= before  # no adapter process survives


def test_v03_refusals_continue_the_stream_without_consuming_numbers():
    proc, _ = _start("faults.json")
    results = [proc.tick() for _ in range(7)]
    codes = [(r["code"], r["flowId"], r["frame"]) for res in results for r in res.refusals]
    assert codes == [("XVERSE-COMPAT-CARLA-SIZE", "camera", 102), ("XVERSE-COMPAT-CARLA-RANGE", "radar-adas", 103),
                     ("XVERSE-COMPAT-CARLA-RANGE", "radar-vc", 103), ("XVERSE-COMPAT-CARLA-FRAME", "camera", 104),
                     ("XVERSE-COMPAT-CARLA-TIMESTAMP", "camera", 105)]
    camera_seq = [i["sequence"] for res in results for i in res.items if i["flowId"] == "camera"]
    radar_seq = [i["sequence"] for res in results for i in res.items if i["flowId"] == "radar-vc"]
    assert camera_seq == [0, 1, 2, 3] and radar_seq == [0, 1, 2, 3, 4, 5]
    code, done = proc.stop()
    assert code == 0 and done.done["forbiddenModulesLoaded"] == []


def test_episode_reset_ends_with_exit_3_after_refusal_and_done():
    proc, _ = _start("episode.json")
    proc.tick(), proc.tick()
    final = proc.tick()
    assert [i["flowId"] for i in final.items] == ["camera", "radar-adas", "radar-vc"]  # earlier flows of the frame stand
    assert [r["code"] for r in final.refusals] == ["XVERSE-COMPAT-CARLA-EPISODE"] and final.done is not None
    assert proc.wait() == 3


def test_asynchronous_settings_refused_before_any_tick():
    proc, _ = _start("asynchronous.json")
    ended = proc.read_until_done()
    assert [r["code"] for r in ended.refusals] == ["XVERSE-COMPAT-CARLA-SETTINGS"] and ended.items == [] and ended.done is not None
    assert proc.wait() == 3


def test_v05_commands_echo_unacknowledged_and_refusals_in_process():
    proc, _ = _start("actuation.json")
    proc.tick()                                   # frame 100
    proc.command("c1", 0.7, 2)
    proc.send_raw({"type": "command", "commandId": "bad", "brake": 2.0, "deadlineFrames": 1})
    proc.send_raw({"type": "launch-missiles"})
    first = proc.tick()                           # frame 101: c1 applied, window 101..102
    assert [r["code"] for r in first.refusals] == ["XVERSE-COMPAT-CARLA-COMMAND", "XVERSE-COMPAT-CARLA-COMMAND"]
    second = proc.tick()                          # frame 102: accel -2.0 -> responded
    assert second.acks == [{"type": "ack", "commandId": "c1", "result": "echoed", "echoFrame": 101, "responded": True}]
    proc.command("c2", 0.9, 2)
    proc.tick()                                   # frame 103: echo forced to 0.3
    mismatch = proc.tick()                        # frame 104
    assert mismatch.acks == [{"type": "ack", "commandId": "c2", "result": "unacknowledged", "echoFrame": None, "responded": False}]
    proc.command("c3", 0.2, 2)
    code, done = proc.stop()
    assert code == 0 and done.acks == [{"type": "ack", "commandId": "c3", "result": "unacknowledged", "echoFrame": None, "responded": None}]


def test_v04_ground_truth_is_a_file_and_never_a_message(tmp_path):
    export = tmp_path / "ground-truth.jsonl"
    proc, _ = _start("nominal.json", ground_truth=export)
    messages = [proc.tick() for _ in range(4)]
    proc.stop()
    rows = [json.loads(line) for line in export.read_text().splitlines()]
    assert [r["frame"] for r in rows] == [100, 101, 102, 103] and all(r["evaluationOnly"] for r in rows)
    assert all("actors" not in json.dumps(i) for res in messages for i in res.items)
    with pytest.raises(CarlaProtocolError):
        parse_outbound(json.dumps({"type": "ground-truth", "frame": 100, "actors": []}))
    with pytest.raises(CarlaProtocolError):
        parse_outbound('{"type":"item","flowId":"camera","sequence":0,"originNs":NaN,"frame":1,"value":{}}')
