"""Scenario-control settings check (synchronous mode, declared fixed delta; design §1, §9.1)."""

from __future__ import annotations

from .codes import SETTINGS, CarlaRefusal
from .descriptors import SensorDescriptors


def check_settings(settings, descriptors: SensorDescriptors) -> None:
    """Refuse unless the world runs synchronously with the declared fixed delta (1e-9 s tolerance).

    @param settings Object with ``synchronous_mode`` and ``fixed_delta_seconds`` (``carla.WorldSettings``).
    """

    if getattr(settings, "synchronous_mode", None) is not True:
        raise CarlaRefusal(SETTINGS, "world is not in synchronous mode")
    delta = getattr(settings, "fixed_delta_seconds", None)
    if type(delta) not in (int, float) or abs(delta - descriptors.fixed_delta_seconds) > 1e-9:
        raise CarlaRefusal(SETTINGS, "fixed_delta_seconds differs from the descriptor")
