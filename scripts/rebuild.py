#!/usr/bin/env python3
"""Run one controlled rebuild and atomically write its public-safe result."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from xverse_compat.rebuild import (
    ControlledRebuilder,
    RebuildError,
    load_manifest,
    write_result_exclusive,
)


def _tool(value: str) -> tuple[str, Path]:
    """Parse one NAME=/absolute/path executable mapping."""
    name, separator, path = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("tool must use NAME=/absolute/path")
    return name, Path(path)


def _arguments() -> argparse.Namespace:
    """Parse explicit rebuild paths and allowlisted tools."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--tool", type=_tool, action="append", required=True)
    parser.add_argument("--result", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Execute the rebuild without ever invoking its resulting artifact."""
    arguments = _arguments()
    try:
        tools = dict(arguments.tool)
        if len(tools) != len(arguments.tool):
            raise RebuildError("build-command-denied")
        manifest = load_manifest(arguments.manifest)
        result = ControlledRebuilder(arguments.git, tools).rebuild(
            manifest, arguments.source, arguments.patch, arguments.work_root
        )
        write_result_exclusive(arguments.result, result)
    except RebuildError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
