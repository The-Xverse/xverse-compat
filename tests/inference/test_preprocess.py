"""Phase 8 WP-09 #2: the shared preprocessing function (review-wp09-preprocess finding 1).

Record validation and the binding run everywhere (standard library). The numpy computation runs as a subprocess in the
U4 inference venv (the WP-08 pattern) and skips cleanly when that venv is absent. Every parameter value here is
test-only; no AD-02 value is set.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess

import pytest

from xverse_compat.inference import preprocess as P, unit

from .test_inference_env import LOCK, PY313, ROOT, SITE, needs_env

AREA = {"schema": P.SCHEMA, "input": {"width": 8, "height": 6, "encoding": "bgra8"}, "crop": {"x": 0, "y": 0, "width": 8, "height": 6},
        "resize": {"method": "area-integer", "width": 4, "height": 3}, "channels": "rgb",
        "normalize": {"mean": [0.5, 0.25, 0.125], "std": [0.5, 0.25, 2.0]}}
NEAREST = {**AREA, "crop": {"x": 1, "y": 1, "width": 7, "height": 5}, "resize": {"method": "nearest", "width": 3, "height": 2},
           "channels": "bgr"}


def _probe(case, record):
    proc = subprocess.run(unit.command(PY313, "tests.inference.preprocess_probe", case, json.dumps(record)),
                          env=unit.environment(SITE, (ROOT / "src", ROOT)), cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---- everywhere (standard library) -------------------------------------------------------------------


def _without(record, *path):
    out = json.loads(json.dumps(record))
    target = out
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return out


def _with(record, value, *path):
    out = json.loads(json.dumps(record))
    target = out
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return out


@pytest.mark.parametrize("record", [
    _without(AREA, "crop"), _without(AREA, "normalize", "std"), _with(AREA, 1, "extra"), _with(AREA, "x", "schema"),
    _with(AREA, "rgb8", "input", "encoding"), _with(AREA, 0, "input", "width"), _with(AREA, True, "crop", "x"),
    _with(AREA, 1, "crop", "x"),  # crop beyond the input
    _with(AREA, 3, "resize", "width"),  # 8 is not a multiple of 3 for area-integer
    _with(AREA, "bilinear", "resize", "method"), _with(AREA, "gray", "channels"),
    _with(AREA, [0.5, 0.5], "normalize", "mean"), _with(AREA, [0.5, float("nan"), 0.5], "normalize", "mean"),
    _with(AREA, [0.5, 0.0, 0.5], "normalize", "std"), _with(AREA, [0.5, True, 0.5], "normalize", "std"), None,
])
def test_wp09_invalid_or_incomplete_parameter_records_are_refused(record):
    with pytest.raises(ValueError):
        P.load_params(record)


def test_wp09_the_binding_covers_every_parameter_the_code_and_numpy():
    base = P.load_params(AREA)
    entries = P.binding(base, numpy_version="2.5.4")
    assert set(entries) == {"xverse.preprocess.schema", "xverse.preprocess.paramsSha256", "xverse.preprocess.codeSha256",
                            "xverse.preprocess.numpy"}
    assert entries["xverse.preprocess.codeSha256"] == hashlib.sha256((ROOT / "src/xverse_compat/inference/preprocess.py").read_bytes()).hexdigest()
    variants = [_with(AREA, {"x": 0, "y": 0, "width": 4, "height": 6}, "crop"),
                _with(AREA, "nearest", "resize", "method"), _with(AREA, "bgr", "channels"),
                _with(AREA, [0.5, 0.25, 0.126], "normalize", "mean"), _with(AREA, [0.5, 0.25, 2.5], "normalize", "std"),
                _with(AREA, {"method": "area-integer", "width": 2, "height": 3}, "resize")]
    digests = {P.load_params(v).sha256 for v in variants} | {base.sha256}
    assert len(digests) == len(variants) + 1  # every parameter change changes the bound digest
    P.verify_binding(entries, base, numpy_version="2.5.4")
    for key, value in [("xverse.preprocess.paramsSha256", "0" * 64), ("xverse.preprocess.codeSha256", "0" * 64),
                       ("xverse.preprocess.numpy", "2.5.3")]:
        with pytest.raises(ValueError, match=key.split(".")[-1]):
            P.verify_binding({**entries, key: value}, base, numpy_version="2.5.4")
    with pytest.raises(ValueError):
        P.verify_binding({}, base, numpy_version="2.5.4")


def test_wp09_the_numpy_used_is_the_one_pinned_by_the_u4_lock():
    pins = dict(line.split()[0].split("==") for line in LOCK.read_text().splitlines() if line.strip() and not line.startswith("#"))
    assert pins["numpy"] == "2.5.4"  # the WP-09 #3 training venv must pin the same version


def test_wp09_the_module_imports_only_the_standard_library():
    tree = ast.parse((ROOT / "src/xverse_compat/inference/preprocess.py").read_text())
    top = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    top |= {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
    assert top == {"__future__", "dataclasses", "hashlib", "json", "math", "pathlib"}  # numpy is imported inside functions


# ---- in the U4 inference venv (numpy and ONNX Runtime present) ---------------------------------------


@needs_env
@pytest.mark.parametrize("record", [AREA, NEAREST], ids=["area-integer", "nearest"])
def test_wp09_both_resize_methods_equal_the_pure_python_reference_bit_for_bit(record):
    out = _probe("compute", record)
    shape = [1, 3, record["resize"]["height"], record["resize"]["width"]]
    assert out["shape"] == shape and out["dtype"] == "float32" and out["contiguous"]
    assert out["referenceEqual"] and out["repeatEqual"]


@needs_env
def test_wp09_results_are_bit_exact_across_fresh_processes():
    assert len({_probe("compute", AREA)["sha256"] for _ in range(3)}) == 1
    assert _probe("compute", AREA)["sha256"] != _probe("compute", NEAREST)["sha256"]


@needs_env
def test_wp09_only_a_verified_frame_of_the_declared_format_is_preprocessed():
    out = _probe("frame", AREA)
    assert out["sha256"] == _probe("compute", AREA)["sha256"]  # the same tensor through the WP-06 FrameResult
    assert len(out["refusals"]) == 4 and "verified" in out["refusals"][0] and "frame format" in out["refusals"][2]


@needs_env
def test_wp09_the_binding_is_carried_in_the_model_metadata_and_its_digest():
    a, b = _probe("binding", AREA), _probe("binding", NEAREST)
    assert a["numpy"] == "2.5.4" and a["exposed"] == a["entries"]  # ONNX Runtime exposes the entries; verify_binding passed
    assert a["modelSha256"] != b["modelSha256"]  # a parameter change changes the model digest
    assert a["entries"]["xverse.preprocess.paramsSha256"] == P.load_params(AREA).sha256
