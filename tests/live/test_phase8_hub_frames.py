"""WP-17f observational frame trace. All frames, times and bounds below are TEST-ONLY.

The fake adapter uses explicit actual frame identities. Existing fake role units speak
hub-units/1 over real Unix sockets; no live CARLA or scientific run is started.
"""

from __future__ import annotations

import copy
import json

import pytest

from xverse_compat.carla_client import TickResult
from xverse_compat.live import hub as H
from xverse_compat.live.hub_topology import SCHEMA

from . import test_phase8_hub as T


MOTION_ONLY = {"schema": SCHEMA, "arm": "test", "hubUnit": "u2", "adapterUnit": "u1",
               "units": {"u1": ["carla-client"], "u2": ["loop-gateway"]},
               "flows": [T._flow("f03-motion-raw", T._e("carla-client", "u1"),
                                  [T._e("loop-gateway", "u2")], route="adapter-link")]}


class ObservedLink(T.FakeLink):
    def __init__(self, actual_frames, *, changes=None, no_motion=(), fail_at=None):
        super().__init__(len(actual_frames), no_motion=no_motion)
        self.actual_frames, self.changes, self.fail_at = actual_frames, changes or {}, fail_at

    def tick(self):
        tick = self.tick_count
        if tick == self.fail_at:
            raise RuntimeError("TEST-ONLY adapter exception; this text is not evidence")
        result = super().tick()
        if result.done is None:
            result.frame = self.actual_frames[tick]
            for item in result.items:
                item["frame"] = self.actual_frames[tick]
            if tick in self.changes:
                self.changes[tick](result)
        return result


def hub(link, *, consumers=None, producers=()):
    return H.Hub(MOTION_ONLY, link=link, units_socket_path=T._socket_path(),
                 command_source=lambda sim_s, motion: (0.0, 0.0, {}), wait_bound_s=1, hold_bound_s=1,
                 startup_deadlines_ns={}, connect_timeout_s=1,
                 local_consumers=consumers, local_producers=producers)


def completed(result):
    return [row for row in result.step_frames if row["status"] == "completed"]


def test_observed_frames_and_origin_are_not_step_ordinals_and_records_are_private_json(monkeypatch):
    samples = iter((100, 500, 900, 1000))
    link = ObservedLink([9001, 9002, 9003])
    instance = hub(link)
    monkeypatch.setattr(H.time, "monotonic_ns", lambda: next(samples))
    result = instance.run(4)
    assert result.steps == 3 and result.episode_origin_frame == 9001
    assert instance.schedule.boundaries == [T.T0, T.T0 + T.STEP, T.T0 + 2 * T.STEP]
    assert [row["step"] for row in completed(result)] == [0, 1, 2]
    assert [row["motionFrame"] for row in completed(result)] == [9001, 9002, 9003]
    assert [row["tickedFrame"] for row in completed(result)] == [9001, 9002, 9003]
    assert [row["episodeNs"] for row in completed(result)] == [0, T.STEP, 2 * T.STEP]
    assert [row["hostNs"] for row in completed(result)] == [100, 500, 900]
    assert all(row["frameIssues"] == [] for row in completed(result))
    assert result.step_frames[-1]["status"] == "adapter-done" and result.step_frames[-1]["step"] is None
    assert link.commands == [("t0", 0.0, 0.0), ("t1", 0.0, 0.0), ("t2", 0.0, 0.0), ("t3", 0.0, 0.0)]
    assert link.owner_calls == []  # the hub still does not stop or kill the adapter
    trace = result.frame_trace()
    assert trace["schema"] == H.FRAME_TRACE_SCHEMA and trace["loopOutcome"] == "returned"
    assert trace["episodeOrigin"] == {"motionFrame": 9001, "tickedFrame": 9001,
                                      "simNs": T.T0, "frameIssues": []}
    assert json.loads(json.dumps(trace, allow_nan=False)) == trace
    trace["records"][0]["frameIssues"].append("mutated")
    trace["episodeOrigin"]["frameIssues"].append("mutated")
    assert result.frame_trace()["records"][0]["frameIssues"] == []
    assert result.episode_origin_frame_issues == []


