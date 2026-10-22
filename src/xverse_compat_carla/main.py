"""Entry point: ``python -s -m xverse_compat_carla.main --source fake:<fixture>|live:<host>:<port>:<ego>:<camera>:<radar>
--descriptors <carla-sensors.json> [--ground-truth PATH]``. Launch with ``env -i PATH=/usr/bin
HOME=/nonexistent-carla-home`` from ``<checkout>/src`` (no ``PYTHONPATH``).

Phase 7 successor (carla-items/2): ``--protocol 2 --connect unix:<path>`` serves the protocol over a Unix
socket (Maestro units have ``/dev/null`` standard streams); ``--source live:<host>:<port>:scenario
--scenario <file>`` spawns and owns the declared ego vehicle and sensors; ``--carla-site <dir>`` adds the
pinned environment's site-packages when the unit is launched through the plain interpreter
(``/usr/bin/python3.10``; a symlinked venv interpreter cannot be sealed by Maestro)."""

from __future__ import annotations

import argparse
import json
import os
import site
import socket
import sys
import time

from .descriptors import load_descriptors
from .protocol import StrictLines, run
from .sources import FakeSource, LiveSource


def main(argv=None) -> int:
    """Parse arguments, serve the protocol, then optionally write a marker and linger (Maestro units)."""

    args_list = sys.argv[1:] if argv is None else list(argv)
    if "--stderr" in args_list:  # Maestro units have /dev/null streams
        index = args_list.index("--stderr")
        fd = os.open(args_list[index + 1], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(fd, 2)
        os.close(fd)
        del args_list[index:index + 2]
    code = _main(args_list)
    linger = "--linger" in args_list and code == 0  # a failed adapter exits, so Maestro's probe sees it
    if "--marker" in args_list:
        marker = args_list[args_list.index("--marker") + 1]
        with open(marker, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"unit": "carla-adapter", "code": code}) + "\n")
    if linger:
        import signal  # noqa: PLC0415

        stopped = []
        signal.signal(signal.SIGTERM, lambda *_: stopped.append(True))
        while not stopped:
            time.sleep(0.2)
    return code


def _main(argv) -> int:
    """Parse arguments, build the source and serve the protocol."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--descriptors", required=True)
    parser.add_argument("--ground-truth", default=None)
    parser.add_argument("--protocol", type=int, choices=(1, 2), default=1)
    parser.add_argument("--connect", default=None, help="unix:<path> (protocol 2 only)")
    parser.add_argument("--connect-timeout-s", type=float, default=10.0)
    parser.add_argument("--scenario", default=None, help="owned live scenario JSON (protocol 2 only)")
    parser.add_argument("--carla-site", default=None, help="site-packages of the pinned carla environment")
    parser.add_argument("--linger", action="store_true", help="after the protocol ends, stay alive until stopped (Maestro unit)")
    parser.add_argument("--marker", default=None, help="write this collection marker when the protocol ends")
    args = parser.parse_args(argv)
    if (args.connect is not None or args.scenario is not None) and args.protocol != 2:
        parser.error("--connect and --scenario require --protocol 2")
    if args.connect is not None and not args.connect.startswith("unix:"):
        parser.error("--connect must be unix:<path>")
    if not args.source.startswith(("fake:", "live:")):
        parser.error("--source must be fake:<fixture> or live:<host>:<port>:<ego>:<camera>:<radar>")
    carla_version = None
    try:  # every construction failure exits 3 with one stderr line before any protocol (review L2, review 2 L-b)
        descriptors = load_descriptors(args.descriptors)
        if args.source.startswith("fake:"):
            source = FakeSource(args.source[len("fake:"):])
        else:  # pragma: no cover - live execution is gated to Phase 7
            if args.ground_truth is not None:  # review 2 N2: live actors are not collected, an export would fail open
                raise ValueError("--ground-truth is fake-source only in Phase 4b (live actor collection is not implemented)")
            if args.carla_site is not None:
                site.addsitedir(args.carla_site)
            os.environ.setdefault("HOME", "/nonexistent-carla-home")  # the carla import aborts without HOME
            import carla  # noqa: PLC0415
            import importlib.metadata  # noqa: PLC0415

            carla_version = importlib.metadata.version("carla")  # before binding (review 2 L-c)
            fields = args.source[len("live:"):].split(":")
            if fields[2:] == ["scenario"]:
                if args.scenario is None:
                    raise ValueError("live:<host>:<port>:scenario requires --scenario")
                client = carla.Client(fields[0], int(fields[1]))
                client.set_timeout(10.0)
                scenario = json.loads(open(args.scenario, encoding="utf-8").read())
                source = LiveSource(client, -1, -1, -1, descriptors, scenario=scenario)
            else:
                host, port, ego, camera, radar = fields
                client = carla.Client(host, int(port))
                client.set_timeout(10.0)
                source = LiveSource(client, int(ego), int(camera), int(radar), descriptors)
    except Exception as error:  # noqa: BLE001
        print(f"XVERSE-COMPAT-CARLA-SOURCE: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    stdout = sys.stdout
    if args.connect is not None:
        try:
            link = _connect(args.connect[len("unix:"):], args.connect_timeout_s)
        except OSError as error:
            _close(source, quiet=True)
            print(f"XVERSE-COMPAT-CARLA-SOURCE: connect failed: {type(error).__name__}: {error}", file=sys.stderr)
            return 3
        stdin, stdout = StrictLines(link.makefile("rb")), link.makefile("w", encoding="utf-8", newline="\n")
    else:
        # strict decoding: under ``env -i`` the interpreter runs in UTF-8 mode with surrogateescape (review 2 L-a)
        stdin = StrictLines(sys.stdin.buffer)
    try:
        code = run(source, descriptors, stdin, stdout, sys.stderr, carla_version=carla_version, ground_truth=args.ground_truth,
                   protocol=args.protocol)
    except Exception as error:  # noqa: BLE001 - e.g. a broken stdout: one stderr line, exit 3 (review 5 N1)
        _close(source, quiet=True)
        print(f"XVERSE-COMPAT-CARLA-SOURCE: {type(error).__name__}: {error}", file=sys.stderr)
        _discard_stdout()
        return 3
    except BaseException:
        _close(source, quiet=True)
        raise
    closed = _close(source, quiet=code == 2)  # always closed; exit 2 keeps its single stderr line (review 5 L1)
    return code or closed


def _connect(path: str, timeout_s: float) -> socket.socket:
    """Connect to the platform's Unix socket, retrying until ``timeout_s`` (monotonic) has elapsed."""

    deadline = time.monotonic() + timeout_s
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(path)
            return sock
        except OSError:
            sock.close()
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def _discard_stdout() -> None:
    """Point stdout at the null device so the interpreter's final flush of a broken pipe cannot fail again
    (that would exit 120 with further stderr lines; review 6 M1)."""

    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        os.close(devnull)
    except (OSError, ValueError, AttributeError):  # stdout without a descriptor (e.g. under a test harness)
        pass


def _close(source, quiet: bool = False) -> int:
    """Close the source; a failure is one stderr line (unless ``quiet``) and exit 3 (review 4 L3)."""

    try:
        source.close()
    except Exception as error:  # noqa: BLE001
        if not quiet:
            print(f"XVERSE-COMPAT-CARLA-SOURCE: close failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
