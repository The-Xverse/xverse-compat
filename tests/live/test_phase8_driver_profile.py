"""Phase 8 WP-03: the FR-030 driver profile and the ED-15 arbitration, offline (review-wp03 finding 1).

The parameter values below are test-only; no protocol value is set here (AD-27).
"""

from __future__ import annotations

import ast
import io
import json
import math
from pathlib import Path

import pytest

from xverse_compat.carla_client import TickResult
from xverse_compat.live import driver_profile as DP
from xverse_compat.live.driver_profile import ArbitratedDriver, SpeedHold, SpeedHoldParams, arbitrate
from xverse_compat.live.loop import LiteVehicleLoop

RECORD = {"schema": DP.SCHEMA, "targetSpeedMps": 8.0, "kp": 0.5, "ki": 0.2, "throttleMax": 0.8}  # test-only values
PARAMS = SpeedHoldParams.from_record(RECORD)


def _motion(speed):
    return {"flowId": "vehicle-motion", "sequence": 0, "originNs": 0, "frame": 1, "value": {"speedMps": speed, "accelForwardMps2": 0.0}}


class FakeLink:
    """In-process stand-in for the adapter link with a first-order longitudinal vehicle (test-only dynamics)."""

    def __init__(self, dt=0.05):
        self.dt, self.frame, self.speed, self.pending, self.commands = dt, 0, 0.0, None, []

    def command(self, command_id, brake, deadline_frames, throttle=0.0):
        self.pending = (throttle, brake)
        self.commands.append(self.pending)

    def tick(self):
        throttle, brake = self.pending
        accel = 3.0 * throttle - 8.0 * brake - 0.1 * self.speed
        self.speed = max(0.0, self.speed + accel * self.dt)
        self.frame += 1
        item = {"flowId": "vehicle-motion", "sequence": self.frame - 1, "originNs": self.frame * round(self.dt * 1e9), "frame": self.frame,
                "value": {"speedMps": self.speed, "accelForwardMps2": accel}}
        return TickResult(frame=self.frame, items=[item])


def _closed_loop(brake_from_s=None, ticks=600):
    link = FakeLink()
    driver = ArbitratedDriver(PARAMS, lambda s: 1.0 if brake_from_s is not None and s >= brake_from_s else 0.0)
    record = io.StringIO()
    result = LiteVehicleLoop(link, driver, record=record, tick_period_s=0.0, max_ticks=ticks, wall_deadline=float("inf")).run()
    rows = [json.loads(line) for line in record.getvalue().splitlines()]
    return link, result, rows


# ---- parameters --------------------------------------------------------------------------------------


@pytest.mark.parametrize("record, message", [
    ({k: v for k, v in RECORD.items() if k != "targetSpeedMps"}, "members must be exactly"),
    ({k: v for k, v in RECORD.items() if k != "kp"}, "members must be exactly"),
    ({k: v for k, v in RECORD.items() if k != "ki"}, "members must be exactly"),
    ({k: v for k, v in RECORD.items() if k != "throttleMax"}, "members must be exactly"),
    ({k: v for k, v in RECORD.items() if k != "schema"}, "members must be exactly"),
    ({**RECORD, "brakeGain": 1.0}, "members must be exactly"),
    ({**RECORD, "schema": "xverse-compat.driver-profile/2"}, "schema"),
    ({**RECORD, "targetSpeedMps": True}, "finite number"),
    ({**RECORD, "kp": math.nan}, "finite number"),
    ({**RECORD, "ki": math.inf}, "finite number"),
    ({**RECORD, "throttleMax": "0.8"}, "finite number"),
    ({**RECORD, "targetSpeedMps": None}, "finite number"),
    ({**RECORD, "targetSpeedMps": 0.0}, "required"),
    ({**RECORD, "kp": 0.0}, "required"),
    ({**RECORD, "ki": -0.1}, "required"),
    ({**RECORD, "throttleMax": 0.0}, "required"),
    ({**RECORD, "throttleMax": 1.2}, "required"),
    ([RECORD], "must be an object"),
])
def test_wp03_missing_or_invalid_parameters_are_refused_with_no_default(record, message):
    with pytest.raises(ValueError, match=message):
        SpeedHoldParams.from_record(record)


