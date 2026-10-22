"""Entry point: ``python -s -m xverse_compat_carla.main --source fake:<fixture>|live:<host>:<port>:<ego>:<camera>:<radar>
--descriptors <carla-sensors.json> [--ground-truth PATH]``. Launch with ``env -i PATH=/usr/bin
HOME=/nonexistent-carla-home`` from ``<checkout>/src`` (no ``PYTHONPATH``)."""

from __future__ import annotations

import argparse
import os
import sys

from .descriptors import load_descriptors
from .protocol import StrictLines, run
from .sources import FakeSource, LiveSource


def main(argv=None) -> int:
    """Parse arguments, build the source and serve the protocol."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--descriptors", required=True)
    parser.add_argument("--ground-truth", default=None)
    args = parser.parse_args(argv)
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
            import carla  # noqa: PLC0415
            import importlib.metadata  # noqa: PLC0415

            carla_version = importlib.metadata.version("carla")  # before binding (review 2 L-c)
            host, port, ego, camera, radar = args.source[len("live:"):].split(":")
            client = carla.Client(host, int(port))
            source = LiveSource(client, int(ego), int(camera), int(radar), descriptors)
    except Exception as error:  # noqa: BLE001
        print(f"XVERSE-COMPAT-CARLA-SOURCE: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    # strict decoding: under ``env -i`` the interpreter runs in UTF-8 mode with surrogateescape (review 2 L-a)
    stdin = StrictLines(sys.stdin.buffer)
    try:
        code = run(source, descriptors, stdin, sys.stdout, sys.stderr, carla_version=carla_version, ground_truth=args.ground_truth)
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
