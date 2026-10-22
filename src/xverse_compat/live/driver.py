"""Lite driver unit (Phase 7): the platform side of ``carla-items/2`` and the gateway to the legacy VCU.

Launched by Maestro as an owned unit, before the adapter unit, so that it listens first. Per tick it:
1. reads the latest legacy VCU commands (``vcu/control/throttle_cmd``, ``vcu/control/brake_cmd``) received
   over zenoh;
2. treats a command older than ``--vcu-stale-ms`` (host-monotonic) as stale: throttle 0, last brake held;
3. sends one throttle/brake command, requests one tick, and routes the motion and radar items through the
   Phase 6 flow receivers (``carla-simulation`` domain; verdicts recorded through ``FlowEvidence`` in an
   Argus run when ``--plan`` is given);
4. publishes ``vehicle/status/velocity_status`` (km/h from the runtime motion item) and
   ``vehicle/status/clock_status`` (simulation elapsed seconds), as the legacy virtual vehicle at
   ``b10e6d8`` does.

After the bounded episode it stops the adapter gracefully (the adapter restores the world), writes its
summary and a collection marker, and lingers until Maestro stops it. Runtime decisions use only runtime
data; no ground truth is read. No brake-status or wheel-speed signal is produced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import time

from xverse_compat.carla_client import SocketAdapterLink
from xverse_compat.live.loop import DOMAIN, LiteVehicleLoop
from xverse_compat.live.zenoh_io import Latest, open_session, redirect_stderr

VCU = {"throttle": "vcu/control/throttle_cmd", "brake": "vcu/control/brake_cmd"}
STATUS = {"speed": "vehicle/status/velocity_status", "clock": "vehicle/status/clock_status"}


class VcuCommands:
    """Command source mapping legacy VCU outputs to adapter commands, with a host-monotonic staleness bound."""

    def __init__(self, session, stale_ms: int) -> None:
        self.throttle, self.brake = Latest(session, VCU["throttle"], 0.0), Latest(session, VCU["brake"], 0.0)
        self.stale_ns = stale_ms * 1_000_000
        self.held_brake = 0.0
        self.stale_ticks = 0

    def __call__(self, sim_s, last_motion):
        now = time.monotonic_ns()
        throttle, t_ns, t_count = self.throttle.read()
        brake, b_ns, b_count = self.brake.read()
        stale = t_ns is None or b_ns is None or now - t_ns > self.stale_ns or now - b_ns > self.stale_ns
        meta = {"vcuThrottle": throttle, "vcuBrake": brake, "throttleAgeMs": None if t_ns is None else round((now - t_ns) / 1e6, 1),
                "brakeAgeMs": None if b_ns is None else round((now - b_ns) / 1e6, 1), "vcuSamples": [t_count, b_count], "stale": stale}
        if stale:
            self.stale_ticks += 1
            return 0.0, self.held_brake, meta  # declared rule: drop throttle, hold the last fresh brake
        self.held_brake = min(max(brake, 0.0), 1.0)
        meta["throttleClamped"] = throttle < 0.0 or throttle > 1.0  # the VCU range is [-1, 1]; reverse is not carried
        return min(max(throttle, 0.0), 1.0), self.held_brake, meta


def _argus(run_dir: Path, plan_path: str | None, run_id: str):
    if plan_path is None:
        return None, None
    from xverse.argus import EvidenceStore  # noqa: PLC0415
    from xverse.flows.evidence import FlowEvidence  # noqa: PLC0415

    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    run = EvidenceStore.open_run(run_dir / "argus-flows", run_id=run_id, plan=plan)
    clocks = lambda tick: {"simulation": {"domain": DOMAIN, "unit": "tick", "value": tick or 0}}  # noqa: E731
    return run, FlowEvidence(run, run_id, clocks)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--descriptors", required=True)
    parser.add_argument("--router", default="tcp/127.0.0.1:7447")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-id", default="lite-live")
    parser.add_argument("--plan", default=None, help="compiled experiment plan JSON (opens the Argus flow-evidence run)")
    parser.add_argument("--episode-s", type=float, default=15.0)
    parser.add_argument("--tick-period-s", type=float, default=0.05)
    parser.add_argument("--vcu-stale-ms", type=int, default=250)
    parser.add_argument("--accept-timeout-s", type=float, default=60.0)
    parser.add_argument("--wall-bound-s", type=float, default=90.0)
    parser.add_argument("--marker", default=None)
    parser.add_argument("--linger", action="store_true", help="after a successful episode, stay alive until stopped")
    parser.add_argument("--pause-after-s", type=float, default=None,
                        help="failure-path case: stop ticking after this many host seconds and hold the world paused")
    argv = list(sys.argv[1:] if argv is None else argv)
    redirect_stderr(argv)
    args = parser.parse_args(argv)
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append("SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.append("SIGINT"))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    summary = {"unit": "lite-driver", "startedWallNs": time.time_ns(), "args": vars(args), "domains": {"items": DOMAIN, "pacing": "host-monotonic"}}
    code = 3
    link = SocketAdapterLink(args.socket, args.descriptors)
    session = open_session(args.router)
    speed_pub, clock_pub = session.declare_publisher(STATUS["speed"]), session.declare_publisher(STATUS["clock"])
    commands = VcuCommands(session, args.vcu_stale_ms)
    argus, evidence = None, None
    try:
        argus, evidence = _argus(run_dir, args.plan, args.run_id)

        def on_motion(motion, sim_s):
            speed_pub.put(str(motion["value"]["speedMps"] * 3.6))
            clock_pub.put(str(motion["originNs"] / 1e9))

        summary["hello"] = link.start(accept_timeout_s=args.accept_timeout_s)
        if args.pause_after_s is not None:  # the simulation clock stops: no further tick is requested
            pause_at = time.monotonic() + args.pause_after_s
            cancelled = lambda: bool(stop) or time.monotonic() >= pause_at  # noqa: E731
        else:
            cancelled = lambda: bool(stop)  # noqa: E731
        with open(run_dir / "driver-ticks.jsonl", "w", encoding="utf-8") as record:
            loop = LiteVehicleLoop(link, commands, record=record, on_motion=on_motion, tick_period_s=args.tick_period_s,
                                   max_ticks=int(args.episode_s / args.tick_period_s), wall_deadline=started + args.wall_bound_s,
                                   cancelled=cancelled, listener=evidence)
            result = loop.run()
        if args.pause_after_s is not None and not stop:
            summary.update(ticks=result.ticks, endReason="paused", pausedMonotonicNs=time.monotonic_ns())
            (run_dir / "driver-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
            while not stop:  # hold the world paused (synchronous, no tick) until Maestro stops the unit
                time.sleep(0.2)
        summary.update(ticks=result.ticks, endReason=result.end_reason, flowVerdicts=result.verdicts, receivers=result.receivers,
                       refusals=result.refusals, vcuStaleTicks=commands.stale_ticks)
        if result.done is None:
            _, final = link.stop()
            summary["done"] = final.done
        else:
            summary["done"] = result.done
        code = 0 if summary["done"] and summary["done"].get("forbiddenModulesLoaded") == [] else 3
    except Exception as error:  # noqa: BLE001 - recorded; the adapter sees end-of-file and restores the world
        summary["error"] = f"{type(error).__name__}: {error}"
        link.kill()
    finally:
        if argus is not None:
            try:
                summary["argus"] = str(argus.finalize())[:400]
            except Exception as error:  # noqa: BLE001
                summary["argusError"] = f"{type(error).__name__}: {error}"
        summary["endedWallNs"] = time.time_ns()
        (run_dir / "driver-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n")
        if args.marker:
            Path(args.marker).write_text(json.dumps({"unit": "lite-driver", "code": code}) + "\n")
    while args.linger and code == 0 and not stop:
        time.sleep(0.2)
    session.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
