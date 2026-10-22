"""Passive evaluation observer (Phase 7): records the ego vehicle's motion from CARLA, never feeding runtime.

It never ticks, never applies control and never changes settings. ``world.wait_for_tick`` receives the
frames produced by whichever client owns the tick (the legacy asynchronous server loop in the baseline,
the Lite adapter in a Lite run), so both runs are measured with the same instrument. Output: a JSON Lines
file whose first line is a header with ``evaluationOnly: true``. ``get_control()`` values are the
client-side cached control and are labelled as such; braking is judged from velocity and acceleration.

Usage: ``python -s -m xverse_compat_carla.observe --role ROLE --duration-s S --out FILE [--host H --port P --carla-site DIR]``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import site
import sys
import time


def _vec(v) -> list:
    return [round(v.x, 6), round(v.y, 6), round(v.z, 6)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--role", required=True, help="role_name of the ego vehicle")
    parser.add_argument("--duration-s", type=float, required=True, help="wall-clock observation bound")
    parser.add_argument("--out", required=True)
    parser.add_argument("--carla-site", default=None)
    args = parser.parse_args(argv)
    if args.carla_site:
        site.addsitedir(args.carla_site)
    os.environ.setdefault("HOME", "/nonexistent-carla-home")
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append("SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.append("SIGINT"))
    import carla  # noqa: PLC0415

    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)
    world = client.get_world()
    deadline = time.monotonic() + args.duration_s
    ego = None
    frames = timeouts = 0
    with open(args.out, "w", encoding="utf-8") as out:
        out.write(json.dumps({"header": True, "evaluationOnly": True, "role": args.role, "map": world.get_map().name,
                              "startedWallNs": time.time_ns(), "startedMonotonicNs": time.monotonic_ns()}) + "\n")
        while time.monotonic() < deadline and not stop:
            try:
                snapshot = world.wait_for_tick(1.0)
            except RuntimeError:
                timeouts += 1  # no frame within 1 s (paused or stopped tick owner); keep waiting until the bound
                continue
            frames += 1
            if ego is None or not ego.is_alive:
                matches = [a for a in world.get_actors().filter("vehicle.*") if a.attributes.get("role_name") == args.role]
                ego = matches[0] if matches else None
            record = {"monotonicNs": time.monotonic_ns(), "frame": snapshot.frame, "elapsedS": snapshot.timestamp.elapsed_seconds,
                      "deltaS": snapshot.timestamp.delta_seconds, "ego": None}
            if ego is not None:
                state = snapshot.find(ego.id)
                if state is not None:
                    v, a = state.get_velocity(), state.get_acceleration()
                    tf = state.get_transform()
                    fwd = tf.get_forward_vector()
                    norm = math.sqrt(fwd.x ** 2 + fwd.y ** 2 + fwd.z ** 2) or 1.0
                    control = ego.get_control()
                    record["ego"] = {"id": ego.id, "location": _vec(tf.location), "velocity": _vec(v), "acceleration": _vec(a),
                                     "speedMps": round(math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2), 6),
                                     "accelForwardMps2": round((a.x * fwd.x + a.y * fwd.y + a.z * fwd.z) / norm, 6),
                                     "cachedControl": {"throttle": control.throttle, "brake": control.brake, "steer": control.steer}}
            out.write(json.dumps(record) + "\n")
        out.write(json.dumps({"footer": True, "frames": frames, "tickTimeouts": timeouts, "stoppedBy": stop[0] if stop else "duration",
                              "endedMonotonicNs": time.monotonic_ns()}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
