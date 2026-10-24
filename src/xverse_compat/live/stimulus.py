"""Declared driver stimulus (Phase 7): publishes accelerator and brake pedal values on the legacy topics.

It replaces the human at ``vehicle_manual_control.py`` in both the baseline and the Lite run, so both runs
receive the same declared input. Segments are keyed (DLG-12, review 1 R-3) on host-monotonic
time since the first ``vehicle/status/clock_status`` sample, because the legacy virtual vehicle's
clock_status lags world time; ``--time-base sim`` keys on the published simulation time instead. It
publishes at a fixed host-monotonic period. Stimulus values are owned inputs, declared here.

Usage: ``python -m xverse_compat.live.stimulus --router tcp/127.0.0.1:7447 --out FILE [--linger] [--marker PATH]
[--profile standard|long-run]``. ``long-run`` (thesis S1 FR-018, the S-D1 long-run horizon) repeats the standard
accelerate-then-brake cycle three times (21 s); ``standard`` is unchanged.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time

from xverse_compat.live.readiness import announce_ready
from xverse_compat.live.zenoh_io import Latest, open_session, redirect_stderr

PROFILE = (  # (until simulation seconds since the first clock sample, accelerator pedal, brake pedal)
    (1.0, 0.0, 0.0),
    (4.5, 0.6, 0.0),
    (7.0, 0.0, 0.8),
)
# S1 FR-018: the standard 7 s cycle (1 s idle, 3.5 s accelerate, 2.5 s brake) three times, for the long-run case.
LONG_RUN_PROFILE = tuple((offset + until, acc, brake) for offset in (0.0, 7.0, 14.0) for until, acc, brake in PROFILE)
PROFILES = {"standard": PROFILE, "long-run": LONG_RUN_PROFILE}
KEYS = {"acc": "vehicle/command/acc_pedal_sts", "brake": "vehicle/command/brake_pedal_sts", "steer": "vehicle/command/steer_sts",
        "clock": "vehicle/status/clock_status", "speed": "vehicle/status/velocity_status"}


def pedals(t: float, profile: tuple = PROFILE) -> tuple[float, float, int]:
    for index, (until, acc, brake) in enumerate(profile):
        if t < until:
            return acc, brake, index
    return 0.0, profile[-1][2], len(profile)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", default="tcp/127.0.0.1:7447")
    parser.add_argument("--out", required=True)
    parser.add_argument("--period-s", type=float, default=0.05)
    parser.add_argument("--wait-clock-s", type=float, default=60.0, help="host-monotonic bound for the first clock sample")
    parser.add_argument("--linger", action="store_true", help="stay alive after the profile until stopped (Maestro unit)")
    parser.add_argument("--marker", default=None, help="write this marker file when the profile is complete")
    parser.add_argument("--time-base", choices=("wall", "sim"), default="wall")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="standard")
    argv = list(sys.argv[1:] if argv is None else argv)
    redirect_stderr(argv)
    args = parser.parse_args(argv)
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append("SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.append("SIGINT"))
    session = open_session(args.router)
    pubs = {k: session.declare_publisher(KEYS[k]) for k in ("acc", "brake", "steer")}
    clock, speed = Latest(session, KEYS["clock"], -1.0), Latest(session, KEYS["speed"], -1.0)
    try:  # S1b nonce marker (a no-op without a challenge): the zenoh session, publishers and subscribers are open
        announce_ready()
    except OSError as error:
        print(f"stimulus: readiness: {type(error).__name__}: {error}", file=sys.stderr)
        session.close()
        return 3
    outcome = "profile-complete"
    with open(args.out, "w", encoding="utf-8") as out:
        profile = PROFILES[args.profile]
        out.write(json.dumps({"header": True, "profile": profile, "profileName": args.profile, "keys": KEYS, "periodS": args.period_s,
                              "startedWallNs": time.time_ns(), "startedMonotonicNs": time.monotonic_ns()}) + "\n")
        deadline = time.monotonic() + args.wait_clock_s
        while clock.read()[2] == 0:
            if stop or time.monotonic() >= deadline:
                outcome = "no-clock" if not stop else stop[0]
                break
            time.sleep(0.05)
        origin, wall_origin = clock.read()[0], time.monotonic()
        next_at = wall_origin
        while outcome == "profile-complete" and not stop:
            sim, _, _ = clock.read()
            t = time.monotonic() - wall_origin if args.time_base == "wall" else sim - origin
            acc, brake, segment = pedals(t, profile)
            if segment >= len(profile):
                break
            pubs["acc"].put(str(acc))
            pubs["brake"].put(str(brake))
            pubs["steer"].put(str(0.0))
            out.write(json.dumps({"monotonicNs": time.monotonic_ns(), "profileS": round(t, 4), "timeBase": args.time_base,
                                  "publishedSimS": round(sim - origin, 4), "segment": segment, "acc": acc, "brake": brake,
                                  "speedKmh": speed.read()[0]}) + "\n")
            next_at += args.period_s
            time.sleep(max(0.0, next_at - time.monotonic()))
        if stop and outcome == "profile-complete":
            outcome = stop[0]
        for key in ("acc", "brake"):
            pubs[key].put(str(0.0))  # release the pedals
        out.write(json.dumps({"footer": True, "outcome": outcome, "endedMonotonicNs": time.monotonic_ns()}) + "\n")
    if args.marker:
        with open(args.marker, "w", encoding="utf-8") as marker:
            marker.write(json.dumps({"unit": "stimulus", "outcome": outcome}) + "\n")
    while args.linger and outcome == "profile-complete" and not stop:  # a failed stimulus exits (visible to Maestro)
        time.sleep(0.2)
    session.close()
    return 0 if outcome in ("profile-complete", "SIGTERM", "SIGINT") else 3


if __name__ == "__main__":
    sys.exit(main())
