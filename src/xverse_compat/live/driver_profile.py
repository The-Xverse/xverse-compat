"""FR-030 driver profile and ED-15 arbitration (Phase 8 WP-03; design record ``docs/engineering/phase8/review-wp03.md``).

A deterministic speed-hold driver keyed to simulation time (AD-38 option B): a PI controller on the ego
speed error, where the speed is the adapter's runtime ``vehicle-motion`` item and never the evaluation-only
stream (FR-021). The driver never brakes and has no steering. The arbiter combines its throttle with the AEB
brake request of the tick: an active request forces throttle to zero (ED-15), and after the first request above
0 the throttle stays latched at 0 for the rest of the run (AD-38 amendment, 2026-10-24; review-wp03 finding 4).
A motion item whose ``originNs`` does not advance is stale: throttle 0, no integration. The adapter remains the
single actuator writer; this module only chooses the one command ``LiteVehicleLoop`` sends per tick.

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


def canonical(record: dict) -> str:
    """The digest form of a record (review-wp03 finding 4, LOW-2): every int or float member as a float, then JSON
    with sorted keys and no spaces; Python writes floats in their shortest round-trip form, so 8 and 8.0 agree."""

    return json.dumps({k: float(v) if type(v) in (int, float) else v for k, v in record.items()}, sort_keys=True, separators=(",", ":"))


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
        digest = hashlib.sha256(canonical(record).encode()).hexdigest()
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


def _motion(last_motion):
    """``(speedMps, originNs)`` of a runtime ``vehicle-motion`` item, or ``(None, None)`` when absent or malformed."""

    if not isinstance(last_motion, dict) or last_motion.get("flowId") != "vehicle-motion":
        return None, None
    value, origin = last_motion.get("value"), last_motion.get("originNs")
    speed = value.get("speedMps") if isinstance(value, dict) else None
    if not (_number(speed) and speed >= 0) or type(origin) is not int:
        return None, None
    return speed, origin


def brake_of(request) -> tuple[float | None, bool, bool]:
    """Return ``(brake, valid, clamped)`` for a brake request (finding 4, MEDIUM-2).

    A finite number in [0, 1] is used as is; a finite number above 1 is clamped to 1.0, as Phase 7
    ``VcuCommands`` does. NaN, infinities, bools, negatives and non-numbers are invalid.
    """

    if not _number(request) or request < 0:
        return None, False, False
    if request > 1:
        return 1.0, True, True
    return float(request), True, False


def arbitrate(driver_throttle: float, brake_request, held_brake: float, latched: bool = False) -> tuple[float, float, bool, bool]:
    """ED-15: return ``(throttle, brake, request_valid, brake_clamped)`` for one tick.

    A valid request ``b > 0`` commands ``(0, b)``; ``b == 0`` commands ``(driver_throttle, 0)``, or ``(0, 0)``
    once ``latched`` (AD-38 amendment). An invalid request commands throttle 0 and holds ``held_brake``. The
    driver never contributes a brake value.
    """

    brake, valid, clamped = brake_of(brake_request)
    if not valid:
        return 0.0, held_brake, False, False
    if brake > 0.0 or latched:
        return 0.0, brake, True, clamped
    return driver_throttle, 0.0, True, clamped


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
        self.latched = False  # AD-38 amendment: set at the first tick with a valid brake request above 0
        self.last_origin_ns = None

    def __call__(self, sim_s, last_motion):
        request = self.brake_request(sim_s)
        brake, valid, clamped = brake_of(request)
        if valid and brake > 0.0:
            self.latched = True
        speed, origin = _motion(last_motion)
        stale = speed is not None and self.last_origin_ns is not None and origin <= self.last_origin_ns  # MEDIUM-1
        if origin is not None and not stale:
            self.last_origin_ns = origin
        demand, meta = self.hold.step(sim_s, None if stale else speed, hold=not valid or self.latched)
        throttle, command_brake, valid, clamped = arbitrate(demand, request, self.held_brake, self.latched)
        if valid:
            self.held_brake = command_brake
        else:
            self.invalid_requests += 1
        if not valid:
            reason = "invalid-request"
        elif command_brake > 0.0:
            reason = "aeb-brake"
        elif self.latched:
            reason = "latched"
        elif stale:
            reason = "motion-stale"
        else:
            reason = meta["reason"]
        meta.update(driverThrottle=demand, brakeRequest=request if _number(request) else repr(request), brakeClamped=clamped,
                    requestValid=valid, aebActive=command_brake > 0.0, latched=self.latched, motionStale=stale,
                    motionOriginNs=origin, reason=reason, profileDigest=self.hold.params.digest)
        return throttle, command_brake, meta