@pytest.mark.parametrize("actual_frames,issue", [([501, 504], "motion-frame-gap"),
                                                ([501, 501], "non-increasing-motion-frame"),
                                                ([501, 500], "non-increasing-motion-frame")])
def test_actual_frame_discontinuity_is_reported_without_interpolation(actual_frames, issue):
    result = hub(ObservedLink(actual_frames)).run(3)
    rows = completed(result)
    assert [row["motionFrame"] for row in rows] == actual_frames
    assert rows[1]["priorMotionFrame"] == actual_frames[0] and issue in rows[1]["frameIssues"]
    assert len(rows) == 2  # no fabricated record for missing frames


@pytest.mark.parametrize("kind,issue", [("motion-missing", "missing-motion-frame"),
                                       ("motion-invalid", "invalid-motion-frame"),
                                       ("ticked-missing", "missing-ticked-frame"),
                                       ("mismatch", "motion-ticked-mismatch"),
                                       ("ambiguous", "ambiguous-motion-items")])
def test_missing_or_mismatched_origin_identity_stays_explicit(kind, issue):
    def alter(result):
        if kind == "motion-missing":
            result.items[0].pop("frame")
        elif kind == "motion-invalid":
            result.items[0]["frame"] = True
        elif kind == "ticked-missing":
            result.frame = None
        elif kind == "mismatch":
            result.items[0]["frame"] = 999
        else:
            result.items.append(copy.deepcopy(result.items[0]))
    result = hub(ObservedLink([700, 701], changes={0: alter})).run(3)
    assert result.steps == 2  # observational flags do not change the existing runtime path
    assert issue in result.episode_origin_frame_issues and issue in result.step_frames[0]["frameIssues"]
    assert result.episode_origin_ticked_frame == (None if kind == "ticked-missing" else 700)
    expected = None if kind in ("motion-missing", "motion-invalid") else 999 if kind == "mismatch" else 700
    assert result.episode_origin_frame == expected
    assert result.episode_origin_frame != 701  # a later good observation cannot replace the origin


def test_tick_without_motion_is_not_given_a_step_or_simulator_stamp():
    result = hub(ObservedLink([800, 801, 802], no_motion=(1,))).run(4)
    gap = result.step_frames[1]
    assert gap["tick"] == 1 and gap["status"] == "no-boundary" and gap["tickedFrame"] == 801
    assert gap["step"] is gap["motionFrame"] is gap["simNs"] is gap["episodeNs"] is None
    assert "no-motion-boundary" in gap["frameIssues"]
    assert [row["step"] for row in completed(result)] == [0, 1]
    assert "motion-frame-gap" in completed(result)[1]["frameIssues"]
    assert result.boundary_gaps == [{"tick": 1, "items": ["radar-adas"],
                                    "reason": "no vehicle-motion item: no step boundary"}]


def test_exception_before_tick_return_leaves_an_explicit_unknown_aborted_attempt():
    instance = hub(ObservedLink([700], fail_at=0))
    with pytest.raises(RuntimeError):
        instance.run(1)
    trace = instance.result.frame_trace()
    row = trace["records"][0]
    assert trace["loopOutcome"] == "raised" and trace["failureType"] == "RuntimeError"
    assert row["status"] == "aborted" and row["phase"] == "adapter-tick"
    assert row["step"] is row["motionFrame"] is row["tickedFrame"] is row["hostNs"] is None
    assert trace["episodeOrigin"] is None and instance.result.steps == 0
    assert "this text is not evidence" not in json.dumps(trace)


