"""A standard-library ONNX writer for one tiny CNN-shaped test model (Phase 8 WP-08, review-wp08 finding 1).

The ``onnx`` package is not part of the U4 venv, so the test model is encoded directly in the ONNX protobuf wire
format (field numbers from ``onnx/onnx.proto``, IR version 8, opset 13). The network is

    X[1,1,8,8] -> Conv(W1[2,1,3,3], B1[2]) -> Relu -> GlobalAveragePool -> Flatten -> Gemm(W2[2,1], B2[1]) -> Sigmoid -> Y[1,1]

with fixed float32 weights from a closed form, so the bytes are deterministic. ``reference`` computes the same
network independently in NumPy for V-1. Test tooling only: it is not a thesis model and carries no evidence.

Usage: ``python -m tests.inference.minimal_onnx OUT.onnx`` writes the model.
"""

from __future__ import annotations

import math
import struct
import sys

FLOAT = 1  # TensorProto.DataType.FLOAT
ATTR_INTS = 7  # AttributeProto.AttributeType.INTS
X_SHAPE = (1, 1, 8, 8)


def _varint(value: int) -> bytes:
    value &= (1 << 64) - 1  # protobuf int64: two's complement
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _key(field: int, wire: int) -> bytes:
    return _varint(field << 3 | wire)


def _int(field: int, value: int) -> bytes:
    return _key(field, 0) + _varint(value)


def _bytes(field: int, value: bytes) -> bytes:
    return _key(field, 2) + _varint(len(value)) + value


def _str(field: int, value: str) -> bytes:
    return _bytes(field, value.encode())


def _weights(count: int, salt: float) -> list[float]:
    """Deterministic float32 values in about [-0.5, 0.5]."""

    return [struct.unpack("<f", struct.pack("<f", 0.5 * math.sin(salt + 1.37 * i)))[0] for i in range(count)]


W1 = _weights(18, 0.1)
B1 = _weights(2, 2.3)
W2 = _weights(2, 4.1)
B2 = _weights(1, 5.9)


def _tensor(name: str, dims: tuple, values: list[float]) -> bytes:
    body = b"".join(_int(1, d) for d in dims) + _int(2, FLOAT) + _str(8, name)
    return body + _bytes(9, struct.pack(f"<{len(values)}f", *values))  # raw_data


def _value_info(name: str, dims: tuple) -> bytes:
    shape = b"".join(_bytes(1, _int(1, d)) for d in dims)  # TensorShapeProto.dim{dim_value}
    tensor_type = _int(1, FLOAT) + _bytes(2, shape)
    return _str(1, name) + _bytes(2, _bytes(1, tensor_type))  # ValueInfoProto{name, type{tensor_type}}


def _node(op: str, inputs: list[str], outputs: list[str], name: str, ints: dict | None = None) -> bytes:
    body = b"".join(_str(1, i) for i in inputs) + b"".join(_str(2, o) for o in outputs) + _str(3, name) + _str(4, op)
    for attr, values in (ints or {}).items():
        body += _bytes(5, _str(1, attr) + b"".join(_int(8, v) for v in values) + _int(20, ATTR_INTS))
    return body


def model_bytes() -> bytes:
    """Return the serialized ``ModelProto``."""

    nodes = [_node("Conv", ["X", "W1", "B1"], ["c"], "conv", {"kernel_shape": [3, 3]}),
             _node("Relu", ["c"], ["r"], "relu"),
             _node("GlobalAveragePool", ["r"], ["g"], "pool"),
             _node("Flatten", ["g"], ["f"], "flatten"),
             _node("Gemm", ["f", "W2", "B2"], ["z"], "gemm"),
             _node("Sigmoid", ["z"], ["Y"], "sigmoid")]
    graph = (b"".join(_bytes(1, n) for n in nodes) + _str(2, "tiny-cnn")
             + b"".join(_bytes(5, t) for t in (_tensor("W1", (2, 1, 3, 3), W1), _tensor("B1", (2,), B1),
                                               _tensor("W2", (2, 1), W2), _tensor("B2", (1,), B2)))
             + _bytes(11, _value_info("X", X_SHAPE)) + _bytes(12, _value_info("Y", (1, 1))))
    opset = _str(1, "") + _int(2, 13)
    metadata = _bytes(14, _str(1, "purpose") + _str(2, "xverse-compat WP-08 test model; not a thesis model"))
    return _int(1, 8) + _str(2, "xverse-compat-minimal-onnx") + _str(3, "1") + _bytes(7, graph) + _bytes(8, opset) + metadata


def test_input(np):
    """The fixed V-1/V-4 input: a deterministic ramp in [0, 1)."""

    return (np.arange(64, dtype=np.float32) / np.float32(64)).reshape(X_SHAPE)


def reference(np, x):
    """The same network computed independently with NumPy (float64 accumulation)."""

    w1 = np.array(W1, dtype=np.float64).reshape(2, 1, 3, 3)
    conv = np.zeros((2, 6, 6))
    for k in range(2):
        for i in range(6):
            for j in range(6):
                conv[k, i, j] = float((x[0, 0, i:i + 3, j:j + 3] * w1[k, 0]).sum()) + B1[k]
    pooled = np.maximum(conv, 0.0).mean(axis=(1, 2))
    z = float(pooled @ np.array(W2, dtype=np.float64)) + B2[0]  # W2 is [2, 1], stored row-major
    return 1.0 / (1.0 + math.exp(-z))


if __name__ == "__main__":
    with open(sys.argv[1], "wb") as out:
        out.write(model_bytes())
