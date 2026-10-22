"""Entry point: ``python -s -m xverse_compat_carla.main --source fake:<fixture>|live:<host>:<port>:<ego>:<camera>:<radar>
--descriptors <carla-sensors.json> [--ground-truth PATH]``. Launch with ``env -i PATH=/usr/bin
HOME=/nonexistent-carla-home`` from ``<checkout>/src`` (no ``PYTHONPATH``)."""

from __future__ import annotations

import argparse
import io
import sys

from .descriptors import load_descriptors
from .protocol import run
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
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="strict", newline="\n")
    try:
        return run(source, descriptors, stdin, sys.stdout, sys.stderr, carla_version=carla_version, ground_truth=args.ground_truth)
    finally:
        source.close()


if __name__ == "__main__":
    raise SystemExit(main())
