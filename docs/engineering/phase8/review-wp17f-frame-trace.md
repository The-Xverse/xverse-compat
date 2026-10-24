# WP-17f compat increment: observed hub frame/host-time trace

Candidate `candidate/phase8-wp17f-frames-20261024`, from compat main
`4172f6151cab34cc8fd196a6d3bbf68fc53af2d4`. This is the accepted small compat part of WP-17f (DN-5), separate
from WP-10 #5 wiring. Offline engineering only; no live CARLA, characterisation run, scientific value, acceptance,
merge or release change is created here. The author's modified main-checkout AGENTS.md and the midnight rc.1 soak
inputs are preserved. Sol at high reasoning is the recommended implementation/review profile for this contract work.

## Finding 1: source gap and implementation design before code (2026-10-24)

Inputs: thesis `specs/002-assured-aeb/design/wp17-support.md` S-3, S-11, O-4 and DN-4/DN-5; accepted decisions
WP-17 DN-1 to DN-9; compat `live/hub.py`, `carla_client.TickResult`/`SocketAdapterLink`, and the adapter's real
`ItemBuilder`/motion item protocol. Main/upstream were freshly fetched and both equal `4172f61`.
The thesis canonical note remains the fully read parent-session blob `ba244ddb7df388386455524ab7667d4a1e86d5a3`.

### Observed source gap

HubResult records the simulator episode origin in nanoseconds but no CARLA origin frame or per-boundary host sample.
Hub.run registers a boundary from the first vehicle-motion item's `originNs`; the real motion item carries its actual
CARLA `frame`, and TickResult.frame carries the adapter's `status:ticked` frame. These are independent observations,
not loop-counter frame identities. The original no-motion boundary-gap record is retained unchanged.

### Record and timing contract

Add only observational fields to HubResult and a JSON-safe, private-copy `frame_trace()` export with schema
`xverse-compat.hub-frame-trace/1`. It records the first registered boundary's actual motion frame, ticked frame,
existing absolute simulator origin and frame-quality issues. No later good frame can substitute for a missing or
mismatched origin observation.

Keep one record for each attempted adapter tick, including normal terminal/no-boundary attempts and aborted partial
steps. Members: tick (request ordinal only), registered step or null, actual motionFrame/tickedFrame or null,
absolute simNs or null, actual episode-relative ns or null, hostNs or null, prior observed motion frame, frameIssues,
phase, completion status and exception type when relevant. Never derive a frame number or missing simulator stamp
from tick/step, another sensor, a fixed grid or interpolation. Missing/invalid/ambiguous motion frames, motion/ticked
frame mismatch, missing ticked frame, non-increasing motion frames and actual frame-number gaps remain explicit.
These flags affect offline join eligibility only; they do not add runtime decisions, lost verdicts or retries.

Sample `time.monotonic_ns()` immediately after `link.tick()` returns, before origin binding, fault-relay holds,
frame verification, local consumers/producers and delivery rounds. It is evidence only and never feeds a runtime
condition, deadline, command, delivery or grid. For consecutive actual motion boundaries, the host-time difference
includes the preceding boundary's binding/hold/verification/round work and the next command/tick/link wait; it
excludes initial unit connection/arming before the first sample. It is not pure CARLA compute time, not a simulator
latency declaration, and not a scientific deadline. A last boundary has no invented next-boundary duration.
D-4c selection of fault-free/message-only valid traces and timing extraction remains the later harness's work.

Append an attempt before commands, with unknown fields until observed, so an exception before tick completion leaves
an explicit aborted attempt without a fake step/frame/host boundary. Once a boundary is observed, preserve the record
if binding, relay, verification, consumers, rounds or deadline checks raise. Record a normal Maestro close as an
aborted unfinished step rather than a completed step. Keep loop return/raise status separate from individual step
completion and from scientific validity. Cleanup exceptions remain raised with evidence marked accordingly.

### Scope and verification

Keep existing command order, schedule.boundary inputs, simulator origin/grid, deliveries, deadlines and cleanup
ownership. Add no adapter command, clock owner, actuator writer, runtime-message member or runtime output consumer.
Do not change Phase 7's loop, the CARLA adapter protocol, rc.1 source pins, retry policy or numeric timing bounds.
The evidence contains no pixels, observer ground truth or arbitrary exception payload; exception type is sufficient.

