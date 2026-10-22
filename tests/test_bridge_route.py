"""V06: recorded bridge samples become flow-route items with a recorded origin (thesis rule 16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xverse_compat.adapters.bridge_route import BridgeRouteAdapter, seconds_to_ns
from xverse_compat.adapters.bridge_samples import read_fixture

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bridge-samples" / "ego-speed-hand-authored.jsonl"

#: Values computed with the platform's xverse.flows.timebase.seconds_to_ns (candidate flows-lite 17d4b1c8a).
PLATFORM_PINS = [(0, 0), (0.0, 0), (1, 1000000000), (1.0, 1000000000), (100.05, 100050000000), (100.1, 100100000000),
                 (2.5e-09, 2), (3.5e-09, 4), (123456.789012345, 123456789012345), (1e-09, 1)]


def test_v06_recorded_speed_samples_become_items_with_recorded_origin():
    batch = BridgeRouteAdapter("speed-flow", "ego_vehicle/speed").to_items(read_fixture(FIXTURE))
    assert [(i["sequence"], i["originNs"], i["value"]) for i in batch.items] == [(1, 100000000000, 0.0), (2, 100050000000, 37.0), (3, 100100000000, 38.0)]
    assert batch.refusals == () and batch.skipped == 1  # the braking-status sample is another key
    assert all(i["flowId"] == "speed-flow" for i in batch.items)


def test_v06_origin_is_checked_first():
    adapter = BridgeRouteAdapter("speed-flow", "ego_vehicle/speed")
    for mono in (None, -1.0, float("nan"), True, "100"):
        sample = {"key": "ego_vehicle/speed", "payload": "bad", "sequence": 1, "receivedMonotonicS": mono, "receivedUtc": 0}
        assert adapter.to_items([sample]).refusals == ({"index": 0, "code": "XVERSE-FLOW-ORIGIN-MISSING"},)


def test_v06_decoder_value_rules_apply_but_not_its_stale_or_duplicate_policy():
    adapter = BridgeRouteAdapter("speed-flow", "ego_vehicle/speed")
    base = {"key": "ego_vehicle/speed", "payload": "10", "sequence": 4, "receivedMonotonicS": 1.0, "receivedUtc": "2026-10-22T10:00:00Z"}
    batch = adapter.to_items([base, dict(base), dict(base, payload="999"), dict(base, payload="x"), dict(base, receivedUtc=5)])
    assert [i["sequence"] for i in batch.items] == [4, 4]  # repeats pass through: the receiver judges duplicates
    assert [r["code"] for r in batch.refusals] == ["XVERSE-COMPAT-SAMPLE-RANGE", "XVERSE-COMPAT-SAMPLE-MALFORMED", "XVERSE-COMPAT-SAMPLE-SHAPE"]


def test_v06_undeclared_key_is_refused_at_construction():
    with pytest.raises(ValueError):
        BridgeRouteAdapter("f", "camera/raw")


@pytest.mark.parametrize("seconds, ns", PLATFORM_PINS)
def test_seconds_to_ns_matches_the_platform_rule(seconds, ns):
    assert seconds_to_ns(seconds) == ns


def test_seconds_to_ns_refusals():
    for bad in (-1.0, float("inf"), True, "1"):
        with pytest.raises(ValueError):
            seconds_to_ns(bad)
