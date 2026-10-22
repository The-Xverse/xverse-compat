"""Entry point: ``python -s -m xverse_compat_carla.main --source fake:<fixture>|live:<host>:<port>:<ego>:<camera>:<radar>
--descriptors <carla-sensors.json> [--ground-truth PATH]``. Launch with ``env -i PATH=/usr/bin
HOME=/nonexistent-carla-home`` from ``<checkout>/src`` (no ``PYTHONPATH``)."""

from __future__ import annotations

import argparse
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
    descriptors = load_descriptors(args.descriptors)
    carla_version = None
    if args.source.startswith("fake:"):
        source = FakeSource(args.source[len("fake:"):])
    elif args.source.startswith("live:"):  # pragma: no cover - live execution is gated to Phase 7
        try:
            import carla  # noqa: PLC0415
            import importlib.metadata  # noqa: PLC0415

            host, port, ego, camera, radar = args.source[len("live:"):].split(":")
            client = carla.Client(host, int(port))
            source = LiveSource(client, int(ego), int(camera), int(radar), descriptors)
            carla_version = importlib.metadata.version("carla")
        except Exception as error:  # noqa: BLE001 - review L2: construction failure exits 3 before any protocol
            print(f"XVERSE-COMPAT-CARLA-SOURCE: {type(error).__name__}: {error}", file=sys.stderr)
            return 3
    else:
        parser.error("--source must be fake:<fixture> or live:<host>:<port>:<ego>:<camera>:<radar>")
    try:
        return run(source, descriptors, sys.stdin, sys.stdout, sys.stderr, carla_version=carla_version, ground_truth=args.ground_truth)
    finally:
        source.close()


if __name__ == "__main__":
    raise SystemExit(main())
