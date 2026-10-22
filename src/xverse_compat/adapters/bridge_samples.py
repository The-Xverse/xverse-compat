"""Decoder for recorded carla-simulator-bridge Zenoh samples (thesis V06).

The adapter consumes samples that were recorded or hand-authored into fixtures. It never opens a
Zenoh session. A sample carries the key expression, the payload text, a producer sequence number,
and two labelled reception timestamps (host-monotonic seconds and UTC). Decoding is fail-closed:
an undeclared key, a malformed or out-of-range payload, a stale sample or a repeated sequence is
reported as a diagnostic and never turned into a value.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

_INT_TEXT = re.compile(r"^-?[0-9]+$")
_FLOAT_TEXT = re.compile(r"^-?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?$")
MAX_PAYLOAD_CHARS = 32

#: Declared keys with their decoder kind and inclusive admissible range.
DECLARED_KEYS: Mapping[str, tuple[str, float, float]] = {
    "ego_vehicle/speed": ("int_kmh", 0.0, 400.0),
    "vehicle/status/throttle_status": ("float_unit", 0.0, 1.0),
    "vehicle/status/steering_status": ("float_unit", -1.0, 1.0),
    "vehicle/status/braking_status": ("float_unit", 0.0, 1.0),
}


class SampleDiagnostic(RuntimeError):
    """Stable, public-safe decoding failure; the sample yields no value."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure.

        @param code Stable code of the form ``XVERSE-COMPAT-SAMPLE-<REASON>``.
        @param message Public-safe explanation (no payload bytes beyond their length).
        """

        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class Observation:
    """One decoded sample with its provenance and labelled reception times."""

    key: str
    value: float
    sequence: int
    received_monotonic_s: float
    received_utc: str
    source: str = "carla-simulator-bridge"


@dataclass(frozen=True)
class DecoderPolicy:
    """Freshness and ordering policy applied by the decoder."""

    freshness_s: float = 1.0
    now_monotonic_s: float | None = None


class BridgeSampleDecoder:
    """Stateful decoder enforcing per-key sequence uniqueness and freshness."""

    def __init__(self, policy: DecoderPolicy = DecoderPolicy()) -> None:
        """Create a decoder with the given policy.

        @param policy Freshness window and the reference monotonic time used for staleness.
        """

        if not (policy.freshness_s > 0):
            raise ValueError("freshness must be positive")
        self._policy = policy
        self._seen: dict[str, set[int]] = {}

    def decode(self, sample: Mapping[str, Any]) -> Observation:
        """Decode one sample mapping or raise a diagnostic.

        @param sample Mapping with ``key``, ``payload``, ``sequence``, ``receivedMonotonicS``, ``receivedUtc``.
        @return The decoded observation.
        @raises SampleDiagnostic ``-KEY``, ``-SHAPE``, ``-MALFORMED``, ``-TIME``, ``-RANGE``, ``-STALE`` or ``-DUPLICATE``.
        """

        code = "XVERSE-COMPAT-SAMPLE"
        key = sample.get("key")
        if not isinstance(key, str) or key not in DECLARED_KEYS:
            raise SampleDiagnostic(f"{code}-KEY", "sample key is not a declared bridge key expression")
        payload = sample.get("payload")
        sequence = sample.get("sequence")
        mono = sample.get("receivedMonotonicS")
        utc = sample.get("receivedUtc")
        if not isinstance(payload, str) or type(sequence) is not int or type(mono) not in (int, float) or not isinstance(utc, str):
            raise SampleDiagnostic(f"{code}-SHAPE", "sample lacks a text payload, integer sequence or labelled reception times")
        if len(payload) > MAX_PAYLOAD_CHARS:
            raise SampleDiagnostic(f"{code}-MALFORMED", f"payload of {len(payload)} chars exceeds {MAX_PAYLOAD_CHARS}")
        if not math.isfinite(float(mono)) or float(mono) < 0:
            raise SampleDiagnostic(f"{code}-TIME", "reception monotonic time is not a finite non-negative number")
        if self._policy.now_monotonic_s is not None and float(mono) > self._policy.now_monotonic_s:
            raise SampleDiagnostic(f"{code}-TIME", "reception monotonic time lies in the future")
        kind, low, high = DECLARED_KEYS[key]
        if kind == "int_kmh":
            if not _INT_TEXT.match(payload):
                raise SampleDiagnostic(f"{code}-MALFORMED", f"payload of {len(payload)} chars is not an integer km/h text")
            value = float(int(payload))
        else:
            if not _FLOAT_TEXT.match(payload):
                raise SampleDiagnostic(f"{code}-MALFORMED", f"payload of {len(payload)} chars is not a finite decimal text")
            value = float(payload)
        if not (low <= value <= high):
            raise SampleDiagnostic(f"{code}-RANGE", f"value outside the declared range [{low}, {high}] for {key}")
        now = self._policy.now_monotonic_s
        if now is not None and (now - float(mono)) > self._policy.freshness_s:
            raise SampleDiagnostic(f"{code}-STALE", "sample older than the declared freshness window")
        seen = self._seen.setdefault(key, set())
        if sequence in seen:
            raise SampleDiagnostic(f"{code}-DUPLICATE", f"sequence {sequence} already decoded for {key}")
        seen.add(sequence)
        return Observation(key=key, value=value, sequence=sequence, received_monotonic_s=float(mono), received_utc=utc)


def read_fixture(path: Path) -> tuple[dict[str, Any], ...]:
    """Read a JSONL fixture of samples (one object per line) without interpreting it.

    @param path Fixture file.
    @return Parsed sample mappings in file order.
    """

    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return tuple(json.loads(line) for line in lines if line.strip())
