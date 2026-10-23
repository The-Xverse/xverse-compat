"""Restore guard (Phase 7, DLG-10): put a CARLA world back to asynchronous mode and remove owned actors.

Maestro stops units with SIGKILL, so an adapter that was killed cannot restore the world settings or
destroy the actors it spawned. The run command executes this guard after every run. It changes only
actors whose ``role_name`` begins with ``xverse-lite-`` and the synchronous-mode settings. It prints one
JSON line, ``{before, after, destroyed}``.

Order (review 1 R-7, DLG-11): hold every owned ego (throttle 0, brake 1, hand brake) while the world is still
paused; restore the pre-run settings recorded by the run command (``--settings-from``; asynchronous when
absent) and commit them with one tick; destroy owned actors; verify none remain.

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


def restore(world, carla=None, settings_to=None, client=None, registry=None) -> dict:
    """Restore world (duck-typed) and return the record.

    The settings are restored and committed first: in a synchronous world new settings take effect on the
    next tick and the actor list is stale until then (live findings 02 and 04). Owned actors are then
    destroyed and the world is listed again to verify that none remain.
    """

    before = _settings(world)
    held = []
    registered = list((registry or {}).get("actors", []))
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
    if before != target:
        settings = world.get_settings()
        settings.synchronous_mode = bool(target["synchronousMode"])
        settings.fixed_delta_seconds = target["fixedDeltaSeconds"]
        world.apply_settings(settings)
        if before["synchronousMode"]:
            try:
                world.tick(2.0)  # a synchronous world applies new settings on the next tick (live finding 02)
            except RuntimeError:
                pass
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
    matches = after["synchronousMode"] == bool(target["synchronousMode"])
    return {"before": before, "target": target, "after": after, "held": held, "destroyed": destroyed, "remaining": remaining,
            "restored": matches and not remaining}


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
