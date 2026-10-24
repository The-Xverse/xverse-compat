# Review log: Phase 8 WP-10 increment #4, the U2 hub relay (xverse-compat)

Candidate `candidate/phase8-wp10-relay-20261024`, base main `34b514d` (hub core merged). Specification:
- thesis `specs/002-assured-aeb/design/wp10-fault-relay.md` §3 and §4, decided as option (A) in the `decisions.md`
  row "WP-10 fault relay" (under the author's delegation, flagged for review);
- the platform side of the control channel. This is platform candidate `candidate/lite-simtime-faults-20261024` at
  `920f7e6e6`, read-only: `ADR-ML3-SIMTIME-0001.md` decisions 4–5 and `src/xverse/faults/simtime.py`, which is
  under independent review. Compat does not import the platform package;
- the hub re-check rule at blueprints main `18201fe`, `automotive/assured-aeb/admission.py` `HubArmingRecheck`
  (target and kind from the topology form, the CC-1 set rule over the whole batch, and the duration bound);
- the notes carried from the hub core (`review-wp10-hub.md` §7: N1, N2 and R-9).

Findings are recorded before repairs. The maturity is an engineering increment verified offline with a fake Maestro
end: not M1, no CARLA, no live run.

## Findings

1. **Design record: the hub relay and the hub end of the control channel (written at 15:33:33 2026-10-24,
   before any code).**
   - **Module.** A new `live/hub_relay.py` (standard library only), plus hooks in `live/hub.py`. The hub core
     keeps its behaviour when no relay is configured: the existing tests stay unchanged, apart from the N1 and N2
     repairs.
   - **Topology contract.** `hub_topology.from_system_document` adds, as optional fields of
     `xverse-compat.hub-topology/1`:
     - each flow's `faultAdmission`, the list of kinds;
     - the record's `freezeTargets` (`admitted` and `admittedSets`).

     `validate` checks both when present. They come from the topology form's blueprint extension, the same data
     that `HubArmingRecheck` reads.
   - **The Maestro end (`MaestroEnd`).**
     - **Transport.** An AF_UNIX `SOCK_SEQPACKET` client socket to the run-scoped path given by the harness
       (increment #5). The harness passes the listening end to Maestro as the `HubChannel`.
     - **Frames.** Canonical JSON (sorted keys, no whitespace), at most 4 096 B, with `v: 1` and a sequence per
       direction starting at 1, and the closed key sets of ADR-ML3-SIMTIME-0001 decision 4.
     - **Inbound check.** Every Maestro frame is checked against them. A violation ends the run: `HubInvalidRun`,
       the link is closed, and nothing more is sent.
   - **Arming.**
     - **Order.** The hub connects and arms before its first adapter tick, so no step exists before arming.
     - **Batch.** It reads `arm` frames until it holds exactly the declared entry set. An unexpected or repeated
       entry, or a missed `arm_timeout_s`, refuses arming.
     - **Re-derivation.** Each descriptor's `onsetStep` and `clearStep` are re-derived from `atNs`, `durationNs`
       and the hub's own `step_ns`, as `ceil(atNs/step)` and `onset + ceil(durationNs/step)`. A different
       `stepNs` or step value refuses arming.
     - **Re-check** (it mirrors `HubArmingRecheck`):
       - a relay entry's kind must be in its flow's `faultAdmission`, and its mode must be `relay`;
       - a `freeze` (mode `hold`) must target an `admitted` unit, or a member of an `admittedSets` group with every
         member in the batch at the same onset and duration (CC-1);
       - when a `SimTimeBound` is given, a freeze must satisfy
         `held_steps · max_step_host_s + 2 · handshake_s ≤ thaw_bound_s`, and an unknown bound refuses;
       - the parameters are checked per kind: `loss` takes exactly one of `every` or `loss-ratio`, `delay` takes
         `delay-ns`, and every other kind takes none;
       - the F12 assurance kinds need a configured proposal-set provider.
     - **Refusal.** A refusal sends nothing, closes the link and ends the run (`HubInvalidRun`). Maestro then sees a
       closed channel, which fails its run (`ML-SCHEDULE-FAULT-CLOCK`). There is no partial arming.
     - **Success.** One `armed` per entry, in the received order.
   - **Simulator clock and grid.**
     - Hub step `k` is the platform grid step `k`. The hub reports `simNs = k · step_ns`.
     - At each step the hub checks `|(frame_ns − episode_origin) − k · step_ns| ≤ grid_tolerance_ns`, otherwise
       `HubInvalidRun`. A dropped or extra frame cannot shift the grid silently.
     - `step_ns` and `grid_tolerance_ns` are required, with no default (K-10, D-4c).
   - **Reports.**
     - `time` frames go only after every entry is armed (platform R9), every `time_report_every` steps, or never
       when that is `None`.
     - At step `k`, before the step's rounds, the hub sends the report of every entry whose `onsetStep` or
       `clearStep` is `k`, ordered by fault id, apply before clear: `applied`/`cleared` for relay entries, and
       `hold` for freezes. It therefore never sends a frame at a later step while a point is pending.
   - **Step-hold handshake (freeze).** At `onsetStep` the hub does not run the step's rounds, and the adapter is
     not ticked.
     - It sends `hold(apply)` and waits for the `ack` within `hold_bound_s`, through the core's bounded `hold`.
     - On `outcome: applied` the target unit enters the frozen set. On `refused`, on a frame that is not the
       expected ack, or at the bound, the run is `HubInvalidRun`.
     - The thaw runs the same way at `clearStep`.
     - **While a unit is frozen (R-9):**
       - it receives no round;
       - it is not waited for;
       - it cannot be lost through a send timeout.
     - Its deliveries, and any `lost` notices for it, are queued in order. They are delivered at the first round
       after the thaw, so the frozen unit misses no message in a host-timing-dependent way.
   - **Message faults at the hub delivery point** (`HubSchedule.due`, then the relay filter, then `_deliver`).
     Window: the steps `onsetStep ≤ s < clearStep`.
     - **`loss`.** With `every: N`, the n-th due item on the flow inside the window, counted from 1, is dropped
       when `n % N == 0`. With `loss-ratio: r`, an item is dropped when
       `SHA-256(seed:entry:flow:item-sequence)/2^64 < r`. Selection is by item sequence and the run seed, never by
       host time (PAIR-1).
     - **`stale`.** The previously delivered item on the flow is delivered again, with its original stamps and
       payload, in place of the new one. With no earlier item, the new one is dropped.
     - **`delay`.** An item due at step `s` is held to step `s + ceil(delay_ns / step_ns)` (rounded up to the grid,
       AD-30), then delivered in round 0 of that step. The release step stays fixed after the clear.
     - **`assurance.proposal-unsafe` and `assurance.proposal-mistimed` (F12).** Each due proposal in the window is
       **replaced** by `ProposalSets.replace(kind, entry, item)`. `ProposalSets.inject(kind, entry, step)` may add
       proposals at the onset step.
       - The sets are AD-11 and AD-27 data (the frozen H3 sets), outside compat. Only the interface and a test fake
         are provided.
       - Without a provider these kinds refuse arming.
     - **`assurance.evidence-loss` (F13).** Each due item in the window is not delivered.
     - **Counts.** `cleared.items` is the number of affected items, and `applied.items` is 0.
   - **Evidence.**
     - `HubResult.faults` holds one record per decision: arm, apply, clear and each affected item.
     - Each record carries entry, kind, flow or unit, step, `simNs`, host monotonic ns, item sequence and the
       SHA-256 of the canonical payload. It holds no payload.
     - The records are written to the result only, and are never published on a runtime flow. A test checks that
       no unit receives a fault identifier.
   - **Carried notes.**
     - **N1, fixed.** A round has one deadline: `wait_bound_s` from the round's start covers the sends and the
       wait.
     - **N2, fixed.** A failed `lost` or `origin` send calls `_unit_gone` at once.
     - **R-9.** It is covered by the frozen-set rules above.
   - **Platform alignment notes (for the platform review and increment #5; no change made here).**
     - **P-1. The platform protocol has no batch end for `arm`.** Maestro sends one `arm` per entry with no count.
       The hub therefore needs the declared entry set out of band, from the harness (increment #5), which holds the
       same admitted schedule.
       - Proposed platform amendment: add `count` and `index` to `arm`.
       - Until then, `expected_entries` is a required hub parameter whenever a Maestro end is configured.
     - **P-2. Two time domains.** The blueprint admission path keys simulator-time faults to `carla-simulation`
       (`admission.py` `SIM_DOMAIN`). The Maestro form has one domain, `experiment-time`, and the platform requires
       the fault's `timeDomainId` to equal `SimulationClock.domain`, the one admitted domain (L-1).
       - Increment #5 must emit the Maestro-form faults in `experiment-time`, with the binding naming it.
       - Otherwise the platform must accept the topology-form domain.
       - This is recorded for the coordinator.
   - **Planned tests** (offline, with a fake Maestro end, fake units and a fake link):
     - the frame codec;
     - arming and every re-check refusal: kind, target, CC-1 lone member, CC-1 mismatched onset, duration bound,
       unknown bound, parameters, `stepNs` mismatch, step mismatch, unexpected entry, timeout, and no provider;
     - `time` only after arming;
     - reports at the exact grid steps;
     - the grid tolerance;
     - each relay action on F09, F12 and F13 with digest-only evidence;
     - the freeze handshake, frozen-unit exemptions and queued deliveries, a refused ack and a missed ack;
     - N1 and N2;
     - PAIR-1 determinism: two runs with different unit answer jitter give identical deliveries and fault records,
       host times aside.

2. **Implementation, conformance to platform amendment ST-2, and offline verification (written at 15:41:25
   2026-10-24).**
   - **Commits.** `11e117a` is finding 1, before any code; `5bb35ba` is the code and tests.
   - **Contract change during the increment (ST-2).** The coordinator relayed platform review finding 3:
     ADR-ML3-SIMTIME-0001 amendment ST-2, and the thesis row "WP-10 #3 review dispositions". The platform side is
     not merged. This branch conforms to the contract as specified, tested with fakes.
     - **`resumed`.** A new hub frame `resumed` (`entry`, `phase`, `step`, `ackSeq`) is the hub's next frame after
       Maestro's `ack` of a hold. It echoes the ack's `seq`, entry, phase and step. Only then does the simulator
       step again, and no frame is sent between `hold` and `resumed`.
       - After a `refused` ack, no `resumed` is sent. The run ends (`HubInvalidRun`) and the simulator never steps
         again.
     - **`armed` first.** Every `armed` precedes any report: the hub arms the whole batch before its first tick.
     - **Benign close.** The hub closes its end at its own stop only when settled, that is, when every entry is
       final and no hold or report is pending.
       - Otherwise it records `stopped-with-pending` with the pending entries.
       - It then keeps the channel open until Maestro closes it, at most `arm_timeout_s`, and only then closes.
       - When Maestro's `close` arrives mid-run, the hub stops every active relay fault (`cleared-by-close`) and
         ends with `end_reason: maestro-closed`.
   - **What was built.** It follows the design in finding 1.
     - `live/hub_relay.py` (+~420 lines, standard library) and hooks in `live/hub.py`.
     - Optional `faultAdmission` and `freezeTargets` in the topology record.
     - The frozen-unit rules (R-9), and the repairs of N1 (one deadline per round) and N2 (a failed `lost` or
       `origin` send loses the unit at once).
     - The platform package is not imported. The frame contract is re-implemented from the ADR.
   - **Tests.** `tests/live/test_phase8_hub_relay.py` has 38 cases, offline. Maestro is a fake end on a
     `SOCK_SEQPACKET` socketpair; the units and the adapter link are the hub-core fakes, over the real MLOC topology
     form `5f71cde`.
     - **Topology and codec:**
       - fault admission and freeze targets come from the form, and an unknown freeze unit is refused;
       - the Maestro frame codec refuses 6 malformed frames.
     - **Arming re-check (15 refusals):**
       - kind not admitted on F12; a non-hub flow; a refused unit;
       - CC-1 with a lone member, and CC-1 with mismatched onsets;
       - a duration above the thaw bound, and an unknown bound;
       - both loss parameters given; `delay-ticks`;
       - a different `stepNs`; mismatched grid steps;
       - an unexpected entry; arming not completed in time;
       - proposal kinds with no sets; two seeds.

       In every refusal case nothing is sent and the link is closed. A complete CC-1 pair with a bounded duration
       is armed. A refusal through the hub is a `HubInvalidRun`.
     - **Reports and the grid:**
       - reports come at the exact steps, ordered apply before clear, with `resumed` after each hold;
       - `time` frames come only after arming;
       - every `simNs` equals `step · step_ns`;
       - an off-grid frame is an invalid run.
     - **Message faults:**
       - `loss` with `every` drops exactly the alternate in-window sequences, with digest-only records and
         `cleared.items` equal to the number dropped;
       - `loss-ratio` is a pure function of the seed, the entry and the sequence (equal under different unit
         jitter, different under another seed);
       - `stale` redelivers the previous sequence;
       - `delay-ns` of one step plus 1 ns releases after two steps;
       - F12 proposals are replaced and injected through `ProposalSets`, with the injection at the onset step;
       - F13 delivers nothing inside the window.
     - **Handshake:**
       - the frozen unit gets no round at steps 3 and 4, its queued deliveries come first at step 5, it produces
         nothing in the window, and the run stays valid;
       - a refused ack and a missed ack (the hold bound) are invalid runs;
       - Maestro's close stops the relay;
       - no unit receives any fault identifier.
     - **N1 and N2.** All sends of a round share one deadline, and a failed `lost` send loses the unit in the same
       step.
     - **PAIR-1.** Two runs with four faults (ratio loss, freeze, stale and F13 loss) and different unit-answer
       jitter give identical fault records (host time aside), identical deliveries and identical Maestro-side frame
       sequences.
     - **ST-2:**
       - `resumed` immediately follows each `hold`, echoing the ack's sequence number;
       - `armed` precedes every report;
       - a settled hub closes at once, and an unsettled one waits for Maestro, at least 0.5 s of a 0.6 s bound,
         recording the pending entry.
     - **Stability.** 38 of 38 passed in each of 3 consecutive runs.
     - **Mutation controls (run, then reverted; the files are byte-identical to `5bb35ba`):**
       - with no `resumed`, 2 cases fail;
       - when frozen units still get rounds, the handshake case fails;
       - with CC-1 disabled, both CC-1 refusals fail;
       - with loss selection by host time, the ratio and PAIR-1 cases fail.
   - **Suite.** `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src /dev/shm/compat-p6-venv/bin/python
     -m pytest tests -q -p no:cacheprovider` gives **573 passed, 39 subtests**, including the 38 new cases. The
     51 existing hub-core cases are unchanged and pass with the N1 and N2 repairs. No CARLA and no live run were
     used.
   - **Residuals (open).**
     - **R-1 (P-1): the platform `arm` has no batch end.** The hub requires `expected_entries` from the harness
       (increment #5). The proposed platform amendment is a `count` (and `index`) on `arm`.
     - **R-2 (P-2): the time domains differ.**
       - The blueprints key simulator-time faults to `carla-simulation`.
       - The platform requires `SimulationClock.domain`, the single Maestro-form domain `experiment-time`.
       - Increment #5 must align them, or the platform must accept the topology-form domain.
     - **R-3. The H3 proposal sets** are an interface only: AD-11 and AD-27 data, which do not exist yet.
       Injection happens once, in round 0 of the onset step.
     - **R-4. Deliveries to a frozen unit are queued and delivered after the thaw, rather than dropped.** This
       models a frozen process whose socket buffer is kept. It is deterministic by step, and is a design choice
       for the author and AD-12.
     - **R-5. Values.** `step_ns`, `grid_tolerance_ns`, `arm_timeout_s` (which also bounds the wait at an
       unsettled stop), the Maestro send timeout, the hold bound, the wait bound and the `SimTimeBound` are D-4c
       or K-10 inputs, and every one is required.
     - **R-6. Peer authentication.** The hub connects to a path that the harness supplies, and does not
       authenticate Maestro. Maestro checks only the uid (platform R3).
     - **R-7. A frozen unit's link failures surface only after the thaw.** Its inbox is not read while it is
       frozen.
     - **R-8. Interoperability.** A wire-level test against the real platform `HubChannel`, with ST-2, has not
       run, because the platform side is unmerged and compat does not import it. It belongs to increment #5 or a
       harness check.
     - **R-9. Live behaviour.** CARLA, the real frame grid tolerance and D-4c are unverified (E8-3a, increment #5).
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.

3. **Dispositions of the alignment residuals (written at 15:42:57 2026-10-24, before code).** Source: the thesis
   `decisions.md` row "WP-10 #4 relay alignment" (15:42, under the author's delegation, flagged for the author's
   review), relayed by the coordinator.
   - **R-1, adopted.** The platform `arm` frame gains the closed keys `count` and `index` (1-based), as part of
     ST-2.
     - **Batch end.** The hub uses them to detect that arming is complete.
     - **Refusals.** The hub refuses arming for any of the following:
       - a `count` that differs between frames, or that differs from the harness list;
       - an `index` outside 1..`count`;
       - an `index` that is not the next one, which covers both a gap and a repeat;
       - a repeated entry;
       - an entry not in the harness list.
     - **Cross-check.** The harness's `expected_entries` stays as a cross-check, not as the batch-end signal.
   - **R-2, assigned to WP-10 #5.** The platform keeps one time domain per Maestro form. WP-10 #5 maps the
     blueprints domain `carla-simulation` onto the form's `experiment-time` domain, whose clock source is the
     CARLA-facing unit, and records the mapping in the run's evidence. Compat needs no change.
   - **R-4, adopted as built.** Deliveries to a frozen unit are queued and delivered after the thaw, modelling a
     stopped process whose socket buffer still accepts. A full buffer during a freeze is a declared residual
     (AD-12).
   - **Change planned.** `live/hub_relay.py`: the `arm` key set, its field checks, and arming completion by `count`
     and `index`. New tests: completion by count; a wrong count; an index gap; a repeated index; a duplicated entry;
     and a count that disagrees with the harness list.

4. **R-1 implemented: arming ends by `count` and `index`, and the suite was re-run (written at 15:44:40 2026-10-24).**
   - **Change** (`live/hub_relay.py`):
     - The `arm` key set gains `count` and `index`. Each must be an integer of at least 1, with `index` ≤ `count`.
     - Arming ends when the batch holds `count` entries.
     - The first frame's `count` must equal the harness `expected_entries` (the cross-check).
     - Every later frame must carry the same `count`, and `index` must be exactly the next one. A repeated or
       unexpected entry is refused, as before.
     - Every refusal sends nothing, closes the link and ends the run.
     - R-2 and R-4 need no compat code (finding 3).
   - **Tests.** `test_phase8_hub_relay.py` now has 44 cases, 6 more than before:
     - completion at `index == count`;
     - a `count` that disagrees with the harness list;
     - a changed `count`;
     - an index gap (2 first);
     - a repeated index;
     - a duplicated entry at the next index.

     The batch-incomplete case now declares `count: 2` and sends one frame. The codec case adds an `arm` without
     `count` and `index`, one with `index` above `count`, and one with `count: 0`. The fake Maestro adds `count` and
     `index` to every arm frame.
   - **Mutation control (run, then reverted; the file is byte-identical).** With the index check disabled, both
     gap and repeat cases fail.
   - **Suite.** The same command as finding 2 gives **579 passed, 39 subtests** (573 + 6), at load about 5.7
     (`evidence-wp10-relay-suite-finding4.log`). No CARLA and no live run were used.
   - **Residuals.**
     - R-1 is closed on the hub side. The platform must emit `count` and `index` in ST-2.
     - R-2 belongs to WP-10 #5.
     - R-4 is adopted. The full-buffer case is a declared residual (AD-12).
     - R-3 and R-5 to R-9 are unchanged.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
5. **Independent review of findings 1 to 4 (written at 15:47:14 2026-10-24).** Reviewer: an independent Claude agent
   that did not write the increment. Scope: `34b514d..c8c376a` (`11e117a`, `5bb35ba`, `6557b42`, `14478e5` and
   `c8c376a`). **Verdict: PASS WITH NOTES.**
   - **Nothing blocks the merge of increment #4.** The merge still needs the author's or the coordinator's
     acceptance, which this finding does not give.
   - **M1 must be repaired before the first live run with a `delay`, or with any fault on a flow that can be lost.**
   - **R-8**, the wire test against the platform with ST-2, must pass before increment #5 wires a live run.
   - **What was checked, and the result.**
     - **Suite at `c8c376a`.** The worktree was clean and the implementer idle. The command given gave **579 passed,
       39 subtests** in 36 s. The relay and hub-core files were run twice more: 95 passed each time.
     - **Frame contract (ST-2, thesis rows "WP-10 #3 review dispositions" and "WP-10 #4 relay alignment").**
       - **Closed sets.** The Maestro frames have closed key sets, including `count` and `index`. The JSON is
         canonical, at most 4 096 B, with no NaN, and the sequence rises by exactly 1 (`hub_relay.py`
         `decode_maestro_frame`, `MaestroEnd.receive`).
       - **Arming end.** Arming ends at `index == count`, the first `count` must equal the harness list, `count` may
         not change, and `index` must be the next one (`:325-350`).
       - **`armed` first.** Every `armed` is sent before the first tick (`hub.py` `run`), so before any report.
       - **`resumed`.** It is the only frame after a hold's ack, and it echoes `ackSeq`. After a `refused` ack nothing
         is sent and the run is invalid (`at_step`).
       - **Benign close.** The hub closes at its own stop only when settled. Otherwise it waits for Maestro's close
         (`finish`, `:505-520`).
       - **Interop not tested.** The platform branch at `920f7e6e6` has no `resumed`, `count` or `index` yet, because
         ST-2 has not landed. Interoperability is therefore untested (R-8).
     - **No host time in fault selection (PAIR-1).**
       - `every` counts in-window due items in the hub's sorted delivery order, and `loss-ratio` hashes
         `seed:entry:flow:sequence`.
       - `stale`, `delay` (the release step) and the F12 replacement are keyed to steps and sequences.
       - Host time appears only in the evidence (`hostNs`) and in bounding the waits. The PAIR-1 test compares runs
         with different unit jitter, host time aside.
     - **CC-1 and the re-check against blueprints `HubArmingRecheck` (`18201fe`, `admission.py:206-247`).** The
       target and kind rule, the CC-1 rule (every member, the same `atNs` and `durationNs`) and the duration-bound
       rule are equivalent.
       - **Compat is stricter**, and fail-closed: it also requires a `hub` route, the declared mode and collection,
         per-kind parameters, an equal `stepNs`, re-derived grid steps, one seed, and a configured proposal provider.
       - **The real form.** On the MLOC form `5f71cde`, only F09 {delay, loss, stale}, F12 {the two proposal kinds}
         and F13 {evidence-loss} carry `faultAdmission`. The freeze targets are front-zone, adas-hpc and vc-assurance
         alone, plus the set {vc-assurance, vc-functional}. Neither the clock source (vehicle-loop) nor the adapter
         is freezable. This matches §K.
     - **Frozen units (R-4) and the N1/N2 repairs.**
       - A frozen unit gets no round, is not waited for, and receives no send.
       - Its deliveries and its `lost` notices are queued and go out at its first round after the thaw.
       - **N1.** One deadline covers a round's sends and its wait.
       - **N2.** A failed `origin` or `lost` send calls `_unit_gone` at once (`hub.py` `_bind_origin`, `_notify`).
     - **No fault identifier on runtime flows.** Fault records go to `HubResult.faults` only. Deliveries carry the
       flow id, source, sequence, stamps and payload. A test asserts that no unit receives a fault identifier.
     - **No invented timing values.** `step_ns`, `grid_tolerance_ns` (< `step_ns`), `arm_timeout_s`, the Maestro send
       timeout and the `SimTimeBound` are required, with no default. The only literal is the hub core's existing
       0.005 s poll.
   - **Issues.**
     - **M1 (MEDIUM; does not block the merge; repair before the first live run with `delay`, or with any fault on a
       flow that can be lost): the Lost-flow rule is bypassed by items the relay holds or creates.**
       - **The rule.** `decisions.md` "Lost-flow rule": once a flow is lost, nothing is delivered on it after the
         verdict.
       - **The gap.** `HubSchedule.discard_flow` empties only the schedule's pending list. The relay's `_held`
         (delayed) items, its F12 injections, and the frozen-unit queues still reach `_deliver`
         (`hub_relay.py:445-500`; `hub.py:462-479,483-495`). `_deliver` does not consult `schedule.lost`.
       - **Probe.** A `delay` of two steps on F09 holds sequence 1 at step 2 (release at step 4). The flow is lost at
         step 3 (`schedule.lost = {f09}`). `filter(4)` still returns `('f09-radar-vc', 1)`, which `_deliver` then
         delivers after the verdict.
       - **A frozen unit sees the wrong order.** It is sent its queued control first (`hub.py:488`) and its queued
         deliveries second (`:494`). A `lost` that arrives during the freeze therefore precedes deliveries that were
         queued before it.
       - **Repair.**
         - Apply the barrier at one point: in `_deliver`, or on the relay's output. Items of a lost flow are
           discarded and recorded in `schedule.discarded` (digest only, with reason "relay-held at the lost
           verdict").
         - Keep a single ordered queue of deliveries and control messages per frozen unit.
         - Add tests: delay then loss; an injection after a loss; a loss during a freeze.
     - **L1 (LOW): a freeze is armable with no duration bound.** With `sim_bound=None` the re-check applies no bound
       at all (`hub_relay.py:289`). A 400-step freeze of front-zone is armable (probe: no refusal). Blueprints has
       the same semantics, and the platform refuses freezes while D-4c is unknown, so a second line exists elsewhere.
       But "an unknown bound refuses" holds only when a `SimTimeBound` object is passed. **Repair.** Refuse a `freeze`
       in the batch whenever no `SimTimeBound` is configured.
     - **L2 (LOW): one round can exceed the line limit after a long freeze.** The first round after a thaw
       concatenates every queued delivery into one `round` line (`hub.py:494`). Above 65 536 bytes,
       `UnitLinks.send` raises `HubProtocolError`, which is not `HubInvalidRun`. It fails closed, but it is not the
       declared full-buffer residual (AD-12). State it under R-4 or R-7, or split the queue across lines.
     - **L3 (LOW): `arm_timeout_s` does two jobs.** It bounds arming and also the unsettled-stop wait (`finish`,
       `:514`). These are different D-4c quantities: arming happens at start-up, while the stop wait must fit
       Maestro's stop action. Separate them, or record that one value must satisfy both (R-5).
     - **L4 (LOW): the F12 provider's output is unchecked.** `ProposalSets.replace` and `inject` return provider
       messages, which are delivered as is. Nothing checks that they carry no fault identifier or run-kind marker.
       Record this as an obligation of the AD-11/AD-27 provider (R-3), or check the injected message shape against
       the flow's schema at the hub.
     - **L5 (LOW, for increment #5): identifiers must match across the two forms.** The Maestro-form `element`
       values must equal the topology-form unit and flow ids (for example `front-zone-unit` and `f09-radar-vc`).
       Otherwise every entry is refused at the re-check, which is fail-closed. R-2 assigns the domain mapping to #5,
       and the identifier mapping belongs there too.
   - **Residuals R-1 to R-9.**
     - **R-1** is closed on the hub side, and R-2 is assigned.
     - **R-4** is adopted, with M1's ordering fix.
     - **R-3 and R-5 to R-9** are honest.
     - **R-6** (Maestro not authenticated) should be closed in #5, together with the platform's L1 obligation: a
       connected socketpair end given at spawn.
     - **R-8** (the wire test against ST-2) is the gate before any live run.
     - **Proposed addition: R-10.** Lost-flow barrier coverage for relay-held, injected and frozen-queued items (M1).

6. **Dispositions of finding 5 (written at 15:49:27 2026-10-24, before code).** Source: the thesis `decisions.md`
   row "WP-10 #4 review dispositions" (15:48, under the author's delegation, flagged for the author's review),
   relayed by the coordinator.
   - **M1, repair now.** The Lost-flow barrier is applied at one point, the hub's final delivery step (`_deliver`).
     - It covers every item: schedule items, relay-held delays, F12 injections, `stale` replays and frozen-unit
       queues.
     - An item stopped there is not delivered. It is recorded in `HubResult.discarded` (digest only), with the
       reason "after the lost verdict at the final delivery step".
     - Each frozen unit has one ordered queue of control and delivery messages, so a `lost` notice keeps its place.
       After the thaw the queue is replayed in order. A delivery on a flow that was lost while the unit was frozen
       is stopped by the barrier, because the queued delivery is checked again at replay.
     - **Tests.** Delay then loss; an injection after a loss; a loss during a freeze, with the ordering preserved.
     - Residual **R-10** is adopted.
   - **L1, repair now.** Arming refuses any `freeze` when no `SimTimeBound` is configured.
   - **L2, repair now.** The backlog after a thaw is sent in rounds, each within the 64 KiB line limit. The unit
     answers each backlog round, and the step's normal round follows. A single message that alone exceeds the
     limit stays a `HubProtocolError`, as before.
   - **L3, repair now.** `arm_timeout_s` bounds arming only. A new required input `stop_wait_s` bounds the wait at
     an unsettled stop. Both are D-4c values (`NEEDS DATA`), with no default.
   - **L4 and L5** are obligations of other increments: L4 belongs to the F12 provider's owner (AD-11 sets, WP-15),
     and L5 to WP-10 #5, which maps Maestro-form element ids onto topology-form unit and flow ids. Both are recorded
     in the WP-10 #5 design record (thesis `design/wp10-5-wiring.md`). No compat code changes for them.

7. **Repairs of finding 6 (M1, L1, L2 and L3) and the suite re-run (written at 15:53:03 2026-10-24).**
   - **M1, the one Lost-flow barrier** (`hub.py` `_deliver`).
     - Every item reaching the final delivery step is checked against `schedule.lost`. That covers schedule items,
       relay-held delays, F12 injections and replacements, and `stale` replays.
     - A stopped item is not delivered. It is appended to `discarded` (digest only), with the reason "after the lost
       verdict at the final delivery step".
     - **Frozen units.** Each frozen unit has one ordered queue of `("control", lost)` and `("delivery", …)` entries.
       After the thaw, `_replay` sends the queue in order before the step's round, within the round's one deadline
       (N1).
     - **Correction to finding 6.** A delivery queued *before* the lost verdict is not checked again at replay. It
       was already delivered in the hub's record at its step, and it goes out before the `lost` notice, which keeps
       its place. Deliveries after the verdict cannot enter the queue, because the barrier stops them first.
   - **L2, the backlog** (`_replay`).
     - Consecutive queued deliveries go out as `backlog` lines (`{"type": "backlog", "step", "deliveries"}`), each
       within the 64 KiB line limit.
     - A `backlog` line needs no answer, like `origin` and `lost`. The thaw step's own `round` follows with the
       step's deliveries only.
     - A single delivery that alone exceeds the limit still raises `HubProtocolError` at send.
     - **This adds the `backlog` message type to the unit protocol `xverse-compat.hub-units/1`.** No unit-side
       implementation exists yet. The unit runtime (WP-10 #5b) must implement it.
   - **L1.** Arming refuses every `freeze` when no `SimTimeBound` is configured ("a freeze needs a configured
     SimTimeBound").
   - **L3.** `FaultRelay` takes a new required input, `stop_wait_s`, which bounds only the unsettled-stop wait.
     `arm_timeout_s` bounds only arming. Both are required and finite, with no default (D-4c, `NEEDS DATA`).
   - **Tests.** `test_phase8_hub_relay.py` has 50 cases, 6 more than before:
     - **Delay then loss.** No F09 delivery after the verdict, and every held sequence is discarded with digests.
     - **An injection after a loss.** The F12 injection at step 4 is discarded after a loss at step 2.
     - **A loss during a freeze.** The queue replays as `backlog` (the pre-verdict F05 and F06 items), then
       `lost`, then `backlog` (F06 only), then the round.
     - **L1.** A freeze is refused when no bound is configured.
     - **L2.** `_replay` splits 6 deliveries of about 20 KB into lines within the limit, with the `lost` in its
       place.
     - **L3.** A missing `stop_wait_s` is a `TypeError`, and 0 is refused.

     The existing freeze test now expects the queued items as one `backlog` line. The test helper `_relay` defaults
     to the test bound (L1). The hub-core `FakeUnit` records `backlog` lines, as a test-helper addition.
   - **Stability and controls.** The relay and hub-core files gave 101 passed in each of 3 consecutive runs. With
     the barrier disabled, the delay and injection cases fail; the barrier was reverted, and the file is
     byte-identical.
   - **Suite.** The same command as finding 2 gives **585 passed, 39 subtests** (579 + 6), at a load of about 6–9
     (`evidence-wp10-relay-suite-finding7.log`). No CARLA and no live run were used.
   - **Residuals.**
     - **R-10 (adopted, M1) is closed** for every item source at the hub.
     - **New R-11:** the unit runtime must implement the `backlog` message (WP-10 #5b).
     - L4 and L5 belong to the WP-10 #5 design record.
     - R-3 and R-5 to R-9 are unchanged. R-8, the wire test against the platform with ST-2, is the gate before any
       live run.
   - **Status.** Candidate for independent re-review. Not accepted, not merged, not pushed.

8. **Focused re-review of findings 6 and 7 (written at 15:57:28 2026-10-24).** Reviewer: the same independent Claude
   agent as finding 5. Scope: `af63416..cf2d106` (`68c57fe` and `cf2d106`). **Verdict: PASS WITH NOTES.**
   - **Nothing blocks the merge of increment #4.** The merge still needs the author's or the coordinator's
     acceptance, which this finding does not give.
   - **R-8**, the wire test against the platform with ST-2, and **R-11**, `backlog` in the unit runtime, stay the
     gates before any live run.
   - **What was checked, and the result.**
     - **Suite at `cf2d106`, with a clean worktree.** **585 passed, 39 subtests** in 42 s. The relay and hub-core
       files were run once more: 101 passed.
     - **M1, one barrier. Repaired.** `_deliver` checks every item against `schedule.lost` before delivery
       (`hub.py:465`), and records a stopped item in `discarded` with digests only.
       - **Every source passes it:** schedule items, relay-held delays, F12 injections and replacements, and
         `stale` replays all go through `relay.filter` and then `_deliver`.
       - **Frozen units:** a frozen unit's queue is filled only from `_deliver`'s output (`:488`) and from
         `_notify` (`:410`).
       - **Tests:** the delay-then-loss and injection-after-loss cases fail with the barrier disabled, which the
         record states.
     - **The corrected claim of finding 7, against the "Lost-flow rule" and "WP-10 #4 review dispositions" rows.**
       The claim was: deliveries queued before the verdict go out before the `lost` notice, and nothing after the
       verdict enters the queue.
       - **The implementation holds it.** A delivery enters a frozen unit's queue only after it has passed the
         barrier, so before the verdict. The `lost` notice is appended in order. `_replay` sends the queue in that
         order, as `backlog` lines with each `lost` in its place (`:521-544`). Nothing on a lost flow can be
         appended after the verdict.
       - **It matches the rows under the reading that the dispositions row and R-4 imply.**
         - That row puts the barrier at "one point, the hub's final delivery step" and gives frozen units "one
           ordered queue … so a `lost` notice keeps its place".
         - R-4 models a stopped process whose socket buffer still accepts. In that model, data written before the
           verdict is delivered on thaw.
       - **A second reading exists.** The Lost-flow rule says the hub "discards every pending message on that
         flow". Under a wire-time reading, a queued delivery not yet sent to the frozen unit is still pending at the
         verdict, and would have to be discarded. Finding 6 first said exactly that, and finding 7 corrected it.
       - **Assessment.** The record-time reading of finding 7 is consistent with R-4 and with the "keeps its place"
         clause, and it is deterministic.
       - **Recommendation (LOW, editorial; for the thesis note).** Clarify the row: "an item enters a frozen unit's
         queue only through the barrier; queued items are delivered on thaw in order, before any later `lost`
         notice".
     - **The other repairs.**
       - **L1.** Arming refuses every freeze without a `SimTimeBound` ("a freeze needs a configured SimTimeBound").
       - **L2.** The backlog goes out as `backlog` lines within 64 KiB. A single delivery above the limit still
         raises `HubProtocolError`.
       - **L3.** `stop_wait_s` is a separate required input, and `finish` uses it. `arm_timeout_s` now bounds arming
         only.
     - **Against the platform's final ST-2 reading** (`ADR-ML3-SIMTIME-0001` amendment ST-2 at `00bd41ba2`).
       - **Frames.** The `arm` key sets match exactly, with `count` and `index`, and so do those of `resumed`
         (`entry`, `phase`, `step`, `ackSeq`). The hub's batch check (the first `count` equal to the harness list,
         the same `count`, the next `index`) is compatible with the platform's `check_arm_batch`.
       - **R9 replaced by the per-entry M3 rule.** The platform now requires only that `armed` precede any step at
         or after that entry's onset. The relay sends every `armed` before its first tick, which satisfies the rule
         and is stricter. They are compatible.
       - **Benign close.** The hub closes only when settled, with every entry done and `resumed` sent at once
         after each ack. The platform accepts an end-of-file once every entry is final and no `resumed` is
         pending, so the two agree.
   - **New notes (LOW; neither blocks the merge).**
     - **N1. A refused ack: the hub and the ADR disagree.**
       - Platform ST-2 decision 5 requires `resumed` after **every** hold ack, "with any outcome".
       - After a `refused` ack, the relay sends no `resumed`. It ends the run (`hub_relay.py:412`) and closes, so
         the platform then sees an end-of-file with `resumed` pending, which is `XVERSE-FAULT-SIMTIME-PROTOCOL`.
       - Both sides fail closed. For a refused clear, however, the platform's run then ends on a protocol failure
         and not only as `incomplete-clearing`.
       - **Fix.** Align one side: the hub sends `resumed` after a refused ack and then stops, or the ADR exempts
         refused acks. Record the choice for R-8's wire test.
     - **N2. Evidence for a frozen unit's backlog.** `HubResult.deliveries` logs a queued delivery at its enqueue
       step, with `deliveredAtNs` set to that step's boundary. The unit actually receives it at the thaw step, in a
       `backlog` line, and nothing records the replay step. For PAIR-1 and AD-12 analysis, add the replay step
       (`replayedAtStep`) to the record of each backlog delivery, or emit one replay record per `backlog` line.
   - **Residuals.**
     - **R-10** is closed for every item source.
     - **R-11** (`backlog` in the unit runtime, WP-10 #5b) is honest, and is a gate for #5b.
     - **L4 and L5** are recorded as obligations elsewhere, as the dispositions row specifies.
     - **R-3 and R-5 to R-9** are unchanged.
     - **R-8** remains the interoperability gate. It should include N1.

9. **Dispositions of finding 8 (written at 15:58:58 2026-10-24, before code).** Source: the thesis `decisions.md` rows
   "WP-10 #3/#4 re-review notes" and "Lost-flow rule, clarification" (both 15:58, under the author's delegation,
   flagged for the author's review).
   - **N1, align to platform ADR decision 5.**
     - After every hold `ack`, including a `refused` one, the hub's next frame is `resumed`, echoing `ackSeq`.
     - After a refused ack the hub does not step again. It waits for Maestro's `close` within `stop_wait_s`, then
       closes and ends the run as invalid (`HubInvalidRun`). The record notes whether the close was observed.
     - **Test:** a refused apply and a refused clear each give `resumed` with the right `ackSeq`, no later step, and
       the close observed.
     - The R-8 wire test includes this case.
   - **N2.** Each queued delivery replayed after a thaw gets `replayedAtStep` and `replayedAtNs` in its
     `HubResult.deliveries` entry. A delivery that was never queued has neither. **Test:** the replay step equals the
     thaw step for every backlog delivery.
   - **Lost-flow rule, clarification (editorial).** A message that passed the final delivery step before the
     verdict, and sits in a frozen unit's queue, counts as already delivered. It is replayed ahead of the `lost`
     notice. That is the behaviour of finding 7, and no code change follows.
