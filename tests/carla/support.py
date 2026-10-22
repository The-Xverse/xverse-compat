"""Shared paths for the Phase 4b tests. The pinned environment is required: tests fail, never skip,
when it is absent (thesis 028 design §9.9)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DESCRIPTORS = ROOT / "xdl" / "descriptors" / "aeb-sim" / "carla-sensors.json"
CARLA_ENV = Path(os.environ.get("XVERSE_COMPAT_CARLA_ENV",
                                "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310"))
PYTHON310 = CARLA_ENV / "bin" / "python"
ENV_RECORD = ROOT / "docs" / "engineering" / "thesis-lite-phase4b" / "env-record.json"


def require_env() -> Path:
    """Return the pinned interpreter or fail the test (never skip)."""

    assert PYTHON310.is_file(), f"pinned CARLA client environment missing: {CARLA_ENV}"
    return PYTHON310
