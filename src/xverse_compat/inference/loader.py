"""Digest-first loader of the frozen U4 model (Phase 8 WP-08; design record ``docs/engineering/phase8/review-wp08.md``).

``load_model`` reads the model file once and compares its SHA-256 with the declared ``sha256:<hex>`` digest
(FR-005, V-6). Refusals raise ``ModelRefused``, always before readiness:
- before ONNX Runtime is imported: an ill-formed digest, an unreadable file, a digest mismatch, telemetry not
  disabled (``ORT_DISABLE_TELEMETRY=1`` must be set in the unit environment), and ``onnxruntime`` already imported
  by someone else, whose import would have initialised its 1DS telemetry before this guard (finding 4, MEDIUM-1);
- after the import: an import failure, a session that cannot be created, providers other than exactly the CPU
  execution provider, and an input or output schema that differs from the declared one (finding 4, LOW-2).
The session is created from the verified bytes in memory, never by re-opening the path, so the file cannot change
between the check and the load. ONNX Runtime runs single-threaded and sequential, with deterministic compute, and
``disable_telemetry_events()`` is called as a second line. There is no training or write path. The U4 entry point
(WP-13) checks ``ORT_DISABLE_TELEMETRY`` before any other import and makes the schema arguments mandatory. This
module imports only the standard library at import time.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
import sys
from typing import Any

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
PROVIDERS = ["CPUExecutionProvider"]
TELEMETRY_ENV = "ORT_DISABLE_TELEMETRY"


class ModelRefused(Exception):
    """The model or its runtime is refused (fail-closed); no session exists."""


@dataclass(frozen=True)
class LoadedModel:
    """A verified inference session and the record of how it was made."""

    session: Any
    digest: str
    record: dict


def verified_bytes(path, expected_digest: str) -> bytes:
    """Return the model file's bytes if their SHA-256 equals ``expected_digest``; else raise ``ModelRefused``."""

    if not isinstance(expected_digest, str) or not DIGEST.match(expected_digest):
        raise ModelRefused(f"declared digest is not sha256:<64 lowercase hex>: {expected_digest!r}")
    try:
        with open(path, "rb") as stream:
            data = stream.read()
    except OSError as error:
        raise ModelRefused(f"model unreadable: {type(error).__name__}: {error}") from error
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != expected_digest:
        raise ModelRefused(f"model digest {actual} differs from the declared {expected_digest}")
    return data


def _signature(args) -> list:
    return [(a.name, list(a.shape), a.type) for a in args]


def load_model(path, expected_digest: str, *, expected_inputs=None, expected_outputs=None) -> LoadedModel:
    """Verify, then load the model; ``expected_inputs``/``expected_outputs``: ``[(name, shape, type), ...]``."""

    data = verified_bytes(path, expected_digest)  # V-6: refused before onnxruntime is imported
    if os.environ.get(TELEMETRY_ENV) != "1":
        raise ModelRefused(f"{TELEMETRY_ENV}=1 must be set in the unit environment before onnxruntime is imported")
    earlier = sorted(name for name in sys.modules if name == "onnxruntime" or name.startswith("onnxruntime."))
    if earlier:  # its telemetry initialised at that import, outside this guard (finding 4, MEDIUM-1)
        raise ModelRefused(f"onnxruntime was imported before the loader's telemetry guard: {earlier[:3]}")
    try:
        import onnxruntime as ort  # noqa: PLC0415 - only after the digest and environment checks
    except Exception as error:  # noqa: BLE001 - an unusable runtime is a refusal (finding 4, LOW-2)
        raise ModelRefused(f"onnxruntime import failed: {type(error).__name__}: {error}") from error

    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    options.use_deterministic_compute = True
    try:
        session = ort.InferenceSession(data, options, providers=list(PROVIDERS))
    except Exception as error:  # noqa: BLE001 - an unloadable model is a refusal, not a crash
        raise ModelRefused(f"session creation failed: {type(error).__name__}: {error}") from error
    if session.get_providers() != PROVIDERS:
        raise ModelRefused(f"providers {session.get_providers()} are not exactly {PROVIDERS}")
    inputs, outputs = _signature(session.get_inputs()), _signature(session.get_outputs())
    for label, expected, actual in (("inputs", expected_inputs, inputs), ("outputs", expected_outputs, outputs)):
        if expected is not None and [tuple(x) for x in actual] != [(n, list(s), t) for n, s, t in expected]:
            raise ModelRefused(f"model {label} {actual} differ from the declared {expected}")
    record = {"digest": expected_digest, "onnxruntime": ort.__version__, "providers": session.get_providers(),
              "intraOpThreads": 1, "interOpThreads": 1, "executionMode": "ORT_SEQUENTIAL", "graphOptimization": "ORT_ENABLE_BASIC",
              "deterministicCompute": True, "telemetry": "disabled", "inputs": inputs, "outputs": outputs}
    return LoadedModel(session, expected_digest, record)
