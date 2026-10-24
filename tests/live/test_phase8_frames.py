"""Phase 8 WP-06: the camera raw-frame side channel (review-wp06 finding 1), offline.

In-process tests drive the 3.10 ``FramePublisher`` and the 3.13 ``FrameReceiver`` over a real Unix socket. The
end-to-end tests run the pinned CPython 3.10 adapter on a fake source (``require_env``, as the Phase 7 subprocess
tests). The frame formats here are test-only; no AD-02 value is set.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

import pytest

from xverse_compat.carla_client import SocketAdapterLink
from xverse_compat.live import frames as R
from xverse_compat.live.frames import FrameChannelError, FrameReceiver
from xverse_compat_carla import frames as P
from xverse_compat_carla.frames import FramePublisher

from ..carla.support import DESCRIPTORS, FIXTURES, ROOT, require_env
from .test_phase7_live import _socket_path

SMALL = {"schema": P.FORMAT_SCHEMA, "width": 4, "height": 3, "encoding": "bgra8"}  # test-only, 48 bytes
SENSOR = {"schema": P.FORMAT_SCHEMA, "width": 800, "height": 600, "encoding": "bgra8"}  # test-only, the K-10 geometry


def _item(frame, raw):
    return {"type": "item", "flowId": "camera", "sequence": frame, "originNs": 0, "frame": frame,
            "value": {"width": 4, "height": 3, "fovDeg": 90.0, "rawSha256": hashlib.sha256(raw).hexdigest(), "rawLength": len(raw)}}


def _pair(fmt=SMALL, publisher_fmt=None, capacity=R.CAPACITY):
    path = _socket_path()
    receiver = FrameReceiver(path, fmt, capacity=capacity)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    publisher = FramePublisher(sock, publisher_fmt or fmt)
    return receiver, publisher, sock


def _raw(n, length=48):
    return bytes((n + i) % 256 for i in range(length))


def _wait_end(receiver, bound_s=10.0):
    deadline = time.monotonic() + bound_s
    while receiver.end is None and not receiver.eof and receiver.error is None and time.monotonic() < deadline:
        time.sleep(0.01)


# ---- format and isolation ----------------------------------------------------------------------------


@pytest.mark.parametrize("record", [
    None, {}, {**SMALL, "extra": 1}, {k: v for k, v in SMALL.items() if k != "encoding"}, {**SMALL, "schema": "x"},
    {**SMALL, "width": 0}, {**SMALL, "height": -1}, {**SMALL, "width": 4.0}, {**SMALL, "width": True}, {**SMALL, "encoding": "rgb8"},
])
def test_wp06_an_undeclared_or_malformed_frame_format_is_refused_on_both_sides(record):
    with pytest.raises(ValueError):
        P.load_format(record)
    with pytest.raises(ValueError):
        R.load_format(record)


def test_wp06_both_sides_share_the_protocol_constants():
    assert (P.PROTOCOL, P.FORMAT_SCHEMA, P.ENCODINGS, P.MAX_LINE) == (R.PROTOCOL, R.FORMAT_SCHEMA, R.ENCODINGS, R.MAX_LINE)
    assert P.FORMAT_MEMBERS == R.FORMAT_MEMBERS and P.format_sha256(SMALL) == hashlib.sha256(R._canonical(SMALL)).hexdigest()


def test_wp06_the_adapter_side_imports_only_the_standard_library():
    tree = ast.parse(Path(P.__file__).read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported == {"__future__", "hashlib", "json", "queue", "threading"}  # never xverse_compat (protocol.FORBIDDEN)


# ---- in-process publisher and receiver ---------------------------------------------------------------


def test_wp06_frames_are_verified_against_the_items_raw_sha256():
    receiver, publisher, _ = _pair()
    receiver.start(accept_timeout_s=5)
    frames = {n: _raw(n) for n in (10, 11, 12)}
    for n, raw in frames.items():
        assert publisher.offer(n, raw)
        result = receiver.take(_item(n, raw), wait_s=5)
        assert result.status == "verified" and result.data == raw and "data" not in result.record()
    assert publisher.close() == {"offered": 3, "sent": 3, "dropped": 0, "error": None}
    _wait_end(receiver)
    report = receiver.reconcile()
    assert report["ok"], report and report["summary"]["counts"]["verified"] == 3
    receiver.close()


def test_wp06_a_frame_that_differs_from_its_item_is_a_mismatch_without_bytes():
    receiver, publisher, _ = _pair()
    receiver.start(accept_timeout_s=5)
    publisher.offer(5, _raw(5))
    result = receiver.take(_item(5, _raw(6)), wait_s=5)  # the item describes other bytes
    assert result.status == "mismatch" and result.data is None and result.actualSha256 == hashlib.sha256(_raw(5)).hexdigest()
    publisher.close()
    receiver.close()


def test_wp06_backpressure_drops_are_counted_at_the_adapter_and_reconciled():
    receiver, publisher, _ = _pair(SENSOR)  # 1.92 MB frames exceed the kernel socket buffer
    receiver.start(accept_timeout_s=5)
    raws = {n: _raw(n, 1_920_000) for n in range(12)}
    started = time.monotonic()
    queued = [publisher.offer(n, raw) for n, raw in raws.items()]  # nobody takes yet: the receiver buffer fills
    assert time.monotonic() - started < 2.0  # the tick path never blocks on a slow consumer
    assert publisher.dropped > 0 and publisher.offered == 12 and queued.count(False) == publisher.dropped
    # a frame dropped after the last one sent is announced only by ``end``: until then its take times out as missing
    results = [receiver.take(_item(n, raw), wait_s=0.5) for n, raw in raws.items()]
    summary = publisher.close()
    _wait_end(receiver)
    statuses = [r.status for r in results]
    assert set(statuses) <= {"verified", "dropped", "missing"}
    assert statuses.count("dropped") + statuses.count("missing") == summary["dropped"]
    assert summary["offered"] == summary["sent"] + summary["dropped"]
    report = receiver.reconcile()
    assert report["ok"], report["checks"]
    receiver.close()


def test_wp06_a_failed_socket_counts_every_later_frame_as_dropped():
    receiver, publisher, sock = _pair()
    receiver.start(accept_timeout_s=5)
    receiver.close()  # the platform side goes away
    for n in range(200):
        publisher.offer(n, _raw(n))
        if publisher.error:
            break
    for n in range(200, 205):
        assert publisher.offer(n, _raw(n)) is False
    summary = publisher.close()
    assert summary["error"] and summary["offered"] == summary["sent"] + summary["dropped"]


def test_wp06_a_hello_with_another_format_is_refused():
    receiver, publisher, _ = _pair(SMALL, publisher_fmt={**SMALL, "width": 5})
    with pytest.raises(FrameChannelError, match="declared protocol or frame format"):
        receiver.start(accept_timeout_s=5)
    publisher.close(timeout_s=1)


def test_wp06_offering_bytes_of_another_length_is_refused():
    receiver, publisher, _ = _pair()
    receiver.start(accept_timeout_s=5)
    with pytest.raises(ValueError, match="declared format needs 48"):
        publisher.offer(1, _raw(1, 47))
    publisher.close()
    receiver.close()


def test_wp06_missing_skipped_and_bounded_buffer():
    receiver, publisher, _ = _pair(capacity=2)
    receiver.start(accept_timeout_s=5)
    assert receiver.take(_item(1, _raw(1)), wait_s=0.1).status == "missing"  # never sent within the bound
    for n in (2, 3, 4):  # paced as ticks are: one frame offered after the previous one was sent
        assert publisher.offer(n, _raw(n))
        deadline = time.monotonic() + 5
        while publisher.sent < n - 1 and time.monotonic() < deadline:
            time.sleep(0.01)
    deadline = time.monotonic() + 5
    while receiver.summary()["counts"]["received"] < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert receiver.summary()["buffered"] == 2  # frame 4 is read but waits: the buffer never holds a third frame
    assert receiver.take(_item(3, _raw(3)), wait_s=5).status == "verified"  # frame 2 is superseded
    assert receiver.summary()["counts"]["skipped"] == 1
    assert receiver.take(_item(4, _raw(4)), wait_s=5).status == "verified"
    publisher.close()
    receiver.close()


def _raw_client(path, records):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    sock.sendall(P.canonical({"type": "hello", "protocol": P.PROTOCOL, "format": SMALL, "formatSha256": P.format_sha256(SMALL)}) + b"\n")
    for record in records:
        sock.sendall(record)
    return sock


def test_wp06_an_unreported_sequence_gap_is_lost_and_fails_reconciliation():
    path = _socket_path()
    receiver = FrameReceiver(path, SMALL)
    header = lambda frame, seq, dropped: P.canonical({"type": "frame", "frame": frame, "sequence": seq, "rawSha256":  # noqa: E731
                                                      hashlib.sha256(_raw(frame)).hexdigest(), "rawLength": 48, "dropped": dropped}) + b"\n"
    sock = _raw_client(path, [header(1, 0, 0) + _raw(1), header(3, 2, 0) + _raw(3),  # sequence 1 vanished, no drop reported
                              P.canonical({"type": "end", "offered": 3, "sent": 2, "dropped": 0, "error": None}) + b"\n"])
    receiver.start(accept_timeout_s=5)
    assert [receiver.take(_item(n, _raw(n)), wait_s=5).status for n in (1, 2, 3)] == ["verified", "lost", "verified"]
    _wait_end(receiver)
    report = receiver.reconcile()
    assert not report["ok"] and not report["checks"]["noUnaccountedGap"] and not report["checks"]["absencesExplainedByDrops"]
    assert not report["checks"]["offeredEqualsSentPlusDropped"]
    sock.close()
    receiver.close()


@pytest.mark.parametrize("record", [b"not json\n", b'{"type":"frame"}\n', b'{"type":"mystery"}\n',
                                    P.canonical({"type": "frame", "frame": 1, "sequence": 0, "rawSha256": "0" * 64, "rawLength": 47,
                                                 "dropped": 0}) + b"\n" + b"x" * 47])
def test_wp06_a_protocol_violation_stops_the_channel_and_takes_fail(record):
    path = _socket_path()
    receiver = FrameReceiver(path, SMALL)
    sock = _raw_client(path, [record])
    receiver.start(accept_timeout_s=5)
    result = receiver.take(_item(1, _raw(1)), wait_s=5)
    assert result.status == "failed" and receiver.error and not receiver.reconcile()["ok"]
    sock.close()
    receiver.close()


# ---- end to end with the pinned 3.10 adapter on a fake source ----------------------------------------


def _adapter(link_path, *extra):
    return subprocess.Popen(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                             "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + link_path, "--source",
                             f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), *extra],
                            cwd=ROOT / "src", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _episode(tmp_path, with_frames: bool):
    """Run the fake episode; return (all link messages as dicts, receiver results, receiver reconcile, adapter exit)."""

    link_path = _socket_path()
    link = SocketAdapterLink(link_path, DESCRIPTORS)
    extra, receiver = (), None
    if with_frames:
        frames_path = _socket_path()
        fmt_file = tmp_path / "frame-format.json"
        fmt_file.write_text(json.dumps(SENSOR))
        receiver = FrameReceiver(frames_path, SENSOR)
        extra = ("--frames", "unix:" + frames_path, "--frame-format", str(fmt_file))
    proc = _adapter(link_path, *extra)
    messages, results = [link.start(accept_timeout_s=30)], []
    if receiver is not None:
        receiver.start(accept_timeout_s=30)
    while True:
        step = link.tick()
        messages += step.items + step.refusals + step.acks
        for item in step.items:
            if item["flowId"] == "camera" and receiver is not None:
                results.append(receiver.take(item, wait_s=10))
        if step.done is not None:
            messages.append(step.done)
            break
    code = proc.wait(timeout=30)
    report = None
    if receiver is not None:
        _wait_end(receiver)
        report = receiver.reconcile()
        receiver.close()
    link.kill()
    return messages, results, report, code


def test_wp06_end_to_end_every_camera_item_is_verified_on_the_side_channel(tmp_path):
    messages, results, report, code = _episode(tmp_path, with_frames=True)
    assert code == 0 and messages[-1]["forbiddenModulesLoaded"] == []
    assert [r.status for r in results] == ["verified"] * 4 and report["ok"], report["checks"]
    assert [r.data[0] for r in results] == [0, 1, 2, 3]  # the fixture's per-frame fill bytes
    assert report["summary"]["end"] == {"type": "end", "offered": 4, "sent": 4, "dropped": 0, "error": None}


def test_wp06_no_pixel_bytes_reach_evidence_or_flows(tmp_path):
    messages, results, report, _ = _episode(tmp_path, with_frames=True)
    cameras = [m for m in messages if m.get("flowId") == "camera" and m.get("type") == "item"]
    assert cameras and all(set(m["value"]) == {"width", "height", "fovDeg", "rawSha256", "rawLength"} for m in cameras)
    evidence = [json.dumps(m) for m in messages] + [json.dumps(r.record()) for r in results] + [json.dumps(report)]
    assert max(len(line) for line in evidence) < 1024  # a frame is 1 920 000 bytes; only hashes and counters remain
    assert all(not isinstance(v, (bytes, bytearray, memoryview)) for r in results for v in r.record().values())


def test_wp06_without_the_side_channel_the_link_is_unchanged(tmp_path):
    plain, _, _, code_plain = _episode(tmp_path, with_frames=False)
    with_frames, _, _, code_frames = _episode(tmp_path, with_frames=True)
    assert code_plain == code_frames == 0 and plain == with_frames  # same hello, items, acks and done


@pytest.mark.parametrize("extra, code", [
    (("--frames", "unix:/nonexistent.sock"), 2),  # --frame-format missing
    (("--frame-format", "x.json"), 2),  # --frames missing
    (("--frames", "tcp:1", "--frame-format", "x.json"), 2),
])
def test_wp06_adapter_argument_refusals(extra, code):
    proc = subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                           "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:/nonexistent.sock", "--source",
                           f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), *extra],
                          cwd=ROOT / "src", capture_output=True, timeout=30)
    assert proc.returncode == code


@pytest.mark.parametrize("fmt", [{**SENSOR, "width": 640}, {**SENSOR, "encoding": "rgb8"}, {"schema": P.FORMAT_SCHEMA}])
def test_wp06_adapter_refuses_an_invalid_or_mismatching_declared_format_before_the_protocol(tmp_path, fmt):
    fmt_file = tmp_path / "frame-format.json"
    fmt_file.write_text(json.dumps(fmt))
    proc = subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(require_env()), "-s", "-B", "-m",
                           "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:/nonexistent.sock", "--source",
                           f"fake:{FIXTURES / 'nominal.json'}", "--descriptors", str(DESCRIPTORS), "--frames", "unix:/nonexistent2.sock",
                           "--frame-format", str(fmt_file)], cwd=ROOT / "src", capture_output=True, timeout=30)
    assert proc.returncode == 3 and b"XVERSE-COMPAT-CARLA-SOURCE" in proc.stderr
