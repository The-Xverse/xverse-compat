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