def test_partial_registered_step_is_retained_when_local_consumer_raises():
    class Consumer:
        def bind_origin(self, origin):
            pass
        def deliver(self, item):
            raise LookupError("TEST-ONLY consumer exception")
    instance = hub(ObservedLink([812]), consumers={"f03-motion-raw": [Consumer()]})
    with pytest.raises(LookupError):
        instance.run(1)
    row = instance.result.step_frames[0]
    assert row["status"] == "aborted" and row["phase"] == "local-delivery" and row["failureType"] == "LookupError"
    assert row["step"] == 0 and row["motionFrame"] == row["tickedFrame"] == 812
    assert row["simNs"] == T.T0 and row["episodeNs"] == 0 and type(row["hostNs"]) is int
    assert instance.result.steps == 0 and instance.units.path.exists() is False


def test_origin_binding_failure_keeps_the_actual_registered_origin_and_partial_time():
    class Consumer:
        def bind_origin(self, origin):
            raise LookupError("TEST-ONLY bind failure")
    instance = hub(ObservedLink([812]), consumers={"f03-motion-raw": [Consumer()]})
    with pytest.raises(LookupError):
        instance.run(1)
    row = instance.result.step_frames[0]
    assert row["phase"] == "origin-binding" and row["status"] == "aborted"
    assert row["step"] == 0 and row["episodeNs"] == 0
    assert instance.result.frame_trace()["episodeOrigin"]["motionFrame"] == 812


def test_rejected_simulator_boundary_does_not_get_an_invented_registered_step():
    def regress_time(result):
        result.items[0]["originNs"] = T.T0
    instance = hub(ObservedLink([700, 701], changes={1: regress_time}))
    with pytest.raises(H.HubProtocolError):
        instance.run(2)
    row = instance.result.step_frames[1]
    assert row["status"] == "aborted" and row["step"] is None
    assert row["motionFrame"] == 701 and row["simNs"] == T.T0 and row["episodeNs"] == 0
    assert instance.schedule.boundaries == [T.T0] and instance.result.steps == 1


def test_frame_sampling_precedes_fault_relay_hold_and_never_controls_simulator_time(monkeypatch):
    clock = [100]
    monkeypatch.setattr(H.time, "monotonic_ns", lambda: clock[0])
    instance = hub(ObservedLink([700, 701]))
    class Relay:
        # A unit-test seam installed after construction; production's strict FaultRelay type check is unchanged.
        def arm(self):
            pass
        def at_step(self, owner, step, relative_ns):
            assert owner.result.step_frames[-1]["hostNs"] == clock[0]
            clock[0] += 1000  # TEST-ONLY held-work observation
            owner.hold(lambda: True)
        def filter(self, step, due):
            return due  # TEST-ONLY no-message-fault relay; preserve the genuine delivery path.
        def finish(self, last):
            pass
    instance.relay = Relay()
    result = instance.run(3)
    assert [row["hostNs"] for row in completed(result)] == [100, 1100]
    assert [row["episodeNs"] for row in completed(result)] == [0, T.STEP]
    assert instance.schedule.boundaries == [T.T0, T.T0 + T.STEP]


def test_real_socket_units_keep_the_same_deliveries_commands_and_frame_join():
    path = T._socket_path()
    link = ObservedLink([1500, 1501, 1502])
    reader = T.Reader()
    instance, units = T._hub(T.SMALL, path, link, T._small_units(path), local_consumers={H.F17: [reader]},
                             producers=(T._hub_producer(["f-hub-a"]),))
    result = instance.run(4)
    for unit in units:
        unit.join(5)
        assert not unit.is_alive()
    assert [row["motionFrame"] for row in completed(result)] == [1500, 1501, 1502]
    assert all(row["frameIssues"] == [] for row in completed(result))
    assert result.deliveries and result.invalid == [] and result.refused == []
    assert {entry["flowId"] for entry in result.deliveries} == {f["id"] for f in T.SMALL["flows"]}
    assert link.commands == [("t0", 0.0, 0.0), ("t1", 0.0, 0.0), ("t2", 0.0, 0.0), ("t3", 0.0, 0.0)]
    assert link.owner_calls == []
