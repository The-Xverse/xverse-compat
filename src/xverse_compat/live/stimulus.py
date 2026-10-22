"""Declared driver stimulus (Phase 7): publishes accelerator and brake pedal values on the legacy topics.

It replaces the human at ``vehicle_manual_control.py`` in both the baseline and the Lite run, so both runs
receive the same declared input. Segments are keyed on simulation time since the first
``vehicle/status/clock_status`` sample received (the legacy virtual vehicle and the Lite gateway both
publish ``elapsed_seconds`` there), so the profile follows the simulation, not the wall clock. It
publishes at a fixed host-monotonic period. Stimulus values are owned inputs, declared here.

Usage: ``python -m xverse_compat.live.stimulus --router tcp/127.0.0.1:7447 --out FILE [--linger] [--marker PATH]``
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time

from xverse_compat.live.zenoh_io import Latest, open_session, redirect_stderr

PROFILE = (  # (until simulation seconds since the first clock sample, accelerator pedal, brake pedal)
    (1.0, 0.0, 0.0),
    (4.5, 0.6, 0.0),
    (7.0, 0.0, 0.8),
)
KEYS = {"acc": "vehicle/command/acc_pedal_sts", "brake": "vehicle/command/brake_pedal_sts", "steer": "vehicle/command/steer_sts",
        "clock": "vehicle/status/clock_status", "speed": "vehicle/status/velocity_status"}


def pedals(t: float) -> tuple[float, float, int]:
    for index, (until, acc, brake) in enumerate(PROFILE):
        if t < until:
            return acc, brake, index
    return 0.0, PROFILE[-1][2], len(PROFILE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", default="tcp/127.0.0.1:7447")
    parser.add_argument("--out", required=True)
    parser.add_argument("--period-s", type=float, default=0.05)
    parser.add_argument("--wait-clock-s", type=float, default=60.0, help="host-monotonic bound for the first clock sample")
    parser.add_argument("--linger", action="store_true", help="stay alive after the profile until stopped (Maestro unit)")
    parser.add_argument("--marker", default=None, help="write this marker file when the profile is complete")
    argv = list(sys.argv[1:] if argv is None else argv)
    redirect_stderr(argv)
    args = parser.parse_args(argv)
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append("SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.append("SIGINT"))
    session = open_session(args.router)
    pubs = {k: session.declare_publisher(KEYS[k]) for k in ("acc", "brake", "steer")}
    clock, speed = Latest(session, KEYS["clock"], -1.0), Latest(session, KEYS["speed"], -1.0)
    outcome = "profile-complete"
    with open(args.out, "w", encoding="utf-8") as out:
        out.write(json.dumps({"header": True, "profile": PROFILE, "keys": KEYS, "periodS": args.period_s,
                              "startedWallNs": time.time_ns(), "startedMonotonicNs": time.monotonic_ns()}) + "\n")
        deadline = time.monotonic() + args.wait_clock_s
        while clock.read()[2] == 0:
            if stop or time.monotonic() >= deadline:
                outcome = "no-clock" if not stop else stop[0]
                break
            time.sleep(0.05)
        origin = clock.read()[0]
        next_at = time.monotonic()
        while outcome == "profile-complete" and not stop:
            sim, _, _ = clock.read()
            t = sim - origin
            acc, brake, segment = pedals(t)
            if segment >= len(PROFILE):
                break
            pubs["acc"].put(str(acc))
            pubs["brake"].put(str(brake))
            pubs["steer"].put(str(0.0))
            out.write(json.dumps({"monotonicNs": time.monotonic_ns(), "simS": round(t, 4), "segment": segment, "acc": acc, "brake": brake,
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
