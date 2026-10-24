"""Phase 8 WP-10 #4: the U2 hub relay and the hub end of the Maestro fault channel (review-wp10-relay finding 1).

Offline. Maestro is a fake end on a ``SOCK_SEQPACKET`` socketpair speaking the platform contract
(ADR-ML3-SIMTIME-0001 decision 4); units are the hub-core fake units; the adapter is the fake link. Every bound and
value here is a test-only value; none is a protocol value.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from xverse_compat.live.hub import F17, HubInvalidRun
from xverse_compat.live.hub_relay import (
    FRAME_MAX, FaultRelay, MaestroEnd, RelayInvalid, SimTimeBound, decode_maestro_frame,
)
from xverse_compat.live.hub_topology import TopologyError, from_system_document, validate

from .test_phase7_live import _socket_path
from .test_phase8_hub import FORM, STEP, T0, FakeLink, Reader, _emit_round0, _hub, _hub_producer

SEED = 7
RECORD = validate(from_system_document(json.loads(FORM.read_text())))
BOUND = SimTimeBound(thaw_bound_s=3.26, max_step_host_s=0.05, handshake_s=0.2)


def _frame(seq, kind, **fields):
    return json.dumps({"v": 1, "kind": kind, "seq": seq, **fields}, sort_keys=True, separators=(",", ":")).encode()


def arm(entry, kind, element, at, duration, parameters=None, *, at_ns=None, duration_ns=None, step_ns=STEP, seed=SEED):
    at_ns = at * STEP if at_ns is None else at_ns
    duration_ns = duration * STEP if duration_ns is None else duration_ns
    onset = -(-at_ns // STEP)
    hold = kind == "freeze"
    return {"entry": entry, "fault": entry.split(":")[-1], "faultKind": kind, "mode": "hold" if hold else "relay",
            "collection": "componentInstances" if hold else "flows", "element": element, "atNs": at_ns,
            "durationNs": duration_ns, "onsetStep": onset, "clearStep": onset + -(-duration_ns // STEP),
            "parameters": parameters or {}, "seed": seed, "stepNs": step_ns}


class FakeMaestro(threading.Thread):
    """Sends the arm frames, then acknowledges every hold (or refuses, or never answers), recording all frames."""

    def __init__(self, sock, arms, ack="normal", close_at_step=None):
        super().__init__(daemon=True)
        self.sock, self.arms, self.ack, self.close_at_step = sock, arms, ack, close_at_step
        self.seq, self.frames, self.acks, self.eof_at = 0, [], [], None

    def send(self, kind, **fields):
        self.seq += 1
        self.sock.send(_frame(self.seq, kind, **fields))

    def run(self):
        for descriptor in self.arms:
            self.send("arm", **descriptor)
        self.sock.settimeout(10)
        while True:
            try:
                data = self.sock.recv(FRAME_MAX)
            except (OSError, socket.timeout):
                return
            if not data:
                self.eof_at = time.monotonic()
                return
            frame = json.loads(data)
            frame["_at"] = time.monotonic()
            self.frames.append(frame)
            if frame["kind"] == "hold" and self.ack != "never":
                outcome = "refused" if self.ack == "refuse" else ("applied" if frame["phase"] == "apply" else "cleared")
                self.send("ack", entry=frame["entry"], phase=frame["phase"], step=frame["step"], outcome=outcome)
                self.acks.append(self.seq)
            if self.close_at_step is not None and frame.get("step", -1) >= self.close_at_step:
                self.send("close", reason="run-finished")
                return

    def kinds(self):
        return [(f["kind"], f.get("entry"), f.get("phase"), f.get("step")) for f in self.frames if f["kind"] != "time"]


class Proposals:
    """A test stand-in for the frozen H3 sets (AD-11, AD-27): marks each replaced proposal and injects one."""

    def __init__(self):
        self.calls = []

    def replace(self, kind, entry_id, message):
        self.calls.append(("replace", kind, message["sequence"]))
        return dict(message, payload={"variant": kind, "of": message["sequence"]})

    def inject(self, kind, entry_id, step):
        self.calls.append(("inject", kind, step))
        return [{"flowId": "f12-proposal", "sequence": 10_000, "originNs": T0, "deliverAtNs": T0, "payload": {"injected": True}}]


def _relay(arms, expected=None, **kw):
    ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    relay = FaultRelay(RECORD, MaestroEnd(ours, 1.0), step_ns=STEP, grid_tolerance_ns=kw.pop("tolerance", 1000),
                       expected_entries=expected or [a["entry"] for a in arms], arm_timeout_s=kw.pop("arm_timeout_s", 2.0), **kw)
    return relay, theirs


def _run(arms, *, frames=10, ack="normal", jitter=None, close_at_step=None, link=None, hold=0.5, **relay_kw):
    relay, theirs = _relay(arms, **relay_kw)
    maestro = FakeMaestro(theirs, arms, ack=ack, close_at_step=close_at_step)
    maestro.start()
    sources = {}
    for f in RECORD["flows"]:
        if f["route"] == "hub":
            sources.setdefault(f["source"]["unit"], []).append(f["id"])
    hub_unit = RECORD["hubUnit"]
    path = _socket_path()
    consumers = {F17: [Reader()], "f18-mrc-request": [Reader()]}
    remote = [u for u in sorted(RECORD["units"]) if u not in (hub_unit, RECORD["adapterUnit"])]
    spec = [(u, _emit_round0(sources), {"jitter_seed": None if jitter is None else jitter + i}) for i, u in enumerate(remote)]
    hub, units = _hub(RECORD, path, link or FakeLink(frames), spec, local_consumers=consumers,
                      producers=(_hub_producer(sources[hub_unit]),), relay=relay, hold=hold)
    try:
        result = hub.run(max_steps=frames + 1)
    finally:
        for u in units:
            u.join(5)
        maestro.join(5)
        theirs.close()
    return result, units, maestro


def _on(result, flow):
    return [(d["step"], d["sequence"], d["to"]) for d in result.deliveries if d["flowId"] == flow]


# ---- topology and codec ------------------------------------------------------------------------------------------

def test_topology_record_carries_fault_admission_and_freeze_targets():
    admission = {f["id"]: f["faultAdmission"] for f in RECORD["flows"] if f["faultAdmission"]}
    assert admission == {"f09-radar-vc": ["delay", "loss", "stale"],
                         "f12-proposal": ["assurance.proposal-mistimed", "assurance.proposal-unsafe"],
                         "f13-qualified-evidence": ["assurance.evidence-loss"]}
    assert RECORD["freezeTargets"] == {"admitted": ["adas-hpc-unit", "front-zone-unit", "vc-assurance-unit"],
                                       "admittedSets": [["vc-assurance-unit", "vc-functional-unit"]]}
    bad = json.loads(json.dumps(RECORD))
    bad["freezeTargets"]["admitted"].append("nobody-unit")
    with pytest.raises(TopologyError):
        validate(bad)


def test_maestro_frame_codec_is_closed_and_canonical():
    good = _frame(1, "ack", entry="fault:f", phase="apply", step=3, outcome="applied")
    assert decode_maestro_frame(good)["step"] == 3
    for bad in (good.replace(b'"seq":1', b'"seq": 1'), _frame(1, "ack", entry="fault:f", phase="up", step=3, outcome="applied"),
                _frame(1, "hold", entry="x", phase="apply", step=1, simNs=1), _frame(0, "close", reason="x"),
                _frame(1, "close", reason="x", extra=1), b"x" * (FRAME_MAX + 1)):
        with pytest.raises(RelayInvalid):
            decode_maestro_frame(bad)


# ---- arming re-check ---------------------------------------------------------------------------------------------

def _arm_only(arms, expected=None, **kw):
    relay, theirs = _relay(arms, expected=expected, **kw)
    maestro = FakeMaestro(theirs, arms)
    maestro.start()
    try:
        relay.arm()
        return relay, maestro
    finally:
        if not relay.armed:
            maestro.join(5)


@pytest.mark.parametrize("arms, expected, kw, reason", [
    ([arm("fault:a", "loss", "f12-proposal", 2, 2, {"every": 2})], None, {}, "not armable (decisions.md"),
    ([arm("fault:a", "loss", "f02-radar-raw", 2, 2, {"every": 2})], None, {}, "not armable (decisions.md"),
    ([arm("fault:a", "freeze", "vehicle-loop-unit", 2, 2)], None, {}, "not armable"),
    ([arm("fault:a", "freeze", "vc-functional-unit", 2, 2)], None, {}, "CC-1"),
    ([arm("fault:a", "freeze", "vc-functional-unit", 2, 2), arm("fault:b", "freeze", "vc-assurance-unit", 3, 2)], None, {}, "CC-1"),
    ([arm("fault:a", "freeze", "front-zone-unit", 2, 60)], None, {"sim_bound": BOUND}, "above the thaw bound"),
    ([arm("fault:a", "freeze", "front-zone-unit", 2, 2)], None, {"sim_bound": SimTimeBound(3.26, None, 0.2)}, "duration bound unknown"),
    ([arm("fault:a", "loss", "f09-radar-vc", 2, 2, {"every": 2, "loss-ratio": 0.5})], None, {}, "parameters"),
    ([arm("fault:a", "delay", "f09-radar-vc", 2, 2, {"delay-ticks": 1})], None, {}, "parameters"),
    ([arm("fault:a", "stale", "f09-radar-vc", 2, 2, step_ns=STEP // 2)], None, {}, "differs from the hub step"),
    ([dict(arm("fault:a", "stale", "f09-radar-vc", 2, 2), onsetStep=3)], None, {}, "do not match"),
    ([arm("fault:a", "stale", "f09-radar-vc", 2, 2)], ["fault:b"], {}, "unexpected or repeated"),
    ([arm("fault:a", "stale", "f09-radar-vc", 2, 2)], ["fault:a", "fault:b"], {"arm_timeout_s": 0.3}, "arming incomplete"),
    ([arm("fault:a", "assurance.proposal-unsafe", "f12-proposal", 2, 2)], None, {}, "proposal sets"),
    ([arm("fault:a", "stale", "f09-radar-vc", 2, 2), arm("fault:b", "assurance.evidence-loss", "f13-qualified-evidence", 2, 2, seed=8)],
     None, {}, "more than one seed"),
])
def test_arming_refusals_send_nothing_and_close(arms, expected, kw, reason):
    with pytest.raises(RelayInvalid, match=reason.replace("(", r"\(")):
        _arm_only(arms, expected=expected, **kw)


def test_cc1_complete_set_and_bounded_freeze_are_armed():
    arms = [arm("fault:a", "freeze", "vc-functional-unit", 2, 4), arm("fault:b", "freeze", "vc-assurance-unit", 2, 4)]
    relay, maestro = _arm_only(arms, sim_bound=BOUND)
    relay.maestro.close()
    maestro.join(5)
    assert [f["entry"] for f in maestro.frames if f["kind"] == "armed"] == ["fault:a", "fault:b"]
    assert relay.seed == SEED and set(relay.entries) == {"fault:a", "fault:b"}


def test_refused_arming_through_the_hub_is_an_invalid_run():
    with pytest.raises(HubInvalidRun, match="fault arming refused"):
        _run([arm("fault:a", "freeze", "carla-adapter-unit", 2, 2)])


# ---- reports, grid, time ----------------------------------------------------------------------------------------

def test_reports_at_the_exact_grid_steps_and_time_only_after_arming():
    arms = [arm("fault:loss", "loss", "f09-radar-vc", 2, 4, {"every": 2}), arm("fault:frz", "freeze", "adas-hpc-unit", 3, 2)]
    result, _, maestro = _run(arms, time_report_every=1)
    kinds = [f["kind"] for f in maestro.frames]
    assert kinds[:2] == ["armed", "armed"] and "time" not in kinds[:2]
    assert maestro.kinds()[2:] == [("applied", "fault:loss", None, 2), ("hold", "fault:frz", "apply", 3),
                                   ("resumed", "fault:frz", "apply", 3), ("hold", "fault:frz", "clear", 5),
                                   ("resumed", "fault:frz", "clear", 5), ("cleared", "fault:loss", None, 6)]
    times = [f["step"] for f in maestro.frames if f["kind"] == "time"]
    assert times == list(range(0, len(times))) and all(f["simNs"] == f["step"] * STEP for f in maestro.frames if "simNs" in f)
    assert result.invalid == [] and result.end_reason == "adapter-done"


class OffGridLink(FakeLink):
    def tick(self):
        result = super().tick()
        if result.items and self.tick_count == 4:
            result.items[0]["originNs"] += STEP // 2
        return result


def test_simulator_time_off_the_grid_is_an_invalid_run():
    with pytest.raises(HubInvalidRun, match="off the"):
        _run([arm("fault:a", "stale", "f09-radar-vc", 5, 2)], link=OffGridLink(10))


# ---- message faults ----------------------------------------------------------------------------------------------

def test_loss_every_n_drops_by_item_sequence_with_digest_only_records():
    baseline, _, _ = _run([arm("fault:x", "assurance.evidence-loss", "f13-qualified-evidence", 8, 1)], frames=10)
    result, _, maestro = _run([arm("fault:loss", "loss", "f09-radar-vc", 2, 4, {"every": 2})])
    before, after = _on(baseline, "f09-radar-vc"), _on(result, "f09-radar-vc")
    dropped = [r for r in result.faults if r["action"] == "dropped"]
    window = sorted({seq for step, seq, _ in before if 2 <= step < 6})
    assert [r["itemSequence"] for r in dropped] == window[1::2]
    assert sorted({seq for step, seq, _ in after}) == sorted(set(s for _, s, _ in before) - set(window[1::2]))
    assert all(set(r) >= {"payloadSha256", "itemSequence", "flowId"} and "payload" not in r for r in dropped)
    cleared = next(f for f in maestro.frames if f["kind"] == "cleared")
    assert cleared["items"] == len(dropped) == 2


def test_loss_ratio_is_a_pure_function_of_seed_entry_and_sequence():
    one, _, _ = _run([arm("fault:r", "loss", "f09-radar-vc", 0, 8, {"loss-ratio": 0.5})], jitter=1)
    two, _, _ = _run([arm("fault:r", "loss", "f09-radar-vc", 0, 8, {"loss-ratio": 0.5})], jitter=50)
    other, _, _ = _run([arm("fault:r", "loss", "f09-radar-vc", 0, 8, {"loss-ratio": 0.5}, seed=8)])
    pick = lambda r: [x["itemSequence"] for x in r.faults if x["action"] == "dropped"]  # noqa: E731
    assert pick(one) == pick(two) and pick(one) != pick(other)


def test_stale_redelivers_the_previous_item_with_its_original_stamps():
    result, _, _ = _run([arm("fault:s", "stale", "f09-radar-vc", 3, 2)])
    seqs = {}
    for step, seq, _ in _on(result, "f09-radar-vc"):
        seqs.setdefault(step, seq)
    assert seqs[3] == seqs[4] == seqs[2] and seqs[5] == seqs[2] + 3
    records = [r for r in result.faults if r["action"] == "stale"]
    assert [(r["step"], r["replayedSequence"]) for r in records] == [(3, seqs[2]), (4, seqs[2])]


def test_delay_is_rounded_up_to_the_step_grid():
    result, _, _ = _run([arm("fault:d", "delay", "f09-radar-vc", 2, 2, {"delay-ns": STEP + 1})])
    delayed = [(r["step"], r["releaseStep"], r["itemSequence"]) for r in result.faults if r["action"] == "delayed"]
    assert [(s, rel) for s, rel, _ in delayed] == [(2, 4), (3, 5)]
    delivered = {seq: step for step, seq, _ in _on(result, "f09-radar-vc")}
    assert all(delivered[seq] == rel for _, rel, seq in delayed)


def test_f12_proposals_are_replaced_and_injected_through_the_proposal_sets():
    sets = Proposals()
    result, _, _ = _run([arm("fault:p", "assurance.proposal-unsafe", "f12-proposal", 2, 2)], proposal_sets=sets)
    actions = [(r["action"], r["step"]) for r in result.faults if r["action"] in ("replaced", "injected")]
    assert actions == [("injected", 2), ("replaced", 2), ("replaced", 3)]  # injected in round 0 of the onset step
    assert ("inject", "assurance.proposal-unsafe", 2) in sets.calls
    injected = [d for d in result.deliveries if d["flowId"] == "f12-proposal" and d["sequence"] == 10_000]
    assert injected and all(d["step"] == 2 for d in injected)


def test_f13_evidence_loss_delivers_nothing_in_the_window():
    result, _, _ = _run([arm("fault:e", "assurance.evidence-loss", "f13-qualified-evidence", 2, 3)])
    steps = {step for step, _, _ in _on(result, "f13-qualified-evidence")}
    assert not steps & {2, 3, 4} and {0, 1, 5} <= steps


# ---- the step-hold handshake -------------------------------------------------------------------------------------

def test_freeze_handshake_frozen_unit_gets_no_round_and_its_deliveries_are_queued():
    result, units, maestro = _run([arm("fault:f", "freeze", "front-zone-unit", 3, 2)])
    zone = next(u for u in units if u.unit == "front-zone-unit")
    steps = sorted({s for s, _, _ in zone.rounds})
    assert 3 not in steps and 4 not in steps and 5 in steps
    assert result.invalid == [] and result.end_reason == "adapter-done"
    acks = [r["action"] for r in result.faults if r["entry"] == "fault:f"] if result.faults else []
    assert acks == ["armed", "hold-apply", "applied", "hold-clear", "cleared"]
    first_after = next(d for s, r, d in zone.rounds if s == 5 and r == 0)
    queued = [d for d in result.deliveries if d["to"] == "front-zone-unit" and d["step"] in (3, 4)]
    assert queued and [(f, q) for f, q in first_after[:len(queued)]] == [(d["flowId"], d["sequence"]) for d in queued]
    assert not [d for d in result.deliveries if d["from"] == "front-zone-unit" and d["step"] in (3, 4)]


def test_refused_ack_is_an_invalid_run():
    with pytest.raises(HubInvalidRun, match="refused"):
        _run([arm("fault:f", "freeze", "front-zone-unit", 3, 2)], ack="refuse")


def test_missed_ack_exceeds_the_hold_bound():
    with pytest.raises(HubInvalidRun, match="hold exceeded"):
        _run([arm("fault:f", "freeze", "front-zone-unit", 3, 2)], ack="never", hold=0.2)


def test_maestro_close_stops_the_relay_and_ends_the_run():
    result, _, _ = _run([arm("fault:l", "loss", "f09-radar-vc", 1, 8, {"every": 2})], time_report_every=1, close_at_step=4)
    assert result.end_reason == "maestro-closed"
    assert [r["action"] for r in result.faults if r.get("entry") == "fault:l"][-1] == "cleared-by-close"


def test_no_fault_identifier_reaches_a_unit():
    arms = [arm("fault:loss", "loss", "f09-radar-vc", 2, 4, {"every": 2}), arm("fault:frz", "freeze", "adas-hpc-unit", 3, 2)]
    result, units, _ = _run(arms)
    for unit in units:
        assert set(unit.order) <= {"origin", "round", "lost", "end"}
    assert not any("fault:" in json.dumps(d) for d in result.deliveries)


# ---- carried notes N1 and N2 --------------------------------------------------------------------------------------

def test_n1_one_deadline_covers_every_send_of_a_round(monkeypatch):
    seen = []
    from xverse_compat.live import hub as hub_module

    original = hub_module.UnitLinks.send

    def send(self, unit, message, deadline=None):
        if message.get("type") == "round":
            seen.append((message["step"], message["round"], deadline))
        return original(self, unit, message, deadline)

    monkeypatch.setattr(hub_module.UnitLinks, "send", send)
    _run([arm("fault:x", "assurance.evidence-loss", "f13-qualified-evidence", 1, 1)], frames=3)
    by_round = {}
    for step, rnd, deadline in seen:
        by_round.setdefault((step, rnd), set()).add(deadline)
    assert by_round and all(len(v) == 1 and None not in v for v in by_round.values())


def test_n2_a_failed_lost_send_loses_the_unit_at_once(monkeypatch):
    from xverse_compat.live import hub as hub_module

    original = hub_module.UnitLinks.send

    def send(self, unit, message, deadline=None):
        if message.get("type") == "lost" and unit == "vc-functional-unit":
            self.closed.add(unit)
            return False
        return original(self, unit, message, deadline)

    monkeypatch.setattr(hub_module.UnitLinks, "send", send)
    monkeypatch.setattr(hub_module.Hub, "_check_deadlines", lambda self, step, sim_ns: (
        self._mark_lost("f09-radar-vc", "test verdict", step) if step == 2 else None))
    result, _, _ = _run([arm("fault:x", "assurance.evidence-loss", "f13-qualified-evidence", 1, 1)], frames=5)
    gone = [x for x in result.invalid if x["unit"] == "vc-functional-unit"]
    assert gone and gone[0]["step"] == 2


# ---- PAIR-1 determinism ------------------------------------------------------------------------------------------

def test_pair1_same_faults_on_the_same_grid_steps_in_two_runs():
    arms = [arm("fault:loss", "loss", "f09-radar-vc", 1, 3, {"loss-ratio": 0.5}), arm("fault:frz", "freeze", "adas-hpc-unit", 2, 3),
            arm("fault:stale", "stale", "f09-radar-vc", 6, 2), arm("fault:ev", "assurance.evidence-loss", "f13-qualified-evidence", 3, 2)]
    first, _, m1 = _run(arms, jitter=3)
    second, _, m2 = _run(arms, jitter=77)
    strip = lambda records: [{k: v for k, v in r.items() if k != "hostNs"} for r in records]  # noqa: E731
    assert strip(first.faults) == strip(second.faults) and first.faults
    assert first.deliveries == second.deliveries
    assert m1.kinds() == m2.kinds()


# ---- amendment ST-2 of the platform contract --------------------------------------------------------------------

def test_st2_resumed_echoes_the_ack_and_follows_the_hold_with_no_frame_between():
    result, _, maestro = _run([arm("fault:f", "freeze", "front-zone-unit", 3, 2)], time_report_every=1)
    frames = maestro.frames
    holds = [i for i, f in enumerate(frames) if f["kind"] == "hold"]
    assert len(holds) == 2
    for index, ack_seq in zip(holds, maestro.acks):
        hold, after = frames[index], frames[index + 1]
        assert after["kind"] == "resumed" and after["ackSeq"] == ack_seq
        assert (after["entry"], after["phase"], after["step"]) == (hold["entry"], hold["phase"], hold["step"])
    assert result.invalid == []


def test_st2_armed_precedes_every_step_report():
    _, _, maestro = _run([arm("fault:a", "stale", "f09-radar-vc", 0, 1)], time_report_every=1)
    kinds = [f["kind"] for f in maestro.frames]
    assert kinds[0] == "armed" and all(k != "armed" for k in kinds[1:])
    assert maestro.frames[1]["kind"] == "applied" and maestro.frames[1]["step"] == 0


def test_st2_a_settled_hub_closes_at_its_stop_and_an_unsettled_one_waits_for_maestro():
    _, _, settled = _run([arm("fault:a", "stale", "f09-radar-vc", 1, 1)], frames=4)
    assert settled.eof_at is not None and settled.eof_at - settled.frames[-1]["_at"] < 0.3
    result, _, pending = _run([arm("fault:b", "stale", "f09-radar-vc", 2, 50)], frames=4, arm_timeout_s=0.6)
    assert pending.eof_at is not None and pending.eof_at - pending.frames[-1]["_at"] >= 0.5
    stop = [r for r in result.faults if r["action"] == "stopped-with-pending"]
    assert stop and stop[0]["pending"] == ["fault:b"]
