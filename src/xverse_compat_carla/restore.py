"""Restore guard (Phase 7, DLG-10/11/11a): restore a CARLA world's settings and remove owned actors.

Maestro stops units with SIGKILL, so an adapter that was killed cannot restore the world settings or
destroy the actors it spawned. The run command executes this guard after every run. It changes only
actors whose ``role_name`` begins with ``xverse-lite-`` (listed, or read from the adapter's owned-actor
registry) and the world's synchronous-mode settings. It prints one JSON line:
``{before, target, after, applyAttempts, held, standstill, unpauseMonotonicNs, destroyMonotonicNs, destroyed,
remaining, restored, wallNs, monotonicNs}``.

Order (review 1 R-7, DLG-11, findings 06 and 21): hold every owned ego (throttle 0, brake 1, hand brake) by id
while the world is still paused; restore the pre-run settings recorded by the run command
(``--settings-from``; asynchronous when absent, or when the recorded synchronous state had no tick owner,
DLG-11a), retrying apply-and-commit-tick up to 3 times until mode and step match; with an asynchronous target,
keep holding every held ego until it is at standstill (< 0.05 m/s) or a 5 s timeout, recorded as a failure (S1
FR-022); destroy owned actors; verify none remain. The un-pause time is the first apply-and-commit.

Usage: ``python -s -m xverse_compat_carla.restore --host H --port P [--carla-site DIR] [--settings-from JSON]``.
"""

from __future__ import annotations

import argparse
import json
import os
import site
import sys
import time

from .scenario import ROLE_PREFIX


def _settings(world) -> dict:
    s = world.get_settings()
    return {"synchronousMode": s.synchronous_mode, "fixedDeltaSeconds": s.fixed_delta_seconds}


def _owned(world) -> list:
    return [a for a in world.get_actors() if getattr(a, "attributes", {}).get("role_name", "").startswith(ROLE_PREFIX)]


STANDSTILL_MPS = 0.05
STANDSTILL_TIMEOUT_S = 5.0


def _speed(actor):
    velocity = actor.get_velocity()
    return (velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2) ** 0.5


def _hold_to_standstill(world, held, timeout_s=STANDSTILL_TIMEOUT_S) -> dict:
    """Wait, holding brake, until every held ego still in the world is at standstill (S1 FR-022)."""

    vehicles, pending = [], []
    for actor_id in held:
        if world.get_actor(actor_id) is None:  # already destroyed (for example by the adapter's own close)
            vehicles.append({"id": actor_id, "absent": True, "speedMps": None, "monotonicNs": time.monotonic_ns()})
        else:
            pending.append(actor_id)
    end = time.monotonic() + timeout_s
    while pending:
        for actor_id in list(pending):
            actor = world.get_actor(actor_id)
            speed = None if actor is None else _speed(actor)
            if actor is None or speed < STANDSTILL_MPS:
                vehicles.append({"id": actor_id, "absent": actor is None, "speedMps": speed, "monotonicNs": time.monotonic_ns()})
                pending.remove(actor_id)
        if not pending or time.monotonic() >= end:
            break
        try:
            world.wait_for_tick(1.0)
        except RuntimeError:
            time.sleep(0.05)
    timed_out = []
    for actor_id in pending:
        actor = world.get_actor(actor_id)
        timed_out.append({"id": actor_id, "speedMps": None if actor is None else _speed(actor)})
    return {"ok": not timed_out, "thresholdMps": STANDSTILL_MPS, "timeoutS": timeout_s, "vehicles": vehicles, "timedOut": timed_out}


def _same_delta(a, b) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-6)


