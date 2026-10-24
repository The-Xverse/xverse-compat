"""Passive evaluation observer (Phase 7; v2 Phase 8 WP-01): records owned actors' motion from CARLA, never feeding runtime.

It never ticks, never applies control, never changes settings and never spawns or destroys an actor.
``world.wait_for_tick`` receives the frames produced by whichever client owns the tick (the legacy
asynchronous server loop in the baseline, the Lite adapter in a Lite run), so both runs are measured with
the same instrument. Output: a JSON Lines file whose first line is a header with ``evaluationOnly: true``.
``get_control()`` values are the client-side cached control and are labelled as such; braking is judged
from velocity and acceleration.

v1 (``--role``, Phase 7 schema, unchanged): the ego record of one role. v2 (``--track``, repeatable;
schema ``xverse-compat.evaluation-observer/2``, design record ``docs/engineering/phase8/review-wp01.md``
finding 1): evaluation-only ground truth for each declared ``xverse-lite-*`` role per simulation frame,
written to an exclusively created file; failures exit 3 (fail-closed). Neither mode is a runtime input
(DYN-002; FR-021): no module imports this one, and it writes no protocol message.

Usage: ``python -s -m xverse_compat_carla.observe (--role ROLE | --track ROLE [--track ROLE ...]) --duration-s S --out FILE
[--host H --port P --carla-site DIR]``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import site
import sys
import time

from .timeconv import seconds_to_ns

SCHEMA = "xverse-compat.evaluation-observer/2"
LABEL = "EVALUATION-ONLY GROUND TRUTH: never a runtime input (DYN-002; FR-021)"
TRACK_ROLE = re.compile(r"xverse-lite-[a-z0-9-]+\Z")  # owned roles only (scenario.ROLE_PREFIX, restore guard)
CLOCK = {"canonical": "simulation", "key": "frame", "simElapsedNs": "seconds_to_ns(snapshot.timestamp.elapsed_seconds)",
         "observerMonotonicNs": "observer receipt time; diagnosis only, never a join key"}
PASSIVE = {"ticks": False, "appliesSettings": False, "appliesControl": False, "spawnsOrDestroys": False}


def _vec(v) -> list:
    return [round(v.x, 6), round(v.y, 6), round(v.z, 6)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--role", help="v1: role_name of the ego vehicle (Phase 7 schema)")
    mode.add_argument("--track", action="append", metavar="ROLE", help="v2: an owned xverse-lite-* role to record (repeatable)")
    parser.add_argument("--duration-s", type=float, required=True, help="wall-clock observation bound")
    parser.add_argument("--out", required=True)
    parser.add_argument("--carla-site", default=None)
    args = parser.parse_args(argv)
    if args.track is not None:
        outside = [role for role in args.track if not TRACK_ROLE.match(role)]
        if outside:
            parser.error(f"--track roles must match xverse-lite-[a-z0-9-]+: {outside}")
        if len(set(args.track)) != len(args.track):
            parser.error("--track roles must be distinct")
    if args.carla_site:
        site.addsitedir(args.carla_site)
    os.environ.setdefault("HOME", "/nonexistent-carla-home")
    return _observe_v1(args) if args.role is not None else _observe_v2(args)


def _observe_v1(args) -> int:
    """Phase 7 schema for one role (unchanged)."""

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


def _line(out, obj) -> None:
    out.write(json.dumps(obj, allow_nan=False) + "\n")


def _role_of(actor):
    return getattr(actor, "attributes", {}).get("role_name")


def _entry(actor, snapshot) -> dict:
    """Return the v2 role entry of ``actor`` in ``snapshot``; nothing non-finite is ever written."""

    state = snapshot.find(actor.id)
    if state is None:
        return {"status": "not-in-snapshot", "id": actor.id}
    tf, v, a = state.get_transform(), state.get_velocity(), state.get_acceleration()
    fwd, rot = tf.get_forward_vector(), tf.rotation
    numbers = [tf.location.x, tf.location.y, tf.location.z, rot.pitch, rot.yaw, rot.roll, v.x, v.y, v.z, a.x, a.y, a.z, fwd.x, fwd.y, fwd.z]
    control = None
    if str(actor.type_id).startswith("vehicle."):
        cached = actor.get_control()
        control = {"throttle": cached.throttle, "brake": cached.brake, "steer": cached.steer}
        numbers += list(control.values())
    if not all(type(n) in (int, float) and math.isfinite(n) for n in numbers):
        return {"status": "non-finite", "id": actor.id}
    norm = math.sqrt(fwd.x ** 2 + fwd.y ** 2 + fwd.z ** 2) or 1.0
    entry = {"status": "observed", "id": actor.id, "typeId": actor.type_id, "location": _vec(tf.location),
             "rotationDeg": [round(rot.pitch, 6), round(rot.yaw, 6), round(rot.roll, 6)], "velocity": _vec(v), "acceleration": _vec(a),
             "speedMps": round(math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2), 6),
             "accelForwardMps2": round((a.x * fwd.x + a.y * fwd.y + a.z * fwd.z) / norm, 6)}
    if control is not None:
        entry["cachedControl"] = control
    return entry


def _observe_v2(args) -> int:
    """Evaluation-only ground truth for the declared roles (design record review-wp01 finding 1)."""

    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append("SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.append("SIGINT"))
    try:
        import carla  # noqa: PLC0415

        client = carla.Client(args.host, args.port)
        client.set_timeout(10.0)
        world = client.get_world()
        map_name = world.get_map().name
    except Exception as error:  # noqa: BLE001 - no output file exists yet
        print(f"observe: CARLA connection failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    try:
        out = open(args.out, "x", encoding="utf-8")  # exclusive: never an existing file, FIFO, socket or stream
    except OSError as error:
        print(f"observe: output path refused: {error}", file=sys.stderr)
        return 3
    roles = list(args.track)
    actors = dict.fromkeys(roles)
    observed = dict.fromkeys(roles, 0)
    frames = timeouts = 0
    error = None
    deadline = time.monotonic() + args.duration_s
    try:
        with out:
            _line(out, {"header": True, "schema": SCHEMA, "evaluationOnly": True, "groundTruth": True, "label": LABEL, "roles": roles,
                        "clock": CLOCK, "map": map_name, "passive": PASSIVE, "startedWallNs": time.time_ns(),
                        "startedMonotonicNs": time.monotonic_ns()})
            try:
                while time.monotonic() < deadline and not stop:
                    try:
                        snapshot = world.wait_for_tick(1.0)
                    except RuntimeError:
                        timeouts += 1  # no frame within 1 s (paused or stopped tick owner); keep waiting until the bound
                        continue
                    frames += 1
                    found = {}
                    unresolved = [role for role in roles if actors[role] is None or not actors[role].is_alive]
                    if unresolved:
                        listed = list(world.get_actors())
                        for role in unresolved:
                            found[role] = [actor for actor in listed if _role_of(actor) == role]
                            actors[role] = found[role][0] if len(found[role]) == 1 else None  # never guess between several
                    entries = {}
                    for role in roles:
                        if actors[role] is not None:
                            entries[role] = _entry(actors[role], snapshot)
                        elif len(found.get(role, ())) > 1:
                            entries[role] = {"status": "ambiguous", "ids": sorted(actor.id for actor in found[role])}
                        else:
                            entries[role] = {"status": "absent"}
                        observed[role] += entries[role]["status"] == "observed"
                    stamp = snapshot.timestamp
                    _line(out, {"frame": snapshot.frame, "simElapsedS": stamp.elapsed_seconds, "simElapsedNs": seconds_to_ns(stamp.elapsed_seconds),
                                "simDeltaS": stamp.delta_seconds, "observerMonotonicNs": time.monotonic_ns(), "roles": entries})
            except Exception as failure:  # noqa: BLE001 - recorded in the footer; the file is then incomplete
                error = f"{type(failure).__name__}: {failure}"
            _line(out, {"footer": True, "schema": SCHEMA, "frames": frames, "tickTimeouts": timeouts, "observedFrames": observed,
                        "stoppedBy": "error" if error else (stop[0] if stop else "duration"), "error": error,
                        "endedMonotonicNs": time.monotonic_ns()})
    except Exception as failure:  # noqa: BLE001 - a header, footer or close failure: no complete file
        error = error or f"{type(failure).__name__}: {failure}"
    if error:
        print(f"observe: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
