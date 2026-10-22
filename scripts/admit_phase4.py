#!/usr/bin/env python3
"""Build the Phase 4 admission record and re-pin the platform content lock (thesis V07).

Usage: admit_phase4.py --platform-root PATH --verification-log PATH --passed N --failed N
       [--command TEXT] [--output PATH]

Revisions are read from the platform checkout with read-only ``git rev-parse`` for the accepted
Phase 1–3 deliveries and the platform main named on the command line. Nothing is executed in the
platform or in any legacy repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xverse_compat.admission import PhaseRevisions, build_admission_record  # noqa: E402

PHASE_REFS = {"xdl_lite": "c1fd213cd", "argus_lite": "c2997c0f8", "maestro_lite": "63f5cb8c7"}


def _rev(platform_root: Path, ref: str) -> str:
    """Return the full commit id of ``ref`` in the platform checkout (read-only)."""

    return subprocess.check_output(["git", "-C", str(platform_root), "rev-parse", "--verify", ref + "^{commit}"], text=True).strip()


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, build the record and print its path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-root", required=True, type=Path)
    parser.add_argument("--platform-main", default="744b66f9c")
    parser.add_argument("--verification-log", required=True, type=Path)
    parser.add_argument("--passed", required=True, type=int)
    parser.add_argument("--failed", required=True, type=int)
    parser.add_argument("--command", default="PYTHONPATH=src python -m pytest tests -q -p no:cacheprovider")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "xdl" / "selection" / "aeb-sim-admission.json")
    parser.add_argument("--review-verdict", default=None, help="verdict of the separate read-only review, if done")
    parser.add_argument("--review-reference", default=None, help="where the review is recorded")
    parser.add_argument("--acceptance-decision", default=None, help="acceptance decision text, if taken")
    parser.add_argument("--acceptance-basis", default=None, help="who/what authorizes the acceptance")
    parser.add_argument("--acceptance-date", default=None, help="ISO date of the acceptance")
    arguments = parser.parse_args(argv)
    root = arguments.platform_root
    head = _rev(root, "HEAD")
    main_rev = _rev(root, arguments.platform_main)
    if head != main_rev:
        print(f"platform checkout HEAD {head} is not {arguments.platform_main}; refusing", file=sys.stderr)
        return 2
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--", "pyproject.toml", "src/xverse_xdl", "xdl/schemas", "xdl/profiles"], text=True)
    if dirty.strip():
        print("platform source surface has uncommitted changes; refusing", file=sys.stderr)
        return 3
    revisions = PhaseRevisions(
        xdl_lite=_rev(root, PHASE_REFS["xdl_lite"]),
        argus_lite=_rev(root, PHASE_REFS["argus_lite"]),
        maestro_lite=_rev(root, PHASE_REFS["maestro_lite"]),
        platform_main=main_rev,
    )
    build_admission_record(
        platform_root=root,
        revisions=revisions,
        verification_log=arguments.verification_log,
        verification_summary={"suite": "xverse-compat tests", "command": arguments.command,
                              "passed": arguments.passed, "failed": arguments.failed},
        output=arguments.output,
        review=None if arguments.review_verdict is None else {"verdict": arguments.review_verdict, "reference": arguments.review_reference},
        acceptance=None if arguments.acceptance_decision is None else {"decision": arguments.acceptance_decision, "basis": arguments.acceptance_basis, "date": arguments.acceptance_date},
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
