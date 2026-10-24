"""U2 hub relay and the hub end of the Maestro fault channel (Phase 8 WP-10 increment #4; ``review-wp10-relay.md``).

The hub is the clock source and the only holder of fault descriptors. Maestro (platform ADR-ML3-SIMTIME-0001) arms
the hub with simulator-timed entries; the hub re-checks the whole batch (blueprints ``HubArmingRecheck``), reports
every apply and clear at its exact grid step, applies message faults at its delivery point, and runs the step-hold
handshake for freezes: hold the step, report, wait for Maestro's acknowledgement, resume. Selection never depends on
host time (PAIR-1). Fault records carry digests only and are never published on a runtime flow. Standard library
only; the platform package is not imported.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import re
import socket
import time
from typing import Any, Callable, Protocol

FRAME_MAX = 4096
RELAY, HOLD = "relay", "hold"
RELAY_KINDS = ("delay", "loss", "stale", "assurance.proposal-unsafe", "assurance.proposal-mistimed", "assurance.evidence-loss")
PROPOSAL_KINDS = ("assurance.proposal-unsafe", "assurance.proposal-mistimed")
_IDENT = re.compile(r"[A-Za-z0-9_.:#/-]{1,256}")
MAESTRO_FRAMES = {
    # ST-2 (thesis decisions.md "WP-10 #4 relay alignment", R-1): ``count`` and 1-based ``index`` end the batch.
    "arm": {"entry", "fault", "faultKind", "mode", "collection", "element", "atNs", "durationNs", "onsetStep",
            "clearStep", "parameters", "seed", "stepNs", "count", "index"},
    "ack": {"entry", "phase", "step", "outcome"},
    "close": {"reason"},
}
HUB_FRAMES = {
    "armed": {"entry"},
    "time": {"step", "simNs"},
    "hold": {"entry", "phase", "step", "simNs"},
    "applied": {"entry", "step", "simNs", "items"},
    "cleared": {"entry", "step", "simNs", "items"},
    "failed": {"entry", "phase", "step", "simNs", "reason"},
    # ADR-ML3-SIMTIME-0001 amendment ST-2: the hub's next frame after Maestro's ack of a hold echoes that ack's seq;
    # only then does the simulator step again, and no frame is sent between ``hold`` and ``resumed``.
    "resumed": {"entry", "phase", "step", "ackSeq"},
}


class RelayInvalid(RuntimeError):
    """The fault channel or the armed batch is invalid: the run ends (fail-closed)."""


class MaestroClosed(RuntimeError):
    """Maestro closed the fault channel (its run ended)."""


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _int(value: Any, low: int = 0) -> bool:
    return type(value) is int and low <= value <= 2**62


def _ceil_div(value: int, step: int) -> int:
    return -(-value // step)


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def decode_maestro_frame(data: bytes) -> dict:
    """Decode one Maestro frame and check it against the closed contract (shape only)."""

    if type(data) is not bytes or not 0 < len(data) <= FRAME_MAX:
        raise RelayInvalid("Maestro frame size")
    try:
        body = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise RelayInvalid("Maestro frame is not JSON") from error
    if type(body) is not dict or _canonical(body) != data:
        raise RelayInvalid("Maestro frame is not canonical JSON")
    kind = body.get("kind")
    if kind not in MAESTRO_FRAMES or set(body) != {"v", "kind", "seq"} | MAESTRO_FRAMES[kind] or body["v"] != 1 \
            or not _int(body["seq"], 1):
        raise RelayInvalid(f"Maestro frame outside the contract: {sorted(body)}")
    if kind == "arm":
        if (not all(type(body[k]) is str and _IDENT.fullmatch(body[k]) for k in ("entry", "fault", "faultKind", "element"))
                or body["mode"] not in (RELAY, HOLD) or body["collection"] not in ("flows", "componentInstances")
                or not all(_int(body[k]) for k in ("atNs", "durationNs", "onsetStep", "clearStep", "seed"))
                or not _int(body["stepNs"], 1) or type(body["parameters"]) is not dict
                or not _int(body["count"], 1) or not _int(body["index"], 1) or body["index"] > body["count"]):
            raise RelayInvalid("arm frame fields")
    elif kind == "ack":
        if (type(body["entry"]) is not str or body["phase"] not in ("apply", "clear") or not _int(body["step"])
                or body["outcome"] not in ("applied", "cleared", "refused")):
            raise RelayInvalid("ack frame fields")
    elif type(body["reason"]) is not str:
        raise RelayInvalid("close frame fields")
    return body


class MaestroEnd:
    """The hub end of Maestro's ``HubChannel``: AF_UNIX ``SOCK_SEQPACKET``, one frame per packet."""

    def __init__(self, sock: socket.socket, send_timeout_s: float) -> None:
        if (type(sock) is not socket.socket or sock.family != socket.AF_UNIX
                or sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET):
            raise ValueError("the Maestro end must be an AF_UNIX SOCK_SEQPACKET socket")
        if type(send_timeout_s) not in (int, float) or not math.isfinite(send_timeout_s) or send_timeout_s <= 0:
            raise ValueError("send_timeout_s must be a finite number > 0 (no default; D-4c)")
        self.sock, self.send_timeout_s = sock, float(send_timeout_s)
        self._send_seq = self._recv_seq = 0
        self.closed = False
        self.sent: list[dict] = []

    @classmethod
    def connect(cls, path: str, send_timeout_s: float) -> "MaestroEnd":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        sock.connect(path)
        return cls(sock, send_timeout_s)

    def send(self, kind: str, **fields: Any) -> None:
        if self.closed:
            raise RelayInvalid("the Maestro end is closed")
        if kind not in HUB_FRAMES or set(fields) != HUB_FRAMES[kind]:
            raise RelayInvalid(f"hub frame {kind!r} outside the contract")
        self._send_seq += 1
        body = {"v": 1, "kind": kind, "seq": self._send_seq, **fields}
        data = _canonical(body)
        if len(data) > FRAME_MAX:
            raise RelayInvalid("hub frame exceeds 4096 bytes")
        self.sock.settimeout(self.send_timeout_s)
        try:
            if self.sock.send(data) != len(data):
                raise RelayInvalid("short send to Maestro")
        except OSError as error:
            raise RelayInvalid(f"send to Maestro failed: {error}") from error
        self.sent.append(body)

    def receive(self, timeout_s: float) -> dict | None:
        """Return the next Maestro frame within ``timeout_s`` (0 polls), or ``None``. ``close`` raises ``MaestroClosed``."""

        if self.closed:
            raise RelayInvalid("the Maestro end is closed")
        self.sock.settimeout(timeout_s if timeout_s > 0 else 0.0)
        try:
            data = self.sock.recv(FRAME_MAX + 1)
        except (BlockingIOError, socket.timeout):
            return None
        except OSError as error:
            raise RelayInvalid(f"the Maestro channel failed: {error}") from error
        if not data:
            raise MaestroClosed("Maestro closed the channel")
        frame = decode_maestro_frame(data)
        if frame["seq"] != self._recv_seq + 1:
            raise RelayInvalid("Maestro sequence gap")
        self._recv_seq = frame["seq"]
        if frame["kind"] == "close":
            raise MaestroClosed(f"Maestro closed the channel: {frame['reason']}")
        return frame

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.sock.close()
            except OSError:
                pass