def test_wp03_params_carry_the_record_digest():
    again = SpeedHoldParams.from_record(dict(reversed(list(RECORD.items()))))
    assert PARAMS.digest == again.digest and len(PARAMS.digest) == 64
    assert SpeedHoldParams.from_record({**RECORD, "kp": 0.6}).digest != PARAMS.digest


# ---- speed-hold law ----------------------------------------------------------------------------------


def test_wp03_pi_law_on_simulation_time_with_clamp_and_anti_windup():
    hold = SpeedHold(PARAMS)
    demand, meta = hold.step(0.0, 7.0, hold=False)  # first call: dt 0, proportional only
    assert demand == pytest.approx(0.5) and meta["dtS"] == 0.0 and hold.integral == 0.0
    demand, meta = hold.step(0.5, 7.0, hold=False)  # integral += ki * e * dt = 0.2 * 1 * 0.5
    assert meta["dtS"] == 0.5 and hold.integral == pytest.approx(0.1) and demand == pytest.approx(0.6)
    demand, _ = hold.step(1.0, 0.0, hold=False)  # kp * 8 = 4 saturates: clamped, the integral does not grow
    assert demand == PARAMS.throttle_max and hold.integral == pytest.approx(0.1)
    demand, _ = hold.step(1.0, 10.0, hold=False)  # above the target: never negative (no braking by the driver)
    assert demand == 0.0
    with pytest.raises(ValueError, match="non-decreasing"):
        hold.step(0.9, 7.0, hold=False)
    with pytest.raises(ValueError):
        SpeedHold(PARAMS).step(math.nan, 7.0, hold=False)


def test_wp03_no_motion_item_means_zero_throttle_and_no_integration():
    driver = ArbitratedDriver(PARAMS, lambda s: 0.0)
    for last_motion in (None, {"flowId": "radar-adas", "value": {"speedMps": 1.0}}, _motion(-1.0), _motion(math.nan), _motion(True)):
        throttle, brake, meta = driver(0.0, last_motion)
        assert (throttle, brake, meta["reason"]) == (0.0, 0.0, "no-motion") and driver.hold.integral == 0.0


# ---- arbitration (ED-15) -----------------------------------------------------------------------------


def test_wp03_arbitration_rule():
    assert arbitrate(0.4, 0.0, 0.0) == (0.4, 0.0, False, True)
    assert arbitrate(0.4, 0.3, 0.0) == (0.0, 0.3, True, True)
    assert arbitrate(0.4, 1.0, 0.0) == (0.0, 1.0, True, True)
    for invalid in (None, math.nan, math.inf, -0.1, 1.1, True, "1.0"):
        assert arbitrate(0.4, invalid, 0.7) == (0.0, 0.7, False, False)


def test_wp03_brake_request_forces_throttle_zero_resets_the_integrator_and_release_resumes():
    requests = {0.0: 0.0, 0.5: 0.0, 1.0: 0.6, 1.5: 0.0, 2.0: math.nan, 2.5: 0.0}
    driver = ArbitratedDriver(PARAMS, lambda s: requests[s])
    out = {s: driver(s, _motion(7.5)) for s in requests}  # error 0.5: kp * e = 0.25, unsaturated
    assert out[0.5][:2] == (pytest.approx(0.25 + 0.2 * 0.5 * 0.5), 0.0) and out[0.5][2]["aebActive"] is False
    assert out[1.0][:2] == (0.0, 0.6) and out[1.0][2]["aebActive"] is True and out[1.0][2]["reason"] == "aeb-brake"
    assert out[1.0][2]["integral"] == 0.0  # reset while braking
    assert out[1.5][:2] == (pytest.approx(0.3), 0.0) and out[1.5][2]["integral"] == pytest.approx(0.05)  # resumes from a reset integrator
    assert out[2.0][:2] == (0.0, 0.0) and out[2.0][2]["requestValid"] is False and out[2.0][2]["brakeRequest"] == "nan"
    assert driver.invalid_requests == 1


