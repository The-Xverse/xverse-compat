"""Bridge samples to Phase 6 flow-route items (thesis contract rule 16, rev 8b; design §10).

``BridgeRouteAdapter`` turns recorded ``carla-simulator-bridge`` samples of one declared key into
route items ``{flowId, sequence, originNs, value}``. The origin is the recorded host-monotonic
reception time ``receivedMonotonicS`` in the declared domain ``bridge-recorder-monotonic`` (D6-3):
it is checked first, so a sample without it is refused with ``XVERSE-FLOW-ORIGIN-MISSING``. The
value is validated by a fresh ``BridgeSampleDecoder`` per sample with no reference time, so the
decoder's stale, future and duplicate policies do not apply and the receiver's verdicts stay
observable. ``bridge_samples.py`` is unchanged; nothing here opens a network session.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
import math
from typing import Any

from .bridge_samples import DECLARED_KEYS, BridgeSampleDecoder, DecoderPolicy, SampleDiagnostic

ORIGIN_MISSING = "XVERSE-FLOW-ORIGIN-MISSING"
SENDER_DOMAIN = "bridge-recorder-monotonic"


def seconds_to_ns(seconds: Any) -> int:
    """Convert non-negative finite seconds to integer ns with round-half-even (platform rule).

    @raises ValueError for a bool, a non-finite or a negative value.
    """

    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be a finite, non-negative int or float")
    return int((Decimal(repr(seconds)) * 10**9).to_integral_value(ROUND_HALF_EVEN))


@dataclass(frozen=True)
class RouteBatch:
    """Adapter output: emitted items, refusals ``{index, code}`` and the count of other-key samples."""

    items: tuple[dict[str, Any], ...]
    refusals: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    skipped: int = 0


class BridgeRouteAdapter:
    """Adapter of one declared bridge key to one flow route."""

    def __init__(self, flow_id: str, key: str, *, sender_domain: str = SENDER_DOMAIN) -> None:
        """Create the adapter.

        @param flow_id Flow (route) id the items are emitted for.
        @param key Declared bridge key expression; other keys are skipped, not refused.
        @param sender_domain Declared origin time domain.
        """

        if key not in DECLARED_KEYS:
            raise ValueError(f"key {key!r} is not a declared bridge key")
        self.flow_id = flow_id
        self.key = key
        self.sender_domain = sender_domain

    def to_items(self, samples: Iterable[Mapping[str, Any]]) -> RouteBatch:
        """Convert samples in input order.

        @param samples Recorded sample mappings (``bridge_samples.read_fixture``).
        @return Items, refusals and the skipped count.
        """

        items: list[dict[str, Any]] = []
        refusals: list[dict[str, Any]] = []
        skipped = 0
        for index, sample in enumerate(samples):
            if sample.get("key") != self.key:
                skipped += 1
                continue
            mono = sample.get("receivedMonotonicS")
            if type(mono) not in (int, float) or not math.isfinite(mono) or mono < 0:
                refusals.append({"index": index, "code": ORIGIN_MISSING})
                continue
            try:
                observation = BridgeSampleDecoder(DecoderPolicy(now_monotonic_s=None)).decode(sample)
            except SampleDiagnostic as error:
                refusals.append({"index": index, "code": error.code})
                continue
            items.append({"flowId": self.flow_id, "sequence": observation.sequence,
                          "originNs": seconds_to_ns(mono), "value": observation.value})
        return RouteBatch(tuple(items), tuple(refusals), skipped)
