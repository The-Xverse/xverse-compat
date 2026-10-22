"""The single compat copy of the platform's ``seconds_to_ns`` rule (round-half-even over repr)."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
import math


def seconds_to_ns(seconds) -> int:
    """Convert non-negative finite seconds to integer ns with round-half-even.

    @raises ValueError for a bool, a non-finite or a negative value.
    """

    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("seconds must be a finite, non-negative int or float")
    return int((Decimal(repr(seconds)) * 10**9).to_integral_value(ROUND_HALF_EVEN))
