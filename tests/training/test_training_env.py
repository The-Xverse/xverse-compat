"""Phase 8 WP-09 #3: the pinned offline training venv (review-wp09-training-venv finding 1).

The lock and the script are checked everywhere. The venv checks run as subprocesses of the real CPython 3.13.13 interpreter
with ``-S -s -B`` and PYTHONPATH to the venv, inside ``unshare -rn`` (no network), and skip cleanly when the training venv
(or, for the comparison, the U4 venv) is absent. The network, data and tolerance here are test-only.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from ..inference.test_inference_env import ENV as U4_ENV, LOCK as U4_LOCK, PY313, ROOT, _tree

CACHE = Path("/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache")
ENV = Path(os.environ.get("XVERSE_COMPAT_TRAINING_ENV", str(CACHE / "xverse-aeb-training-20261024")))
SITE = ENV / "venv" / "lib" / "python3.13" / "site-packages"
U4_SITE = U4_ENV / "venv" / "lib" / "python3.13" / "site-packages"
LOCK = ROOT / "tools" / "training" / "training.lock"
SCRIPT = ROOT / "tools" / "training" / "make-training-env.sh"
V1_OPERATORS = {"Conv", "Relu", "GlobalAveragePool", "Flatten", "Gemm"}
NETNS = shutil.which("unshare") is not None and subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode == 0
needs_venv = pytest.mark.skipif(not (PY313.is_file() and (SITE / "torch").is_dir() and (ENV / "identity.json").is_file()),
                                reason=f"training venv absent: {ENV}")
needs_both = pytest.mark.skipif(not ((SITE / "torch").is_dir() and (U4_SITE / "onnxruntime").is_dir()), reason="training or U4 venv absent")


def _lock(path):
    return {line.split()[0].split("==")[0]: (line.split()[0].split("==")[1], line.split()[1].removeprefix("--hash=sha256:"), line)
            for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")}


def _run(site, module, *args, tmp):
    env = {"PATH": "/usr/bin", "HOME": "/nonexistent-training-home", "TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1",
           "OMP_NUM_THREADS": "1", "ORT_DISABLE_TELEMETRY": "1", "PYTHONPATH": f"{site}:{ROOT}"}
    cmd = (["unshare", "-rn"] if NETNS else []) + [str(PY313), "-S", "-s", "-B", "-m", module, *map(str, args)]
    proc = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---- everywhere ----------------------------------------------------------------------------------------


def test_wp09_lock_pins_cpu_torch_onnx_and_the_u4_numpy_with_hashes():
    lock = _lock(LOCK)
    assert lock["torch"][0].endswith("+cpu") and "https://download.pytorch.org/whl/cpu" in lock["torch"][2]
    assert all("https://pypi.org/simple" in v[2] for k, v in lock.items() if k != "torch")
    assert lock["numpy"][:2] == _lock(U4_LOCK)["numpy"][:2] == ("2.5.4", _lock(U4_LOCK)["numpy"][1])  # bit-exact preprocessing
    assert {"onnx", "filelock", "typing_extensions", "setuptools", "sympy", "networkx", "jinja2", "fsspec"} <= set(lock)
    assert all(len(v[1]) == 64 for v in lock.values())


def test_wp09_build_script_flags():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    text = SCRIPT.read_text()
    for flag in ("--without-pip", "--no-index", "--require-hashes", "--no-deps", "--no-compile", "-S -s -B", "PYTHONDONTWRITEBYTECODE=1"):
        assert flag in text
    assert text.index("freeze --all") < text.index("refused: bytecode present")  # the check follows every interpreter run


# ---- in the training venv ------------------------------------------------------------------------------


@needs_venv
def test_wp09_identity_record_matches_the_lock_and_the_venv_on_disk():
    record = json.loads((ENV / "identity.json").read_text())
    assert record["schema"] == "xverse-compat.training-env-record/1" and record["importReturnCode"] == 0
    assert record["lock"]["repositoryPath"] == "tools/training/training.lock"
    assert record["lock"]["sha256"] == hashlib.sha256(LOCK.read_bytes()).hexdigest()
    assert {w["name"]: w["sha256"] for w in record["wheels"]} and \
        sorted(w["sha256"] for w in record["wheels"]) == sorted(v[1] for v in _lock(LOCK).values())
    assert not [p for p in (ENV / "venv").rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
    assert _tree(SITE) == record["sitePackagesTree"] and _tree(ENV / "venv") == record["venvTree"]
    assert "pip" not in {i.split("==")[0] for i in record["installed"]}


@needs_venv
def test_wp09_torch_is_the_cpu_build_and_uses_only_the_cpu(tmp_path):
    out = _run(SITE, "tests.training.train_probe", "cpu", tmp_path, tmp=tmp_path)
    assert out == {"version": "2.14.1+cpu", "cuda": None, "cudaAvailable": False, "threads": 1, "deterministic": True}


@needs_venv
def test_wp09_training_is_bit_reproducible_across_fresh_processes(tmp_path):
    first = _run(SITE, "tests.training.train_probe", "train", tmp_path, tmp=tmp_path)
    second = _run(SITE, "tests.training.train_probe", "train", tmp_path, tmp=tmp_path)
    assert first == second and len(first["weightsSha256"]) == 64


@needs_venv
def test_wp09_export_uses_only_v1_operators_at_opset_13(tmp_path):
    out = _run(SITE, "tests.training.train_probe", "export", tmp_path, tmp=tmp_path)
    assert set(out["operators"]) <= V1_OPERATORS and out["opset"] == [13]
    assert out["sha256"] == hashlib.sha256((tmp_path / "tiny.onnx").read_bytes()).hexdigest()


@needs_both
def test_wp09_the_export_runs_in_the_u4_onnx_runtime_and_matches_pytorch(tmp_path):
    exported = _run(SITE, "tests.training.train_probe", "export", tmp_path, tmp=tmp_path)
    out = _run(U4_SITE, "tests.training.ort_compare", tmp_path / "tiny.onnx", exported["sha256"], tmp_path / "io.json", tmp=tmp_path)
    assert out["providers"] == ["CPUExecutionProvider"]
    assert out["maxAbsDiff"] <= 1e-6  # a test-only bound; the observed value is recorded in finding 2 (an observation)
    assert not [p for p in U4_ENV.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]  # the U4 venv stays untouched
