"""V01/V01b: the pinned client environment record, the selection pin and 3.10 compilation."""

from __future__ import annotations

import json
import subprocess

from .support import ENV_RECORD, ROOT, require_env


def test_v01_env_record():
    record = json.loads(ENV_RECORD.read_text())
    assert record["importReturnCode"] == 0 and record["importOutput"][0] == "0.9.15"
    assert record["wheelSha256"] == "61449e33260f6a0cfd2f88d56f2463a5797a0b51bc46618beec07365422d4ad6"
    assert [line.split("@")[0].split("==")[0].strip() for line in record["pipFreeze"]] == ["carla", "pip", "setuptools"]


def test_v01_live_import_in_the_pinned_environment():
    python = require_env()
    out = subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", str(python), "-s", "-c",
                          "import carla, importlib.metadata as m; print(m.version('carla'))"], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and out.stdout.strip() == "0.9.15"


def test_v01b_package_compiles_and_imports_under_310_without_forbidden_modules():
    python = require_env()
    # compiled in memory: compileall would write bytecode despite -B (review 2 L-g)
    script = ("import sys, pathlib; ok = all(compile(f.read_text(encoding='utf-8'), str(f), 'exec') is not None "
              "for f in sorted(pathlib.Path('xverse_compat_carla').glob('*.py'))); "
              "import xverse_compat_carla.main, xverse_compat_carla.protocol as p; "
              "print(ok, sys.version_info[:2], p.forbidden_modules_loaded())")
    out = subprocess.run(["env", "-i", "PATH=/usr/bin", "HOME=/nonexistent-carla-home", "PYTHONDONTWRITEBYTECODE=1", str(python), "-s", "-B", "-c", script],
                         cwd=ROOT / "src", capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "True (3, 10) []"
