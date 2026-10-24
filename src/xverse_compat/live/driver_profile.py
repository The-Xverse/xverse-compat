"""FR-030 driver profile and ED-15 arbitration (Phase 8 WP-03; design record ``docs/engineering/phase8/review-wp03.md``).

A deterministic speed-hold driver keyed to simulation time (AD-38 option B): a PI controller on the ego
speed error, where the speed is the adapter's runtime ``vehicle-motion`` item and never the evaluation-only
stream (FR-021). The driver never brakes and has no steering. The arbiter combines its throttle with the AEB
brake request of the tick: an active request forces throttle to zero (ED-15). The adapter remains the single
actuator writer; this module only chooses the one command ``LiteVehicleLoop`` sends per tick.

Its parameters are protocol values (AD-27) with no defaults: ``SpeedHoldParams.from_record`` refuses a record
with a missing, extra or ill-typed member. Nothing here reads a clock other than the loop's simulation time.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable

SCHEMA = "xverse-compat.driver-profile/1"
MEMBERS = frozenset({"schema", "targetSpeedMps", "kp", "ki", "throttleMax"})


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class SpeedHoldParams:
    """Validated driver-profile parameters and the digest of their record."""

    target_speed_mps: float
    kp: float
    ki: float
    throttle_max: float
    digest: str

    @classmethod
    def from_record(cls, record) -> "SpeedHoldParams":
        """Validate a ``xverse-compat.driver-profile/1`` record (fail-closed, no defaults)."""

        if not isinstance(record, dict):
            raise ValueError("the driver-profile record must be an object")
        if set(record) != MEMBERS:
            raise ValueError(f"driver-profile members must be exactly {sorted(MEMBERS)}; got {sorted(record)}")
        if record["schema"] != SCHEMA:
            raise ValueError(f"driver-profile schema must be {SCHEMA}")
        for name in ("targetSpeedMps", "kp", "ki", "throttleMax"):
            if not _number(record[name]):
                raise ValueError(f"{name} must be a finite number; got {record[name]!r}")
        if record["targetSpeedMps"] <= 0 or record["kp"] <= 0 or record["ki"] < 0 or not 0 < record["throttleMax"] <= 1:
            raise ValueError("required: targetSpeedMps > 0, kp > 0, ki >= 0, 0 < throttleMax <= 1")
        digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(float(record["targetSpeedMps"]), float(record["kp"]), float(record["ki"]), float(record["throttleMax"]), digest)


class SpeedHold:
    """Discrete PI speed hold on simulation time, with conditional-integration anti-windup."""

    def __init__(self, params: SpeedHoldParams) -> None:
        self.params = params
        self.integral = 0.0
        self.last_sim_s = None

    def step(self, sim_s: float, speed_mps, hold: bool) -> tuple[float, dict]:
        """Return the driver's throttle demand for this tick and its meta.

        ``hold``: the arbiter forces throttle to zero this tick; the integrator is reset (no wound-up surge on
        release). ``speed_mps`` ``None``: no valid runtime motion item; the demand is 0 and nothing integrates.
        """

        if not _number(sim_s) or (self.last_sim_s is not None and sim_s < self.last_sim_s):
            raise ValueError(f"simulation time must be finite and non-decreasing; got {sim_s!r} after {self.last_sim_s!r}")
        dt = 0.0 if self.last_sim_s is None else sim_s - self.last_sim_s
        self.last_sim_s = sim_s
        p = self.params
        if hold:
            self.integral = 0.0
        if speed_mps is None:
            return 0.0, {"speedErrorMps": None, "integral": self.integral, "dtS": dt, "reason": "no-motion"}
        error = p.target_speed_mps - speed_mps
        if not hold:
            candidate = self.integral + p.ki * error * dt
            if 0.0 <= p.kp * error + candidate <= p.throttle_max:  # integrate only while unsaturated
                self.integral = candidate
        demand = min(max(p.kp * error + self.integral, 0.0), p.throttle_max)
        return demand, {"speedErrorMps": error, "integral": self.integral, "dtS": dt, "reason": None}


def _speed(last_motion):
    """The ego speed of a runtime ``vehicle-motion`` item, or ``None`` when absent or malformed."""

    value = last_motion.get("value") if isinstance(last_motion, dict) and last_motion.get("flowId") == "vehicle-motion" else None
    speed = value.get("speedMps") if isinstance(value, dict) else None
    return speed if _number(speed) and speed >= 0 else None


def arbitrate(driver_throttle: float, brake_request, held_brake: float) -> tuple[float, float, bool, bool]:
    """ED-15: return ``(throttle, brake, aeb_active, request_valid)`` for one tick.

    A valid request ``b`` in [0, 1] with ``b > 0`` commands ``(0, b)``; ``b == 0`` commands
    ``(driver_throttle, 0)``. An invalid request commands throttle 0 and holds ``held_brake``. The driver never
    contributes a brake value.
    """

    valid = _number(brake_request) and 0.0 <= brake_request <= 1.0
    if not valid:
        return 0.0, held_brake, False, False
    if brake_request > 0.0:
        return 0.0, float(brake_request), True, True
    return driver_throttle, 0.0, False, True


class ArbitratedDriver:
    """``LiteVehicleLoop`` command source: the FR-030 speed hold under the ED-15 arbitration.

    @param params Validated ``SpeedHoldParams``.
    @param brake_request ``f(sim_s) -> float``: the AEB brake request of the tick, a runtime input.
    """

    def __init__(self, params: SpeedHoldParams, brake_request: Callable[[float], float]) -> None:
        self.hold = SpeedHold(params)
        self.brake_request = brake_request
        self.held_brake = 0.0
        self.invalid_requests = 0

    def __call__(self, sim_s, last_motion):
        request = self.brake_request(sim_s)
        valid = _number(request) and 0.0 <= request <= 1.0
        forced = not valid or request > 0.0
        demand, meta = self.hold.step(sim_s, _speed(last_motion), hold=forced)
        throttle, brake, active, valid = arbitrate(demand, request, self.held_brake)
        if valid:
            self.held_brake = brake
        else:
            self.invalid_requests += 1
        meta.update(driverThrottle=demand, brakeRequest=request if _number(request) else repr(request), aebActive=active,
                    requestValid=valid, profileDigest=self.hold.params.digest)
        if throttle == 0.0 and meta["reason"] is None:
            meta["reason"] = "aeb-brake" if active else ("invalid-request" if not valid else None)
        return throttle, brake, meta
