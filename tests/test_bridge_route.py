"""V06: recorded bridge samples become flow-route items with a recorded origin (thesis rule 16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from xverse_compat.adapters.bridge_route import BridgeRouteAdapter, seconds_to_ns
from xverse_compat.adapters.bridge_samples import read_fixture

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bridge-samples" / "ego-speed-hand-authored.jsonl"

#: Values computed with the platform's xverse.flows.timebase.seconds_to_ns; also compared live below (L6).
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
    from xverse.flows import seconds_to_ns as platform_seconds_to_ns  # requires the Phase 6 platform (L6)

    assert seconds_to_ns(seconds) == ns == platform_seconds_to_ns(seconds)


def test_v06_adapter_items_through_the_platform_receiver_with_hand_computed_ages():
    """M2: recorded samples -> adapter -> xverse.flows.FlowReceiver in the bridge-recorder-monotonic domain."""
    from xverse.flows import FlowItem, FlowReceiver
    from xverse.flows.binding import FlowBinding, FlowPolicy
    from xverse.flows.timebase import TimeMapping

    domain = "bridge-recorder-monotonic"
    binding = FlowBinding("speed-flow", "bridge-out", "ecu-in", "speed", "ordered", FlowPolicy("fifo", "best-effort", 8, "reject", 0, 0),
                          "best_effort", "per_route_fifo", "loopback", domain, domain, TimeMapping(domain, domain, 0, 0),
                          freshness_ns=60_000_000, deadline_ns=80_000_000)

    class Clock:
        now = 0

        def read(self, d):
            assert d == domain
            return self.now

    clock = Clock()
    receiver = FlowReceiver(binding, clock)
    clock.now = 99_990_000_000  # route activation 10 ms before the first recorded sample
    receiver.activate()
    items = BridgeRouteAdapter("speed-flow", "ego_vehicle/speed").to_items(read_fixture(FIXTURE)).items
    # Receiver readings: each recorded origin plus a 5 ms processing latency, except sample 3 at +70 ms.
    readings = [100_005_000_000, 100_055_000_000, 100_170_000_000]
    verdicts = []
    for item, reading in zip(items, readings):
        clock.now = reading
        verdicts.append(receiver.receive(FlowItem(item["flowId"], item["sequence"], item["originNs"])))
    assert [(v.sequence, v.age_ns, v.verdict) for v in verdicts] == [
        (1, 5_000_000, "delivered"), (2, 5_000_000, "delivered"), (3, 70_000_000, "stale")]
    clock.now = 100_300_000_000  # final reading: last delivery at 100.055 s, deadline 80 ms
    receiver.poll()
    # 100.300 > 100.055 + k*0.080 for k = 1, 2, 3 (100.135, 100.215, 100.295): three deadline events
    assert receiver.deadline_missed_count == 3 and receiver.summary()["counts"]["stale"] == 1


def test_seconds_to_ns_refusals():
    for bad in (-1.0, float("inf"), True, "1"):
        with pytest.raises(ValueError):
            seconds_to_ns(bad)