Meaningful tests use fake links with actual nonzero frame identities and existing real Unix-socket unit fixtures.
Cover normal trace/serialization/private copies, missing or mismatched frame identity, actual frame gaps, origin
mismatch evidence, partial step and pre-boundary exceptions, normal done/no-motion cases, and host sampling before
holds. Preserve commands, deliveries and schedule inputs under the same fixtures. A socket-adapter fake-source check
will assert actual item/status frames; no live CARLA is involved. The full owning suite and independent review remain
required. The platform regression owns the heavy-test slot: syntax and tiny stdlib probes only until released.
SADS/P8-T06 disposition stays partial: this supplies join inputs, not observer coverage, the oracle, a completed join,
D-4c measurements, runtime fitness or H1–H4 evidence.

## Finding 2: implementation candidate and deferred validation (2026-10-24)

Implemented after design checkpoint `6da575015dd26d92360ab6b2a8e55b38cb11d0ed`.
`live/hub.py` adds the private-copy `HubResult.frame_trace()` export, origin identity, actual motion/ticked
frame observations, host samples and attempted-step completion/failure records. The original schedule inputs,
no-motion gap dictionaries, commands, delivery/hold order and cleanup calls are preserved. No adapter protocol,
Phase 7 source or release input changes. `hub-frame-trace.md` documents all members/issues, exact sampling point,
host-difference meaning, explicit offline gap treatment and the boundary between loop completion and run validity.

`test_phase8_hub_frames.py` adds fake-link regressions for actual nonzero identities, private JSON export, actual
gaps/regressions, missing/invalid/mismatched/ambiguous origins, no-motion ticks, pre-return and post-boundary
exceptions, rejected simulator boundaries and sampling before a relay hold. Its real Unix-socket unit case checks
unchanged commands and delivery membership. The existing end-to-end socket-adapter fake-source case additionally
checks actual item/status frames 100..103, episode time and serialized observations; it does not start live CARLA.
All fixture frames, timestamps and bounds are TEST-ONLY.

Checks performed: AST parsing of the three changed Python files; `git diff --check`; a tiny stdlib probe using
three real listener lifecycle traces (normal, missing motion and pre-return exception), private-copy/JSON exports
and four diagnostic controls (frame mismatch/gap/regression and boolean identity). All passed. No pytest, pinned
adapter process or real remote unit threads were run in this pass. The platform full run still owns that slot.

Queued validation after slot release: focused `tests/live/test_phase8_hub_frames.py` and
`tests/live/test_phase8_hub.py`, then the owning complete compat suite under the admitted test environment.
Suggested focused command from this worktree (preserving the real UID for `/run/user/<uid>` sockets):

```sh
unshare -cn env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src /dev/shm/compat-p6-venv/bin/python -B -m pytest tests/live/test_phase8_hub_frames.py tests/live/test_phase8_hub.py -q -p no:cacheprovider --tb=short
```

Status: implementation candidate pending independent review and queued suites; no acceptance, merge, live run or
scientific measurement. Offline oracle join/extractor and observer-origin verification remain future WP-17f work.

## Independent source review (Codex coordinator, 2026-10-24), PASS for scheduled verification

Reviewed exact57ef514fd17dbdb9a6423d66fbd89e72485ec497 against4172f61: actual motion/ticked identities,
immutable export, origin preservation, gaps, aborted boundaries, host sampling before binding/holds/delivery,
normal/exceptional cleanup and genuine socket regression coverage. The metadata never feeds runtime decisions.
No source blocker found. Initial connection/arming and final nonexistent successor interval are explicitly excluded;
frame/episode membership still requires the future offline join. Full compiled/runtime/scientific claims remain
unproven. No CARLA/pytest/adapter process was executed in this read-only pass.

Assemble with accepted compat mainc7f92eb (training/sensor tools, independent605passed/2network-refusal-skips/39subtests)
and run the complete owning suite with all environments available and namespace isolation. The independent host
refusal controls already cover those namespace-only skips. Candidate remains unaccepted until that result.

## Owning-suite finding and TEST-ONLY relay fixture repair design (Codex, 2026-10-24)

Exact assembled4e61adf48a3349bb2a857d7d50c44ddc0138027a gives1failed,620passed,2host-network-
refusal skips,39subtests in72.59s. Full log/receipt: thesisreview/codex-hub-verification-20261024/hub-frame-trace/.
The new host-sampling control's fakeRelay supplies arm/at_step/finish but omits the preexistingfilter(step,due)
method called by Hub._rounds. This raisesAttributeError after the observation and before assertions; no product
error is demonstrated. The fake must represent the unchanged no-message-fault relay seam completely.

Repair design, before code: add only identityfilter(step,due) to that TEST-ONLY fake, retaining host advancement
and hold assertions, genuine hub loop and expected simulator times. No product/control/clock change. Repeat the
exact test and full owning suite. Another reviewer must inspect the test-only delta before acceptance. No acceptance
or merge follows the failing run; retain its evidence.
