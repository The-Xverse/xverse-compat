"""WP-09 #3: run the exported test model in the U4 inference venv through the WP-08 loader and compare with PyTorch.

Usage (U4 venv, ``-S -s -B``, ``ORT_DISABLE_TELEMETRY=1``): ``python -m tests.training.ort_compare MODEL SHA256 IO_JSON`` prints the
maximum absolute difference as one JSON line. The difference is an observation, not a protocol value. Test tooling only.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

# Loaded by file path: under -S the package __init__ of xverse_compat (provider, rebuild) needs xverse_xdl, which only an
# editable install in the base pyenv site-packages provided (finding 2); loader.py itself is standard library only.
_spec = importlib.util.spec_from_file_location("wp08_loader", Path(__file__).resolve().parents[2] / "src/xverse_compat/inference/loader.py")
_loader = sys.modules["wp08_loader"] = importlib.util.module_from_spec(_spec)  # dataclasses resolve the module there
_spec.loader.exec_module(_loader)
load_model = _loader.load_model


def main(argv) -> int:
    model, digest, io_path = argv
    loaded = load_model(model, "sha256:" + digest, expected_inputs=[("X", [1, 3, 8, 8], "tensor(float)")],
                        expected_outputs=[("logits", [1, 2], "tensor(float)")])
    import numpy as np  # noqa: PLC0415

    io = json.loads(Path(io_path).read_text())
    diffs = []
    for x, want in zip(io["inputs"], io["outputs"]):
        got = loaded.session.run(None, {"X": np.asarray(x, dtype=np.float32)})[0]
        diffs.append(float(np.max(np.abs(got.astype(np.float64) - np.asarray(want, dtype=np.float64)))))
    print(json.dumps({"maxAbsDiff": max(diffs), "perInput": diffs, "providers": loaded.record["providers"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
