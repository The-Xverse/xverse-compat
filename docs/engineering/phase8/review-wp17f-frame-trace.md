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
