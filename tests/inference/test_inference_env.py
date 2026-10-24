"""Phase 8 WP-08: the U4 inference venv, the digest-first loader and checks V-1, V-4 and V-6 (review-wp08).

The loader refusals, the lock and the test-model writer run everywhere (standard library only). V-1, V-4 and the
venv side of V-6 run as subprocesses of the real CPython 3.13.13 interpreter with PYTHONPATH to the inference venv
(the U4 pattern, K-11), and skip cleanly when the venv is absent.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from xverse_compat.inference import loader
from xverse_compat.inference.loader import ModelRefused, verified_bytes

from . import minimal_onnx

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tiny-cnn.onnx"
FIXTURE_DIGEST = "sha256:29f7e86bd6ab25f3dcf6abc7dd9785025101d44c9aba32620b63112458a89d64"
LOCK = ROOT / "tools" / "inference" / "u4-inference.lock"
SCRIPT = ROOT / "tools" / "inference" / "make-inference-env.sh"
PY313 = Path("/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13")
ENV = Path(os.environ.get("XVERSE_COMPAT_INFERENCE_ENV",
                          "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-aeb-inference-20261024"))
SITE = ENV / "venv" / "lib" / "python3.13" / "site-packages"
needs_env = pytest.mark.skipif(not (PY313.is_file() and (SITE / "onnxruntime").is_dir() and (ENV / "identity.json").is_file()),
                               reason=f"U4 inference venv absent: {ENV}")


def _u4(*args, telemetry_off=True, timeout=120):
    """Run ``tests.inference.probe`` in the U4 pattern: env -i, the real interpreter, PYTHONPATH to the venv."""

    env = {"PATH": "/usr/bin", "HOME": "/nonexistent-inference-home", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
           "PYTHONPATH": f"{SITE}:{ROOT / 'src'}:{ROOT}"}
    if telemetry_off:
        env["ORT_DISABLE_TELEMETRY"] = "1"
    proc = subprocess.run([str(PY313), "-s", "-B", "-m", "tests.inference.probe", *map(str, args)], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1]), proc.stderr


# ---- everywhere (standard library) -------------------------------------------------------------------


def test_wp08_test_model_bytes_are_deterministic_and_equal_the_checked_in_fixture():
    assert minimal_onnx.model_bytes() == minimal_onnx.model_bytes() == FIXTURE.read_bytes()
    assert "sha256:" + hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_DIGEST


@pytest.mark.parametrize("digest", ["", "29f7e86b", "sha256:" + "0" * 63, "sha256:" + "A" * 64, "md5:" + "0" * 32, None, 7])
def test_wp08_ill_formed_declared_digests_are_refused(digest):
    with pytest.raises(ModelRefused, match="declared digest"):
        verified_bytes(FIXTURE, digest)


def test_wp08_v6_a_mismatching_or_unreadable_model_is_refused_before_onnxruntime_is_imported(tmp_path, monkeypatch):
    tampered = tmp_path / "tampered.onnx"
    tampered.write_bytes(FIXTURE.read_bytes()[:-1] + b"\x00")
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "1")
    for path in (tampered, tmp_path / "missing.onnx"):
        with pytest.raises(ModelRefused):
            loader.load_model(path, FIXTURE_DIGEST)
    assert "onnxruntime" not in sys.modules
    assert verified_bytes(FIXTURE, FIXTURE_DIGEST) == FIXTURE.read_bytes()


def test_wp08_telemetry_must_be_disabled_before_the_import(monkeypatch):
    monkeypatch.delenv("ORT_DISABLE_TELEMETRY", raising=False)
    with pytest.raises(ModelRefused, match="ORT_DISABLE_TELEMETRY=1"):
        loader.load_model(FIXTURE, FIXTURE_DIGEST)
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "0")
    with pytest.raises(ModelRefused, match="ORT_DISABLE_TELEMETRY=1"):
        loader.load_model(FIXTURE, FIXTURE_DIGEST)
    assert "onnxruntime" not in sys.modules


def test_wp08_loader_imports_only_the_standard_library_at_import():
    import ast  # noqa: PLC0415

    tree = ast.parse(Path(loader.__file__).read_text())
    top = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    top |= {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
    assert top == {"__future__", "dataclasses", "hashlib", "os", "re", "typing"}


def test_wp08_lock_pins_exactly_two_hashed_cp313_requirements():
    lines = [line.split() for line in LOCK.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert [line[0] for line in lines] == ["onnxruntime==1.31.0", "numpy==2.5.4"]
    assert all(len(line) == 2 and line[1].startswith("--hash=sha256:") and len(line[1]) == len("--hash=sha256:") + 64 for line in lines)
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0
    text = SCRIPT.read_text()
    assert "--no-index" in text and "--require-hashes" in text and "--no-deps" in text and "ORT_DISABLE_TELEMETRY=1" in text


# ---- in the U4 inference venv (skip when absent) -----------------------------------------------------


@needs_env
def test_wp08_identity_record_matches_the_lock():
    record = json.loads((ENV / "identity.json").read_text())
    locked = {line.split()[0].split("==")[0]: line.split()[1].removeprefix("--hash=sha256:") for line in LOCK.read_text().splitlines()
              if line.strip() and not line.startswith("#")}
    assert {w["name"].split("-")[0]: w["sha256"] for w in record["wheels"]} == locked
    assert record["lockSha256"] == hashlib.sha256(LOCK.read_bytes()).hexdigest() and record["importReturnCode"] == 0
    assert sorted(p.split("==")[0] for p in record["pipFreeze"]) == ["numpy", "onnxruntime", "pip"]  # V-1: numpy only, --no-deps


@needs_env
def test_wp08_v1_onnxruntime_runs_the_test_model_with_numpy_only():
    out, stderr = _u4(FIXTURE, FIXTURE_DIGEST, 1)
    assert out["record"]["providers"] == ["CPUExecutionProvider"] and out["record"]["onnxruntime"] == "1.31.0"
    assert out["dtype"] == "float32" and out["value"] == pytest.approx(out["reference"], rel=1e-5, abs=1e-5)
    assert "telemetry" not in stderr  # ORT_DISABLE_TELEMETRY=1 skips the 1DS initialisation (finding 2)


@needs_env
def test_wp08_v4_repeats_are_bit_exact_in_one_process_and_across_processes():
    runs = [_u4(FIXTURE, FIXTURE_DIGEST, 100 if i == 0 else 10)[0] for i in range(5)]
    assert all(len(r["hashes"]) == 1 for r in runs)  # within each process
    assert len({r["hashes"][0] for r in runs}) == 1  # across five fresh processes


@needs_env
def test_wp08_v6_in_the_venv_a_tampered_model_is_refused_before_onnxruntime_is_imported(tmp_path):
    tampered = tmp_path / "tampered.onnx"
    shutil.copyfile(FIXTURE, tampered)
    with tampered.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"\x01")
    out, _ = _u4(tampered, FIXTURE_DIGEST, 1)
    assert "differs from the declared" in out["refused"] and out["onnxruntimeImported"] is False
    out, _ = _u4(FIXTURE, FIXTURE_DIGEST, 1, telemetry_off=False)
    assert "ORT_DISABLE_TELEMETRY=1" in out["refused"] and out["onnxruntimeImported"] is False
    out, _ = _u4(FIXTURE, FIXTURE_DIGEST, 1, "wrong-schema")  # a model that does not match the declared schema
    assert "differ from the declared" in out["refused"]