@dataclass(frozen=True)
class SimTimeBound:
    """The WP-10 §4 inequality inputs; ``None`` is unknown (D-4c) and refuses a freeze. Mirrors the blueprints
    ``SimTimeFreezeBound`` in whole steps."""

    thaw_bound_s: float | None
    max_step_host_s: float | None
    handshake_s: float | None

    def problems(self) -> list[str]:
        return [f"{name} must be a known finite number > 0 (got {getattr(self, name)!r})"
                for name in ("thaw_bound_s", "max_step_host_s", "handshake_s")
                if not (type(getattr(self, name)) in (int, float) and math.isfinite(getattr(self, name)) and getattr(self, name) > 0)]


class ProposalSets(Protocol):
    """The frozen H3 proposal sets (AD-11, AD-27 data, outside compat): replacement and injection on F12."""

    def replace(self, kind: str, entry_id: str, message: dict) -> dict: ...

    def inject(self, kind: str, entry_id: str, step: int) -> list[dict]: ...


@dataclass
class Entry:
    entry_id: str
    fault_id: str
    kind: str
    mode: str
    element: str
    at_ns: int
    duration_ns: int
    onset_step: int
    clear_step: int
    parameters: dict
    active: bool = False
    done: bool = False
    affected: int = 0
    counter: int = 0
    injected: bool = False


