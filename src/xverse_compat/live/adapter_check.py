"""Bounded live check of the CARLA adapter alone (Phase 7). NOT Lite integration: no Maestro, no XDL plan.

It verifies the ``carla-items/2`` adapter against a running CARLA 0.9.15 server: owned scenario spawn, the
single tick owner and actuator writer, a declared open-loop throttle/brake profile, measured motion and
deceleration (adapter motion items and an independent passive observer), graceful stop, and the restore
guard. Usage::

    python -m xverse_compat.live.adapter_check --run-dir DIR --carla-env ENV [--host H --port P]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from xverse_compat.carla_client import SocketAdapterLink
from xverse_compat.live.loop import LiteVehicleLoop, profile_source

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTORS = ROOT / "xdl/descriptors/aeb-sim/carla-sensors.json"
SCENARIO = ROOT / "xdl/descriptors/aeb-sim/live-scenario.json"
PROFILE = [{"untilS": 1.0, "throttle": 0.0, "brake": 0.0}, {"untilS": 7.0, "throttle": 0.6, "brake": 0.0},
           {"untilS": 12.0, "throttle": 0.0, "brake": 1.0}]


def adapter_argv(python: str, socket_path: str, carla_site: str, host: str, port: int) -> list[str]:
    return [python, "-s", "-B", "-m", "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + socket_path,
            "--source", f"live:{host}:{port}:scenario", "--scenario", str(SCENARIO), "--descriptors", str(DESCRIPTORS),
            "--carla-site", carla_site]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--carla-env", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    args = parser.parse_args(argv)
    run = Path(args.run_dir)
    run.mkdir(parents=True, exist_ok=True)
    (run / "carla-home").mkdir(exist_ok=True)
    site = str(Path(args.carla_env) / "lib/python3.10/site-packages")
    env = {"PATH": "/usr/bin", "HOME": str(run / "carla-home")}
    socket_path = f"/run/user/{os.getuid()}/xverse-lite/check-{os.getpid()}.sock"
    Path(socket_path).parent.mkdir(parents=True, exist_ok=True)
    src = ROOT / "src"
    summary = {"kind": "adapter-live-check", "notLiteIntegration": True, "profile": PROFILE, "startedWallNs": time.time_ns()}
    observer = subprocess.Popen(["/usr/bin/python3.10", "-s", "-B", "-m", "xverse_compat_carla.observe", "--host", args.host, "--port",
                                 str(args.port), "--role", "xverse-lite-ego", "--duration-s", "40", "--out", str(run / "observer.jsonl"),
                                 "--carla-site", site], cwd=src, env=env, stdout=subprocess.DEVNULL, stderr=open(run / "observer.err", "w"))
    link = SocketAdapterLink(socket_path, DESCRIPTORS)
    adapter = subprocess.Popen(adapter_argv("/usr/bin/python3.10", socket_path, site, args.host, args.port), cwd=src, env=env,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=open(run / "adapter.err", "w"))
    summary["adapterArgv"] = adapter.args
    code = 1
    try:
        summary["hello"] = link.start(accept_timeout_s=60)
        with open(run / "ticks.jsonl", "w", encoding="utf-8") as record:
            loop = LiteVehicleLoop(link, profile_source(PROFILE), record=record, max_ticks=int(12.0 / 0.05) + 5,
                                   wall_deadline=time.monotonic() + 60)
            result = loop.run()
        summary.update(ticks=result.ticks, endReason=result.end_reason, flowVerdicts=result.verdicts, receivers=result.receivers,
                       refusals=result.refusals)
        _, final = link.stop()
        summary["done"] = final.done
        code = 0
    except Exception as error:  # noqa: BLE001 - recorded, then cleanup
        summary["error"] = f"{type(error).__name__}: {error}"
        link.kill()
    finally:
        try:
            summary["adapterExit"] = adapter.wait(timeout=30)
        except subprocess.TimeoutExpired:
            adapter.kill()
            summary["adapterExit"] = "killed-after-timeout"
        observer.terminate()
        try:
            summary["observerExit"] = observer.wait(timeout=15)
        except subprocess.TimeoutExpired:
            observer.kill()
            summary["observerExit"] = "killed"
        guard = subprocess.run(["/usr/bin/python3.10", "-s", "-B", "-m", "xverse_compat_carla.restore", "--host", args.host, "--port",
                                str(args.port), "--carla-site", site], cwd=src, env=env, capture_output=True, text=True, timeout=60)
        summary["restoreGuard"] = {"exit": guard.returncode, "record": guard.stdout.strip()}
        summary["endedWallNs"] = time.time_ns()
        (run / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return code if summary.get("adapterExit") == 0 and summary["restoreGuard"]["exit"] == 0 else max(code, 1)


if __name__ == "__main__":
    sys.exit(main())
