"""Restore guard (Phase 7, DLG-10): put a CARLA world back to asynchronous mode and remove owned actors.

Maestro stops units with SIGKILL, so an adapter that was killed cannot restore the world settings or
destroy the actors it spawned. The run command executes this guard after every run. It changes only
actors whose ``role_name`` begins with ``xverse-lite-`` and the synchronous-mode settings. It prints one
JSON line, ``{before, after, destroyed}``.

Usage: ``python -s -m xverse_compat_carla.restore --host H --port P [--carla-site DIR]``.
"""

from __future__ import annotations

import argparse
import json
import os
import site
import sys

from .scenario import ROLE_PREFIX


def _settings(world) -> dict:
    s = world.get_settings()
    return {"synchronousMode": s.synchronous_mode, "fixedDeltaSeconds": s.fixed_delta_seconds}


def _owned(world) -> list:
    return [a for a in world.get_actors() if getattr(a, "attributes", {}).get("role_name", "").startswith(ROLE_PREFIX)]


def restore(world) -> dict:
    """Restore world (duck-typed) and return the record.

    The settings are restored and committed first: in a synchronous world new settings take effect on the
    next tick and the actor list is stale until then (live findings 02 and 04). Owned actors are then
    destroyed and the world is listed again to verify that none remain.
    """

    before = _settings(world)
    if before["synchronousMode"]:
        settings = world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        world.apply_settings(settings)
        try:
            world.tick(2.0)  # a synchronous world applies new settings on the next tick (live finding 02)
        except RuntimeError:
            pass
    destroyed = []
    for actor in _owned(world):
        destroyed.append({"id": actor.id, "typeId": actor.type_id, "roleName": actor.attributes.get("role_name")})
        actor.destroy()
    try:
        world.wait_for_tick(2.0)  # let the destruction reach the client's view of the episode
    except RuntimeError:
        pass
    after = _settings(world)
    remaining = [a.id for a in _owned(world)]
    return {"before": before, "after": after, "destroyed": destroyed, "remaining": remaining,
            "restored": after["synchronousMode"] is False and not remaining}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--carla-site", default=None)
    args = parser.parse_args(argv)
    if args.carla_site:
        site.addsitedir(args.carla_site)
    os.environ.setdefault("HOME", "/nonexistent-carla-home")
    try:
        import carla  # noqa: PLC0415

        client = carla.Client(args.host, args.port)
        client.set_timeout(10.0)
        record = restore(client.get_world())
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}), flush=True)
        return 3
    print(json.dumps(record, sort_keys=True), flush=True)
    return 0 if record["restored"] else 3


if __name__ == "__main__":
    sys.exit(main())
