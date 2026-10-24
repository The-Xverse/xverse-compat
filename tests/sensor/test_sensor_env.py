"""Phase 8 WP-13 #4: the U2/U3 sensor numpy venv (review-wp13-sensor-venv).

The lock and script checks run everywhere, with the standard library only. The venv checks run when
``XVERSE_COMPAT_SENSOR_ENV`` names a built env (``<envdir>`` with ``venv/`` and ``identity.json``) and skip otherwise. The
variable has no default, because this increment's build is a verification build in ``/dev/shm``, not the loop10 cache.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools" / "sensor" / "u2u3-sensor.lock"
U4_LOCK = ROOT / "tools" / "inference" / "u4-inference.lock"
SCRIPT = ROOT / "tools" / "sensor" / "make-sensor-env.sh"
PY313 = Path("/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13")
ENV = Path(os.environ["XVERSE_COMPAT_SENSOR_ENV"]) if os.environ.get("XVERSE_COMPAT_SENSOR_ENV") else None
SITE = ENV / "venv" / "lib" / "python3.13" / "site-packages" if ENV else None
needs_env = pytest.mark.skipif(not (ENV and PY313.is_file() and (SITE / "numpy").is_dir() and (ENV / "identity.json").is_file()),
                               reason="XVERSE_COMPAT_SENSOR_ENV does not name a built sensor env")


def _requirements(path):
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def _tree(root):
    """The identity record's tree digest: sorted relative paths, a file's SHA-256 or a symlink's target."""

    digest, count = hashlib.sha256(), 0
    for base, dirs, files in os.walk(root):
        dirs.sort()
        links = [d for d in os.listdir(base) if os.path.islink(os.path.join(base, d)) and d not in files]
        for name in sorted(files + links):
            path = os.path.join(base, name)
            entry = "link:" + os.readlink(path) if os.path.islink(path) else hashlib.sha256(Path(path).read_bytes()).hexdigest()
            digest.update(f"{os.path.relpath(path, root)}\0{entry}\n".encode())
            count += 1
    return {"sha256": digest.hexdigest(), "entries": count}


def test_wp13_lock_is_the_u4_numpy_line_exactly():
    (line,) = _requirements(LOCK)
    assert line == next(r for r in _requirements(U4_LOCK) if r.startswith("numpy=="))
    assert line.split()[0] == "numpy==2.5.4" and len(line.split()[1]) == len("--hash=sha256:") + 64


def test_wp13_script_flags_and_refusals():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    text = SCRIPT.read_text()
    for flag in ("--no-index", "--require-hashes", "--no-deps", "--no-compile", "--without-pip", "-S -s -B",
                 "PYTHONDONTWRITEBYTECODE=1", "/proc/self/net/dev", "run inside unshare -rn", "env -i"):
        assert flag in text, flag
    # the bytecode check follows the last interpreter step on the venv (pip freeze), as WP-09 #3 / R-9
    assert text.index("freeze=$(") < text.index("bytecode=$(find")


def test_wp13_script_refuses_with_a_visible_network(tmp_path):
    interfaces = [line.split(":")[0].strip() for line in Path("/proc/self/net/dev").read_text().splitlines()[2:]]
    if all(name == "lo" for name in interfaces):
        pytest.skip("this test process already runs without non-loopback interfaces")
    result = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "env"), str(tmp_path), str(LOCK), str(tmp_path / "r.json")],
                            capture_output=True, text=True)
    assert result.returncode == 6 and "unshare -rn" in result.stderr and not (tmp_path / "env").exists()


@needs_env
def test_wp13_identity_record_matches_the_lock_and_the_venv_on_disk():
    record = json.loads((ENV / "identity.json").read_text())
    assert record["schema"] == "xverse-compat.sensor-env-record/1" and record["importReturnCode"] == 0
    assert record["lock"]["sha256"] == hashlib.sha256(LOCK.read_bytes()).hexdigest()
    assert record["lock"]["repositoryPath"] == "tools/sensor/u2u3-sensor.lock"
    assert record["installed"] == ["numpy==2.5.4"] and record["networkInterfaces"] == ["lo"]
    numpy_wheel = next(w for w in record["wheels"] if w["name"].startswith("numpy-2.5.4-"))
    assert numpy_wheel["sha256"] == _requirements(LOCK)[0].split("--hash=sha256:")[1]
    assert not [p for p in (ENV / "venv").rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
    assert _tree(SITE) == record["sitePackagesTree"] and _tree(ENV / "venv") == record["venvTree"]
    assert not (SITE / "onnxruntime").exists() and not (SITE / "pip").exists()
    interpreter = record["interpreter"]
    assert interpreter["sha256"] == hashlib.sha256(PY313.read_bytes()).hexdigest() and interpreter["version"] == "3.13.13"


@needs_env
def test_wp13_unit_pattern_import_uses_only_the_venv():
    probe = ("import sys, numpy; print(numpy.__version__); print(numpy.__file__); "
             "print(int('site' in sys.modules)); print(int(any('pyenv/versions/3.13.13/lib/python3.13/site-packages' in p for p in sys.path)))")
    env = {"PATH": "/usr/bin", "HOME": "/nonexistent-sensor-home", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
           "OPENBLAS_NUM_THREADS": "1", "PYTHONPATH": str(SITE)}
    out = subprocess.run([str(PY313), "-S", "-s", "-B", "-c", probe], env=env, capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == "2.5.4" and out[1].startswith(str(SITE)) and out[2:] == ["0", "0"]
    assert not [p for p in (ENV / "venv").rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
