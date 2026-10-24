"""WP-09 #3 probe run inside the offline training venv (the real 3.13.13 interpreter, ``-S -s -B``, PYTHONPATH to the venv).

Usage: ``python -S -s -B -m tests.training.train_probe CASE OUT_DIR`` prints one JSON line. Test tooling only: the network,
data and step count are test-only, and nothing here is a thesis model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

V1_OPERATORS = {"Conv", "Relu", "GlobalAveragePool", "Flatten", "Gemm"}  # compat review-wp08 V-1
SEED, STEPS, BATCH = 1234, 20, 8


def _torch():
    import torch  # noqa: PLC0415

    torch.manual_seed(SEED)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    return torch


def _model(torch):
    return torch.nn.Sequential(torch.nn.Conv2d(3, 4, 3), torch.nn.ReLU(), torch.nn.AdaptiveAvgPool2d(1), torch.nn.Flatten(),
                               torch.nn.Linear(4, 2))


def _weights_sha256(model) -> str:
    digest = hashlib.sha256()
    for key, tensor in sorted(model.state_dict().items()):
        digest.update(key.encode() + b"\0" + tensor.detach().contiguous().numpy().tobytes())
    return digest.hexdigest()


def train(torch):
    generator = torch.Generator().manual_seed(SEED)
    x = torch.rand(STEPS, BATCH, 3, 8, 8, generator=generator)
    y = torch.randint(0, 2, (STEPS, BATCH), generator=generator)
    model = _model(torch)
    optimiser = torch.optim.SGD(model.parameters(), lr=0.1)
    for step in range(STEPS):
        optimiser.zero_grad()
        loss = torch.nn.functional.cross_entropy(model(x[step]), y[step])
        loss.backward()
        optimiser.step()
    return model.eval(), float(loss)


def main(argv) -> int:
    case, out_dir = argv[0], Path(argv[1])
    torch = _torch()
    if case == "cpu":
        print(json.dumps({"version": torch.__version__, "cuda": torch.version.cuda, "cudaAvailable": torch.cuda.is_available(),
                          "threads": torch.get_num_threads(), "deterministic": torch.are_deterministic_algorithms_enabled()}))
    elif case == "train":
        model, loss = train(torch)
        print(json.dumps({"weightsSha256": _weights_sha256(model), "loss": loss}))
    elif case == "export":
        import onnx  # noqa: PLC0415

        model, _ = train(torch)
        path = out_dir / "tiny.onnx"
        torch.onnx.export(model, torch.zeros(1, 3, 8, 8), str(path), opset_version=13, input_names=["X"], output_names=["logits"],
                          do_constant_folding=True, dynamo=False)
        proto = onnx.load(str(path))
        onnx.checker.check_model(proto)
        inputs = torch.rand(4, 1, 3, 8, 8, generator=torch.Generator().manual_seed(SEED + 1))
        with torch.no_grad():
            outputs = [model(i).numpy().tolist() for i in inputs]
        (out_dir / "io.json").write_text(json.dumps({"inputs": inputs.numpy().tolist(), "outputs": outputs}))
        data = path.read_bytes()
        print(json.dumps({"operators": sorted({n.op_type for n in proto.graph.node}), "opset": [o.version for o in proto.opset_import],
                          "irVersion": proto.ir_version, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                          "weightsSha256": _weights_sha256(model)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