def _payload_digest(message: Any) -> str:
    payload = message.get("payload") if isinstance(message, dict) else None
    return hashlib.sha256(_canonical(payload)).hexdigest()


class FaultRelay:
    """Arming, grid reports, message faults at the delivery point, and the step-hold handshake."""

    def __init__(self, topology: dict, maestro: MaestroEnd, *, step_ns: int, grid_tolerance_ns: int,
                 expected_entries: list[str] | tuple[str, ...], arm_timeout_s: float, stop_wait_s: float,
                 sim_bound: SimTimeBound | None = None,
                 proposal_sets: ProposalSets | None = None, time_report_every: int | None = None,
                 host_ns: Callable[[], int] = time.monotonic_ns) -> None:
        if type(step_ns) is not int or step_ns <= 0 or type(grid_tolerance_ns) is not int or not 0 <= grid_tolerance_ns < step_ns:
            raise ValueError("step_ns > 0 and 0 <= grid_tolerance_ns < step_ns are required ints (no default; K-10, D-4c)")
        for name, value in (("arm_timeout_s", arm_timeout_s), ("stop_wait_s", stop_wait_s)):  # finding 6, L3
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite number > 0 (no default; D-4c, NEEDS DATA)")
        if time_report_every is not None and (type(time_report_every) is not int or time_report_every < 1):
            raise ValueError("time_report_every must be None or an int >= 1")
        expected = list(expected_entries)
        if not expected or len(set(expected)) != len(expected) or any(type(e) is not str for e in expected):
            raise ValueError("expected_entries must list distinct entry ids (finding 1, P-1)")
        self.topology, self.maestro = topology, maestro
        self.flows = {f["id"]: f for f in topology["flows"]}
        self.step_ns, self.grid_tolerance_ns, self.expected = step_ns, grid_tolerance_ns, expected
        self.arm_timeout_s, self.stop_wait_s = float(arm_timeout_s), float(stop_wait_s)
        self.sim_bound, self.proposal_sets = sim_bound, proposal_sets
        self.time_report_every, self._host_ns = time_report_every, host_ns
        self.entries: dict[str, Entry] = {}
        self.seed: int | None = None
        self.records: list[dict] = []
        self.armed = False
        self._held: list[tuple[int, int, Any]] = []  # (release step, order, pending item) for delay
        self._order = 0
        self._last: dict[str, Any] = {}  # last delivered pending item per flow (for stale)

    # -- evidence -------------------------------------------------------------------------------------------

    def _record(self, entry: Entry | None, action: str, step: int | None, **detail: Any) -> None:
        record = {"action": action, "step": step, "simNs": None if step is None else step * self.step_ns, "hostNs": self._host_ns()}
        if entry is not None:
            record.update(entry=entry.entry_id, fault=entry.fault_id, kind=entry.kind, target=entry.element)
        record.update(detail)
        self.records.append(record)

    # -- arming ---------------------------------------------------------------------------------------------

    def recheck(self, batch: list[dict]) -> list[str]:
        """The hub's second line over the whole armed batch (blueprints ``HubArmingRecheck``); empty means armable."""

        refusals = []
        freeze = self.topology.get("freezeTargets") or {"admitted": [], "admittedSets": []}
        single, sets = set(freeze["admitted"]), [tuple(g) for g in freeze["admittedSets"]]
        holds = [d for d in batch if d["faultKind"] == "freeze"]
        seeds = {d["seed"] for d in batch}
        if len(seeds) != 1:
            refusals.append("the armed batch carries more than one seed")
        for d in batch:
            entry = d["entry"]
            if d["stepNs"] != self.step_ns:
                refusals.append(f"{entry}: stepNs {d['stepNs']} differs from the hub step {self.step_ns}")
                continue
            onset = _ceil_div(d["atNs"], self.step_ns)
            if (d["onsetStep"], d["clearStep"]) != (onset, onset + _ceil_div(d["durationNs"], self.step_ns)):
                refusals.append(f"{entry}: onsetStep/clearStep do not match atNs/durationNs on the hub grid")
            params = d["parameters"]
            if d["faultKind"] == "freeze":
                if d["mode"] != HOLD or d["collection"] != "componentInstances" or params:
                    refusals.append(f"{entry}: a freeze must be a held componentInstances entry without parameters")
                target = d["element"]
                if target in single:
                    pass
                elif any(target in group for group in sets):
                    complete = any(target in group and all(
                        any(o["element"] == member and (o["atNs"], o["durationNs"]) == (d["atNs"], d["durationNs"]) for o in holds)
                        for member in group) for group in sets)
                    if not complete:
                        refusals.append(f"{entry}: freeze of {target} not armable alone (CC-1: every member, same onset and duration)")
                else:
                    refusals.append(f"{entry}: freeze of {target} not armable")
                if self.sim_bound is None:  # finding 6, L1: no bound configured refuses every freeze
                    refusals.append(f"{entry}: a freeze needs a configured SimTimeBound (none given)")
                else:
                    problems = self.sim_bound.problems()
                    if problems:
                        refusals.append(f"{entry}: duration bound unknown ({'; '.join(problems)})")
                    else:
                        steps = d["clearStep"] - d["onsetStep"]
                        need = steps * self.sim_bound.max_step_host_s + 2 * self.sim_bound.handshake_s
                        if need > self.sim_bound.thaw_bound_s:
                            refusals.append(f"{entry}: {steps} steps need {need:.3f} s of host time, above the thaw bound "
                                            f"{self.sim_bound.thaw_bound_s} s")
                continue
            flow = self.flows.get(d["element"])
            if (d["mode"] != RELAY or d["collection"] != "flows" or flow is None or flow["route"] != "hub"
                    or d["faultKind"] not in flow.get("faultAdmission", []) or d["faultKind"] not in RELAY_KINDS):
                refusals.append(f"{entry}: {d['faultKind']} on {d['element']} not armable (decisions.md §K)")
                continue
            kind = d["faultKind"]
            if kind == "loss":
                ok = (set(params) == {"every"} and _int(params["every"], 1)) or (
                    set(params) == {"loss-ratio"} and type(params["loss-ratio"]) in (int, float)
                    and math.isfinite(params["loss-ratio"]) and 0 < params["loss-ratio"] <= 1)
            elif kind == "delay":
                ok = set(params) == {"delay-ns"} and _int(params["delay-ns"], 1)
            else:
                ok = not params
            if not ok:
                refusals.append(f"{entry}: parameters {sorted(params)} invalid for {kind}")
            if kind in PROPOSAL_KINDS and self.proposal_sets is None:
                refusals.append(f"{entry}: {kind} needs the frozen H3 proposal sets (AD-11, AD-27), none configured")
        return refusals

    def arm(self) -> None:
        """Read the declared batch, re-check it as a whole, then send ``armed`` per entry; refuse without arming."""

        deadline = time.monotonic() + self.arm_timeout_s
        batch: list[dict] = []
        count: int | None = None
        try:
            while count is None or len(batch) < count:  # the batch ends at index == count (ST-2, R-1)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RelayInvalid(f"arming incomplete within {self.arm_timeout_s} s: {len(batch)} of "
                                       f"{count if count is not None else '?'}")
                frame = self.maestro.receive(remaining)
                if frame is None:
                    continue
                if frame["kind"] != "arm":
                    raise RelayInvalid(f"{frame['kind']} before arming completed")
                if count is None:
                    count = frame["count"]
                    if count != len(self.expected):  # the harness list stays a cross-check
                        raise RelayInvalid(f"arm count {count} disagrees with the harness list of {len(self.expected)}")
                if frame["count"] != count:
                    raise RelayInvalid(f"arm count changed from {count} to {frame['count']}")
                if frame["index"] != len(batch) + 1:
                    raise RelayInvalid(f"arm index {frame['index']} where {len(batch) + 1} was due (gap or repeat)")
                if frame["entry"] not in self.expected or any(b["entry"] == frame["entry"] for b in batch):
                    raise RelayInvalid(f"unexpected or repeated entry {frame['entry']}")
                batch.append(frame)
            refusals = self.recheck(batch)
            if refusals:
                raise RelayInvalid("arming refused: " + " | ".join(refusals))
        except (RelayInvalid, MaestroClosed) as error:
            self._record(None, "arm-refused", None, reason=str(error))
            self.maestro.close()
            raise RelayInvalid(str(error)) from error
        self.seed = batch[0]["seed"]
        for d in batch:
            entry = Entry(d["entry"], d["fault"], d["faultKind"], d["mode"], d["element"], d["atNs"], d["durationNs"],
                          d["onsetStep"], d["clearStep"], dict(d["parameters"]))
            self.entries[entry.entry_id] = entry
            self._record(entry, "armed", None, onsetStep=entry.onset_step, clearStep=entry.clear_step)
        for d in batch:
            self.maestro.send("armed", entry=d["entry"])
        self.armed = True

    # -- the step ---------------------------------------------------------------------------------------------

    def _points(self, step: int) -> list[tuple[Entry, str]]:
        points = []
        for entry in sorted(self.entries.values(), key=lambda e: e.fault_id):
            if entry.onset_step == step and not entry.active and not entry.done:
                points.append((entry, "apply"))
            if entry.clear_step == step and not entry.done:
                points.append((entry, "clear"))
        return points

    def _await_ack(self, hub: Any, entry: Entry, phase: str, step: int) -> tuple[str, int]:
        box: dict[str, Any] = {}

        def acknowledged() -> bool:
            frame = self.maestro.receive(0)
            if frame is None:
                return False
            if frame["kind"] != "ack" or (frame["entry"], frame["phase"], frame["step"]) != (entry.entry_id, phase, step):
                raise RelayInvalid(f"expected the {phase} ack of {entry.entry_id} at step {step}, got {frame}")
            box["outcome"], box["seq"] = frame["outcome"], frame["seq"]
            return True

        hub.hold(acknowledged)
        return box["outcome"], box["seq"]

    def _await_close(self) -> bool:
        """After a refused ack: wait for Maestro's close within ``stop_wait_s``; return whether it came."""

        deadline = time.monotonic() + self.stop_wait_s
        try:
            while time.monotonic() < deadline:
                if self.maestro.receive(max(0.0, deadline - time.monotonic())) is not None:
                    return False  # anything but close after a refusal: stop waiting, the run is invalid anyway
        except MaestroClosed:
            return True
        except RelayInvalid:
            return False
        return False

    def at_step(self, hub: Any, step: int, elapsed_ns: int) -> None:
        """At the step boundary: check the grid, then report and act on every point of this step, apply before clear."""

        if abs(elapsed_ns - step * self.step_ns) > self.grid_tolerance_ns:
            raise RelayInvalid(f"step {step}: simulator time {elapsed_ns} ns is off the {self.step_ns} ns grid "
                               f"beyond {self.grid_tolerance_ns} ns")
        if self.maestro.receive(0) is not None:  # only close (MaestroClosed) may arrive between handshakes
            raise RelayInvalid("unexpected Maestro frame outside a handshake")
        sim_ns = step * self.step_ns
        for entry, phase in self._points(step):
            if entry.mode == HOLD:
                self._record(entry, f"hold-{phase}", step)
                self.maestro.send("hold", entry=entry.entry_id, phase=phase, step=step, simNs=sim_ns)
                outcome, ack_seq = self._await_ack(hub, entry, phase, step)
                if outcome == "refused":
                    # Finding 9 (N1; ADR-ML3-SIMTIME-0001 decision 5): ``resumed`` follows every ack, a refused one
                    # included; then the hub never steps again and follows Maestro's close, within stop_wait_s.
                    try:
                        self.maestro.send("resumed", entry=entry.entry_id, phase=phase, step=step, ackSeq=ack_seq)
                        resumed = True
                    except RelayInvalid:  # Maestro may already have closed its end after the refusal
                        resumed = False
                    closed = self._await_close()
                    self._record(entry, "refused", step, resumedSent=resumed, maestroClosed=closed)
                    self.maestro.close()
                    raise RelayInvalid(f"Maestro refused the {phase} of {entry.entry_id} at step {step}"
                                       f" ({'close observed' if closed else 'no close within stop_wait_s'})")
                if phase == "apply":
                    entry.active = True
                    hub.freeze_unit(entry.element)
                else:
                    entry.active, entry.done = False, True
                    hub.thaw_unit(entry.element)
                self._record(entry, outcome, step)
                # ST-2: the next frame echoes the ack; only after it may the simulator step again.
                self.maestro.send("resumed", entry=entry.entry_id, phase=phase, step=step, ackSeq=ack_seq)
            elif phase == "apply":
                entry.active = True
                self._record(entry, "applied", step)
                self.maestro.send("applied", entry=entry.entry_id, step=step, simNs=sim_ns, items=0)
            else:
                entry.active, entry.done = False, True
                self._record(entry, "cleared", step, items=entry.affected)
                self.maestro.send("cleared", entry=entry.entry_id, step=step, simNs=sim_ns, items=entry.affected)
        if self.time_report_every is not None and step % self.time_report_every == 0:
            self.maestro.send("time", step=step, simNs=sim_ns)

    # -- message faults at the delivery point -----------------------------------------------------------------

    def _active_on(self, flow_id: str) -> Entry | None:
        return next((e for e in self.entries.values() if e.active and e.mode == RELAY and e.element == flow_id), None)

    def _drop(self, entry: Entry, step: int, item: Any) -> bool:
        if "every" in entry.parameters:
            entry.counter += 1
            return entry.counter % entry.parameters["every"] == 0
        digest = hashlib.sha256(f"{self.seed}:{entry.entry_id}:{item.flow}:{item.sequence}".encode()).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64) < entry.parameters["loss-ratio"]

    def _affect(self, entry: Entry, step: int, action: str, item: Any, **detail: Any) -> None:
        entry.affected += 1
        self._record(entry, action, step, flowId=item.flow, itemSequence=item.sequence, payloadSha256=_payload_digest(item.message), **detail)

    def filter(self, step: int, due: list) -> list:
        """Apply the active message faults to the items due at ``step``; release delayed items; inject proposals."""

        out = []
        released = sorted((h for h in self._held if h[0] <= step), key=lambda h: (h[0], h[1]))
        self._held = [h for h in self._held if h[0] > step]
        out.extend(h[2] for h in released)
        for item in due:
            entry = self._active_on(item.flow)
            if entry is None:
                out.append(item)
                continue
            kind = entry.kind
            if kind == "loss":
                if self._drop(entry, step, item):
                    self._affect(entry, step, "dropped", item)
                    continue
                out.append(item)
            elif kind == "assurance.evidence-loss":
                self._affect(entry, step, "dropped", item)
            elif kind == "stale":
                previous = self._last.get(item.flow)
                self._affect(entry, step, "stale" if previous is not None else "dropped", item,
                             replayedSequence=None if previous is None else previous.sequence)
                if previous is not None:
                    out.append(previous)
            elif kind == "delay":
                release = step + _ceil_div(entry.parameters["delay-ns"], self.step_ns)
                self._order += 1
                self._held.append((release, self._order, item))
                self._affect(entry, step, "delayed", item, releaseStep=release)
            else:  # proposal replacement (F12)
                variant = self.proposal_sets.replace(kind, entry.entry_id, dict(item.message))
                if not isinstance(variant, dict):
                    raise RelayInvalid(f"{entry.entry_id}: the proposal set returned no message")
                replaced = replace(item, message=variant, origin_ns=variant.get("originNs", item.origin_ns),
                                   deliver_at_ns=variant.get("deliverAtNs", item.deliver_at_ns))
                self._affect(entry, step, "replaced", item, variantSha256=_payload_digest(variant))
                out.append(replaced)
        for entry in sorted(self.entries.values(), key=lambda e: e.fault_id):
            if entry.active and entry.kind in PROPOSAL_KINDS and entry.onset_step == step and not entry.injected:
                entry.injected = True
                flow = self.flows[entry.element]
                for message in self.proposal_sets.inject(entry.kind, entry.entry_id, step) or ():
                    if not isinstance(message, dict):
                        raise RelayInvalid(f"{entry.entry_id}: an injected proposal is not a message")
                    item = _Injected(entry.element, flow["source"]["unit"], message.get("sequence"), step,
                                     message.get("originNs"), message.get("deliverAtNs"), message)
                    self._affect(entry, step, "injected", item)
                    out.append(item)
        for item in out:
            self._last[item.flow] = item
        return out

    @property
    def settled(self) -> bool:
        """Every entry is final and no hold or report is pending (ST-2: only then is the hub's close benign)."""

        return all(entry.done for entry in self.entries.values())

    def finish(self, step: int | None) -> None:
        """At the hub's own stop: close at once when settled; otherwise keep the channel open until Maestro closes
        it, within ``stop_wait_s``, then close and record the pending entries (ST-2: never close earlier)."""

        if self.maestro.closed:
            return
        if not self.settled:
            pending = sorted(e.entry_id for e in self.entries.values() if not e.done)
            self._record(None, "stopped-with-pending", step, pending=pending)
            deadline = time.monotonic() + self.stop_wait_s  # finding 6, L3: its own bound
            try:
                while time.monotonic() < deadline:
                    if self.maestro.receive(max(0.0, deadline - time.monotonic())) is not None:
                        self._record(None, "unexpected-frame-at-stop", step)
                        break
            except (MaestroClosed, RelayInvalid):
                pass
        self.maestro.close()

    def close_on_maestro_end(self, step: int | None) -> None:
        """Maestro closed the channel: stop every active relay fault locally and record it."""

        for entry in self.entries.values():
            if entry.active and entry.mode == RELAY:
                entry.active, entry.done = False, True
                self._record(entry, "cleared-by-close", step, items=entry.affected)
        self.maestro.close()


@dataclass
class _Injected:
    """An injected F12 proposal, delivered like a due item (``hub._deliver`` reads these fields)."""

    flow: str
    source_unit: str
    sequence: Any
    produced_step: int
    origin_ns: Any
    deliver_at_ns: Any
    message: dict = field(default_factory=dict)
    first_step: int | None = None
