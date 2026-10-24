"""WP-09 #2 probe run inside the U4 inference venv (the real 3.13.13 interpreter, PYTHONPATH to the venv).

Usage: ``python -s -B -m tests.inference.preprocess_probe CASE PARAMS_JSON`` prints one JSON line. Test tooling only.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys

from xverse_compat.inference import preprocess as P

FORMAT = {"schema": P.FORMAT_SCHEMA, "width": 8, "height": 6, "encoding": "bgra8"}  # test-only frame format


def frame(width=8, height=6, salt=0) -> bytes:
    """A deterministic BGRA test frame with distinct values per pixel and channel."""

    return bytes((salt + 7 * i + 13 * (i // 4)) % 256 for i in range(width * height * 4))


def reference(raw: bytes, p: P.PreprocessParams) -> list:
    """The same formula in pure Python floats, cast with ``struct`` to float32 (an independent implementation)."""

    cx, cy, cw, ch = p.crop
    px = lambda r, c, b: raw[((cy + r) * p.in_w + (cx + c)) * 4 + b]  # noqa: E731
    out = []
    for channel in range(3):
        b = p.channels[channel]
        for i in range(p.out_h):
            for j in range(p.out_w):
                if p.method == "area-integer":
                    ky, kx = ch // p.out_h, cw // p.out_w
                    s = sum(px(i * ky + a, j * kx + c, b) for a in range(ky) for c in range(kx))
                    k = ky * kx
                else:
                    s = px((2 * i + 1) * ch // (2 * p.out_h), (2 * j + 1) * cw // (2 * p.out_w), b)
                    k = 1
                y = (s / (k * 255.0) - p.mean[channel]) / p.std[channel]
                out.append(struct.unpack("<f", struct.pack("<f", y))[0])
    return out


def main(argv) -> int:
    case, params = argv[0], P.load_params(json.loads(argv[1]))
    raw = frame()
    if case == "compute":
        tensor = P.preprocess(raw, FORMAT, params)
        again = P.preprocess(raw, FORMAT, params)
        print(json.dumps({"shape": list(tensor.shape), "dtype": str(tensor.dtype), "contiguous": bool(tensor.flags["C_CONTIGUOUS"]),
                          "sha256": hashlib.sha256(tensor.tobytes()).hexdigest(), "repeatEqual": tensor.tobytes() == again.tobytes(),
                          "referenceEqual": tensor.ravel().tolist() == reference(raw, params)}))
    elif case == "frame":
        from xverse_compat.live.frames import FrameResult  # noqa: PLC0415

        ok = FrameResult.with_pixels(raw, "verified", 1, "0" * 64, len(raw))
        tensor = P.preprocess_frame(ok, FORMAT, params)
        refusals = []
        for bad in (FrameResult.with_pixels(None, "mismatch", 1, "0" * 64, len(raw)), FrameResult("missing", 1, "0" * 64, len(raw))):
            try:
                P.preprocess_frame(bad, FORMAT, params)
            except ValueError as error:
                refusals.append(str(error))
        for fmt, data in (({**FORMAT, "width": 9}, raw), (FORMAT, raw[:-1])):
            try:
                P.preprocess(data, fmt, params)
            except ValueError as error:
                refusals.append(str(error))
        print(json.dumps({"sha256": hashlib.sha256(tensor.tobytes()).hexdigest(), "refusals": refusals}))
    elif case == "binding":
        import numpy  # noqa: PLC0415
        import onnxruntime as ort  # noqa: PLC0415 - ORT_DISABLE_TELEMETRY=1 is set by the test

        from tests.inference.minimal_onnx import model_bytes  # noqa: PLC0415

        entries = P.binding(params)
        model = model_bytes(entries)
        session = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
        meta = dict(session.get_modelmeta().custom_metadata_map)
        P.verify_binding(meta, params)
        print(json.dumps({"numpy": numpy.__version__, "entries": entries, "modelSha256": hashlib.sha256(model).hexdigest(),
                          "exposed": {k: meta.get(k) for k in entries}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