def restore(world, carla=None, settings_to=None, client=None, registry=None) -> dict:
    """Restore world (duck-typed) and return the record.

    The settings are restored and committed first: in a synchronous world new settings take effect on the
    next tick and the actor list is stale until then (live findings 02 and 04). Owned actors are then
    destroyed and the world is listed again to verify that none remain.
    """

    before = _settings(world)
    held = []
    registered = [a for a in (registry or {}).get("actors", []) if str(a.get("roleName", "")).startswith(ROLE_PREFIX)]  # N-8
    if carla is not None and client is not None and registered:  # by id, server-side: no stale client list (finding 06)
        hold = carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0, hand_brake=True)
        vehicles = [a["id"] for a in registered if str(a.get("typeId", "")).startswith("vehicle.")]
        responses = client.apply_batch_sync([carla.command.ApplyVehicleControl(i, hold) for i in vehicles], False)
        held += [i for i, r in zip(vehicles, responses) if not r.has_error()]
    if carla is not None:
        for actor in _owned(world):  # hold before un-pausing: a killed adapter leaves its last throttle applied
            if str(getattr(actor, "type_id", "")).startswith("vehicle.") and actor.id not in held:
                actor.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0, hand_brake=True))
                held.append(actor.id)
    target = settings_to or {"synchronousMode": False, "fixedDeltaSeconds": None}
    attempts = 0
    hold_ns = time.monotonic_ns()  # the brake hold is applied (S1 FR-022)
    unpause_ns = None
    unpause_reason = "world already in the target mode: it was not paused by this guard"
    if before != {k: target[k] for k in ("synchronousMode", "fixedDeltaSeconds")}:
        # bounded retry: right after a server start a commit tick can time out and leave the settings (review log 21)
        for attempts in range(1, 4):
            settings = world.get_settings()
            synchronous_now = settings.synchronous_mode  # the mode this attempt is applied in (S1c finding 2)
            settings.synchronous_mode = bool(target["synchronousMode"])
            settings.fixed_delta_seconds = target["fixedDeltaSeconds"]
            world.apply_settings(settings)
            if synchronous_now:
                try:
                    world.tick(5.0)  # a synchronous world applies new settings on the next tick (live finding 02)
                except RuntimeError:
                    pass
            if unpause_ns is None:
                unpause_ns, unpause_reason = time.monotonic_ns(), None  # after the first apply-and-commit (S1 FR-022)
            now = _settings(world)
            if now["synchronousMode"] == bool(target["synchronousMode"]) and _same_delta(now["fixedDeltaSeconds"], target["fixedDeltaSeconds"]):
                break  # mode and step both match (review 3 M-2)
    standstill = {"ok": True, "applicable": False, "vehicles": [], "timedOut": []}
    if held and not target["synchronousMode"]:  # an asynchronous world advances: hold until standstill (S1 FR-022)
        try:
            standstill = dict(_hold_to_standstill(world, held), applicable=True)
        except Exception as error:  # noqa: BLE001 - never skip the destroy below (S1c review 1 R1-1)
            standstill = {"ok": False, "applicable": True, "vehicles": [], "timedOut": list(held),
                          "error": f"{type(error).__name__}: {error}"}
    elif held:
        standstill["reason"] = ("synchronous restore target: after the restore this guard does not tick, "
                                "so standstill is not awaited")
    destroy_ns = time.monotonic_ns()
    destroyed = []
    if carla is not None and client is not None and registered:
        for entry, response in zip(registered, client.apply_batch_sync([carla.command.DestroyActor(a["id"]) for a in registered], False)):
            if not response.has_error():
                destroyed.append({"id": entry["id"], "typeId": entry.get("typeId"), "roleName": entry.get("roleName"), "via": "registry"})
    gone = {d["id"] for d in destroyed}
    for actor in [x for x in _owned(world) if x.id not in gone]:
        destroyed.append({"id": actor.id, "typeId": actor.type_id, "roleName": actor.attributes.get("role_name")})
        actor.destroy()
    try:
        world.wait_for_tick(2.0)  # let the destruction reach the client's view of the episode
    except RuntimeError:
        pass
    after = _settings(world)
    remaining = [a.id for a in _owned(world)]
    delta_ok = target["fixedDeltaSeconds"] is None and after["fixedDeltaSeconds"] is None or (
        target["fixedDeltaSeconds"] is not None and after["fixedDeltaSeconds"] is not None
        and abs(after["fixedDeltaSeconds"] - target["fixedDeltaSeconds"]) < 1e-6)
    matches = after["synchronousMode"] == bool(target["synchronousMode"]) and delta_ok  # review 2 N-8: the step too
    return {"before": before, "target": target, "after": after, "applyAttempts": attempts, "held": held, "standstill": standstill,
            "holdMonotonicNs": hold_ns, "unpauseMonotonicNs": unpause_ns, "unpauseReason": unpause_reason,
            "destroyMonotonicNs": destroy_ns, "destroyed": destroyed, "remaining": remaining,
            "restored": matches and not remaining and standstill["ok"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--carla-site", default=None)
    parser.add_argument("--settings-from", default=None, help="JSON with synchronousMode/fixedDeltaSeconds recorded before the run")
    parser.add_argument("--owned-registry", default=None, help="owned-actor registry written by the adapter")
    args = parser.parse_args(argv)
    target = None
    if args.settings_from:
        recorded = json.loads(open(args.settings_from, encoding="utf-8").read())
        target = {"synchronousMode": recorded["synchronousMode"], "fixedDeltaSeconds": recorded["fixedDeltaSeconds"]}
        if target["synchronousMode"] and not recorded.get("frameAdvancing", True):
            # DLG-11a: a synchronous world that no client was ticking is not a usable original state (it would
            # block the asynchronous legacy loop); restore asynchronous and say why
            target = {"synchronousMode": False, "fixedDeltaSeconds": None, "reason": "recorded synchronous state had no tick owner"}
    if args.carla_site:
        site.addsitedir(args.carla_site)
    os.environ.setdefault("HOME", "/nonexistent-carla-home")
    try:
        import carla  # noqa: PLC0415

        client = carla.Client(args.host, args.port)
        client.set_timeout(10.0)
        registry = None
        if args.owned_registry and os.path.exists(args.owned_registry):
            registry = json.loads(open(args.owned_registry, encoding="utf-8").read())
        record = restore(client.get_world(), carla, target, client, registry)
        record.update(wallNs=time.time_ns(), monotonicNs=time.monotonic_ns())
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}), flush=True)
        return 3
    print(json.dumps(record, sort_keys=True), flush=True)
    return 0 if record["restored"] else 3


if __name__ == "__main__":
    sys.exit(main())