def test_wp03_invalid_request_holds_the_last_valid_brake():
    requests = iter([0.9, None, -1.0, 0.0])
    driver = ArbitratedDriver(PARAMS, lambda s: next(requests))
    assert [driver(s, _motion(6.0))[:2] for s in (0.0, 0.05, 0.1)] == [(0.0, 0.9), (0.0, 0.9), (0.0, 0.9)]
    assert driver(0.15, _motion(6.0))[1] == 0.0


def test_wp03_the_driver_never_brakes_or_steers():
    for request in (0.0, 0.0, 0.25, 0.0, 1.0, 0.0):
        driver = ArbitratedDriver(PARAMS, lambda s, r=request: r)
        for step, speed in enumerate((0.0, 3.0, 8.0, 12.0, 30.0)):
            command = driver(step * 0.05, _motion(speed))
            assert len(command) == 3 and command[1] == request  # the brake is the AEB request, never the driver's
            assert command[0] == 0.0 or request == 0.0 and 0.0 <= command[0] <= PARAMS.throttle_max
            assert not any("steer" in key.lower() for key in command[2])


# ---- determinism and time base -----------------------------------------------------------------------


def test_wp03_identical_inputs_give_identical_commands(monkeypatch):
    first, _, _ = _closed_loop(brake_from_s=20.0, ticks=500)
    second, _, _ = _closed_loop(brake_from_s=20.0, ticks=500)
    assert first.commands == second.commands and len(first.commands) == 500  # host pacing differs, commands do not


def test_wp03_commands_do_not_depend_on_host_time(monkeypatch):
    inputs = [(i * 0.05, _motion(min(8.5, i * 0.1)), 0.0 if i < 60 else 0.7) for i in range(100)]

    def run():
        driver = ArbitratedDriver(PARAMS, lambda s: next(r for t, _, r in inputs if t == s))
        return [driver(t, motion) for t, motion, _ in inputs]

    reference = run()
    import time as time_module

    def refuse(*_):
        raise AssertionError("host clock read")
    for name in ("time", "time_ns", "monotonic", "monotonic_ns", "perf_counter"):
        monkeypatch.setattr(time_module, name, refuse)
    assert run() == reference


def test_wp03_module_reads_no_clock_randomness_or_transport():
    tree = ast.parse(Path(DP.__file__).read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported == {"__future__", "dataclasses", "hashlib", "json", "math", "typing"}


# ---- closed loop on the Lite loop --------------------------------------------------------------------


def test_wp03_closed_loop_reaches_and_holds_the_speed_then_zeroes_throttle_on_brake():
    link, result, rows = _closed_loop(brake_from_s=25.0, ticks=600)
    ticks = [r for r in rows if r["kind"] == "tick"]
    assert result.end_reason == "max-ticks" and len(ticks) == 600
    held = [r for r in ticks if 15.0 <= r["simS"] < 25.0]
    assert held and all(abs(r["motion"]["speedMps"] - 8.0) < 0.1 for r in held)  # reached and held (fake dynamics)
    # a row's simS is the time after its tick; its command was decided at the previous row's simS (loop.py 94, 115)
    decided = [0.0] + [r["simS"] for r in ticks[:-1]]
    assert all(r["brake"] == 0.0 for r, t in zip(ticks, decided) if t < 25.0)  # the driver never brakes
    braking = [(r, t) for r, t in zip(ticks, decided) if t >= 25.0]
    assert braking and all(r["throttle"] == 0.0 and r["brake"] == 1.0 and r["commandMeta"]["aebActive"] for r, _ in braking)
    assert braking[0][1] == pytest.approx(25.0)  # from the tick whose decision time reaches the request
    assert ticks[-1]["motion"]["speedMps"] == 0.0
    assert {r["commandMeta"]["profileDigest"] for r in ticks} == {PARAMS.digest}
