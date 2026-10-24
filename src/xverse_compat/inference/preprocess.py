"""Shared camera preprocessing for U4 and the offline training (Phase 8 WP-09 #2; ``docs/engineering/phase8/review-wp09-preprocess.md``).

``preprocess(raw, frame_format, params)`` turns one BGRA8 camera frame into the float32 NCHW tensor of the logits-only
ONNX graph: crop, resize (``area-integer`` or ``nearest``, in exact integer arithmetic), channel order, and one float64
normalisation step cast once to float32. Every parameter comes from a ``xverse-compat.preprocess/1`` record with no
defaults; the values are AD-02 protocol values. ``binding`` and ``verify_binding`` bind the parameters, this module's
source and the numpy version into the model's ``metadata_props``, which the model digest covers.

numpy is imported only inside the functions, so this module imports the standard library alone.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "xverse-compat.preprocess/1"
FORMAT_SCHEMA = "xverse-compat.camera-frame-format/1"
MEMBERS = {"schema", "input", "crop", "resize", "channels", "normalize"}
RESIZE_METHODS = ("area-integer", "nearest")
CHANNELS = {"rgb": (2, 1, 0), "bgr": (0, 1, 2)}  # indices into BGRA
META_PREFIX = "xverse.preprocess."


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _int(value, name, low=0) -> int:
    if type(value) is not int or value < low:
        raise ValueError(f"{name} must be an int >= {low}; got {value!r}")
    return value


def _exact(record, members, name) -> dict:
    if not isinstance(record, dict) or set(record) != set(members):
        raise ValueError(f"{name} members must be exactly {sorted(members)}")
    return record


@dataclass(frozen=True)
class PreprocessParams:
    """Validated parameters and the SHA-256 of their canonical record."""

    record: dict
    sha256: str
    in_w: int
    in_h: int
    crop: tuple
    out_w: int
    out_h: int
    method: str
    channels: tuple
    mean: tuple
    std: tuple


def load_params(record) -> PreprocessParams:
    """Validate a ``xverse-compat.preprocess/1`` record (fail-closed, no defaults)."""

    _exact(record, MEMBERS, "preprocess")
    if record["schema"] != SCHEMA:
        raise ValueError(f"preprocess schema must be {SCHEMA}")
    inp = _exact(record["input"], {"width", "height", "encoding"}, "input")
    in_w, in_h = _int(inp["width"], "input.width", 1), _int(inp["height"], "input.height", 1)
    if inp["encoding"] != "bgra8":
        raise ValueError("input.encoding must be bgra8 (the WP-06 frame encoding)")
    crop = _exact(record["crop"], {"x", "y", "width", "height"}, "crop")
    cx, cy = _int(crop["x"], "crop.x"), _int(crop["y"], "crop.y")
    cw, ch = _int(crop["width"], "crop.width", 1), _int(crop["height"], "crop.height", 1)
    if cx + cw > in_w or cy + ch > in_h:
        raise ValueError("crop lies outside the input")
    resize = _exact(record["resize"], {"method", "width", "height"}, "resize")
    if resize["method"] not in RESIZE_METHODS:
        raise ValueError(f"resize.method must be one of {RESIZE_METHODS}")
    out_w, out_h = _int(resize["width"], "resize.width", 1), _int(resize["height"], "resize.height", 1)
    if resize["method"] == "area-integer" and (cw % out_w or ch % out_h):
        raise ValueError("area-integer needs the crop size to be an integer multiple of the output size")
    if record["channels"] not in CHANNELS:
        raise ValueError(f"channels must be one of {sorted(CHANNELS)}")
    norm = _exact(record["normalize"], {"mean", "std"}, "normalize")
    for key in ("mean", "std"):
        values = norm[key]
        if not isinstance(values, list) or len(values) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in values):
            raise ValueError(f"normalize.{key} must be 3 finite numbers")
    if any(v <= 0 for v in norm["std"]):
        raise ValueError("normalize.std must be > 0")
    return PreprocessParams(dict(record), hashlib.sha256(_canonical(record)).hexdigest(), in_w, in_h, (cx, cy, cw, ch), out_w,
                            out_h, resize["method"], CHANNELS[record["channels"]], tuple(float(v) for v in norm["mean"]),
                            tuple(float(v) for v in norm["std"]))


def _check_format(frame_format, p: PreprocessParams) -> None:
    if not isinstance(frame_format, dict) or frame_format.get("schema") != FORMAT_SCHEMA or \
            (frame_format.get("width"), frame_format.get("height"), frame_format.get("encoding")) != (p.in_w, p.in_h, "bgra8"):
        raise ValueError("the frame format differs from the preprocessing input")


def preprocess(raw: bytes, frame_format: dict, params: PreprocessParams):
    """Return the float32 NCHW tensor ``[1, 3, out_h, out_w]`` of one BGRA8 frame."""

    import numpy as np  # noqa: PLC0415 - lazy: the module stays standard-library at import

    if not isinstance(params, PreprocessParams):
        raise TypeError("params must come from load_params")
    _check_format(frame_format, params)
    p = params
    if len(raw) != p.in_w * p.in_h * 4:
        raise ValueError(f"{len(raw)} bytes; the format needs {p.in_w * p.in_h * 4}")
    image = np.frombuffer(raw, dtype=np.uint8).reshape(p.in_h, p.in_w, 4)
    cx, cy, cw, ch = p.crop
    image = image[cy:cy + ch, cx:cx + cw, :3]
    if p.method == "area-integer":
        ky, kx = ch // p.out_h, cw // p.out_w
        sums = image.astype(np.int64).reshape(p.out_h, ky, p.out_w, kx, 3).sum(axis=(1, 3))  # exact integer block sums
        k = ky * kx
    else:
        rows = (np.arange(p.out_h, dtype=np.int64) * 2 + 1) * ch // (2 * p.out_h)
        cols = (np.arange(p.out_w, dtype=np.int64) * 2 + 1) * cw // (2 * p.out_w)
        sums = image[rows][:, cols].astype(np.int64)
        k = 1
    selected = sums[:, :, list(p.channels)]  # [out_h, out_w, 3] in the declared order
    mean = np.asarray(p.mean, dtype=np.float64)
    std = np.asarray(p.std, dtype=np.float64)
    normalized = (selected.astype(np.float64) / (k * 255.0) - mean) / std  # elementwise IEEE-754 float64, no reduction
    return np.ascontiguousarray(normalized.astype(np.float32).transpose(2, 0, 1)[np.newaxis])


def preprocess_frame(result, frame_format: dict, params: PreprocessParams):
    """Preprocess a WP-06 ``FrameResult``; refuse anything but a ``verified`` frame."""

    if getattr(result, "status", None) != "verified" or not callable(getattr(result, "pixels", None)) or result.pixels() is None:
        raise ValueError(f"only a verified frame is preprocessed; got status {getattr(result, 'status', None)!r}")
    return preprocess(result.pixels(), frame_format, params)


def code_sha256() -> str:
    """SHA-256 of this module's source bytes (part of the binding)."""

    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def binding(params: PreprocessParams, numpy_version: str | None = None) -> dict:
    """The ``metadata_props`` entries that bind this preprocessing into the model (WP-09 #4 writes them)."""

    if numpy_version is None:
        import numpy  # noqa: PLC0415

        numpy_version = numpy.__version__
    return {META_PREFIX + "schema": SCHEMA, META_PREFIX + "paramsSha256": params.sha256, META_PREFIX + "codeSha256": code_sha256(),
            META_PREFIX + "numpy": numpy_version}


def verify_binding(metadata: dict, params: PreprocessParams, numpy_version: str | None = None) -> None:
    """Refuse (``ValueError``) a model whose preprocessing binding differs from the parameters, code and numpy in use."""

    expected = binding(params, numpy_version)
    actual = {k: metadata.get(k) for k in expected} if isinstance(metadata, dict) else {}
    if actual != expected:
        differing = sorted(k for k in expected if actual.get(k) != expected[k])
        raise ValueError(f"the model's preprocessing binding differs: {differing}")
