"""V-1/V-4/V-6 probe run inside the U4 pattern (the real 3.13.13 interpreter, PYTHONPATH to the inference venv).

Usage: ``python -s -B -m tests.inference.probe MODEL DIGEST REPEATS [wrong-schema|import-first]`` prints one JSON line: the loader record, the
output values and the SHA-256 of each repeat's output bytes, the NumPy reference, and whether ``onnxruntime`` was
imported. A refusal prints ``{"refused": ...}``. ``import-first`` imports ``onnxruntime`` before setting
``ORT_DISABLE_TELEMETRY=1`` (the finding 4 MEDIUM-1 bypass); it initialises the default telemetry, so the test runs it
only inside ``unshare -rn``. Test tooling only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

from xverse_compat.inference.loader import ModelRefused, load_model

from . import minimal_onnx as m


def main(argv) -> int:
    path, digest, repeats = argv[0], argv[1], int(argv[2])
    shape = [1, 1, 9, 9] if argv[3:] == ["wrong-schema"] else [1, 1, 8, 8]
    if argv[3:] == ["import-first"]:
        import onnxruntime  # noqa: F401, PLC0415 - an earlier import outside the loader's guard
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    try:
        loaded = load_model(path, digest, expected_inputs=[("X", shape, "tensor(float)")],
                            expected_outputs=[("Y", [1, 1], "tensor(float)")])
    except ModelRefused as error:
        print(json.dumps({"refused": str(error), "onnxruntimeImported": "onnxruntime" in sys.modules}))
        return 0
    import numpy as np  # noqa: PLC0415

    x = m.test_input(np)
    outputs = [loaded.session.run(None, {"X": x})[0] for _ in range(repeats)]
    print(json.dumps({"record": loaded.record, "value": float(outputs[0][0, 0]), "reference": m.reference(np, x),
                      "dtype": str(outputs[0].dtype), "hashes": sorted({hashlib.sha256(o.tobytes()).hexdigest() for o in outputs}),
                      "repeats": repeats, "onnxruntimeImported": "onnxruntime" in sys.modules}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
