# Hub frame trace (WP-17f candidate)

`HubResult.frame_trace()` returns a private, JSON-safe copy of observational records with schema
`xverse-compat.hub-frame-trace/1`. It supplies inputs to the future offline oracle join and D-4c timing
extractor. It does not perform either analysis or classify a scientific run. No live CARLA run, timing
bound, runtime fitness input, protocol freeze or WP-10 #5 wiring is supplied by this increment.

The export has `schema`, `episodeOrigin`, `loopOutcome`, `failureType` and `records` members.
`episodeOrigin` is null until the first simulator boundary is registered. Thereafter it contains that
boundary's `motionFrame`, `tickedFrame`, absolute `simNs` and `frameIssues`, including when origin binding
subsequently raises. Missing or mismatched first-frame identity stays at the origin; a later good frame
does not replace it. `loopOutcome` is `not-started`, `running`, `returned` or `raised`. `failureType` is
the exception class name when raised, otherwise null; arbitrary exception messages are not recorded.
These describe hub execution, not experimental acceptance.

There is one record per attempted adapter tick, including terminal, missing-boundary and partial
attempts. The fields are:

| Member | Meaning |
| --- | --- |
| `tick` | Request ordinal, never a CARLA frame or join key. |
| `step` | Existing schedule's registered boundary index, or null if no registration completed. |
| `motionFrame` | Actual `vehicle-motion` item's nonnegative integer `frame`, or null. |
| `tickedFrame` | Actual adapter `status:ticked` frame, or null. |
| `simNs` | Actual motion item's nonnegative integer `originNs`, or null. |
| `episodeNs` | Observed `simNs` minus the existing bound simulator origin, when both are known; otherwise null. |
| `hostNs` | Host monotonic nanoseconds sampled immediately after `link.tick()` returns, or null if it did not return. |
| `priorMotionFrame` | Previous observed nonnegative integer motion frame, if any. |
| `frameIssues` | Explicit identity/time/gap diagnostics, described below. |
| `phase` | Last reached loop phase; useful when a partial attempt aborts. |
| `status` | `pending`, `completed`, `no-boundary`, `adapter-done` or `aborted`. |
| `failureType` | Exception class name for an aborted attempt, otherwise null. |

`completed` means that the existing loop body finished and incremented `HubResult.steps`. It does not
mean that frame identity or the scientific run is valid. `no-boundary` retains a returned adapter tick
without a motion item, without inventing a step, motion frame or simulator stamp. `adapter-done` is a
terminal response, with `not-a-boundary` in `frameIssues`. An exception before tick return leaves an
`aborted` row with unknown frame/time fields; an exception after observation preserves the known fields.
A Maestro close records an aborted unfinished step and the existing `maestro-closed` end reason; the
hub may return normally. A cleanup or final relay exception can mark the loop raised after its last
step completed. Inspect both loop and row status. Cleanup and original exceptions still propagate.

Frame issues are `boundary-not-observed` before an observation; `missing-ticked-frame` or
`invalid-ticked-frame`; `no-motion-boundary`; `missing-motion-frame` or `invalid-motion-frame`;
`missing-motion-time` or `invalid-motion-time`; `ambiguous-motion-items`; `motion-ticked-mismatch`;
`non-increasing-motion-frame`; `motion-frame-gap`; and the terminal `not-a-boundary`. Invalid includes
booleans and negative or noninteger identities. No invalid raw value enters this export. A frame gap
is diagnosed against the preceding actual observed motion frame; absent boundaries are never filled.
Existing runtime validation and no-motion diagnostics remain authoritative for their existing purposes.

The offline join must use actual CARLA motion frame identities, check the episode origin against the
observer's episode, and treat missing/invalid/ambiguous/mismatched origin or row evidence and frame gaps
as explicit join gaps. An empty issue list alone does not certify observer coverage, provenance, run
validity or membership in a frozen protocol. Never join by `tick`, `step`, observer host time or an
assumed fixed frame increment; never interpolate a missing frame. This increment supplies evidence,
not a join implementation or a validity decision.

The host sample is taken immediately after the adapter response returns, before boundary registration,
origin binding, relay holds, frame verification, consumers/producers and delivery rounds. For consecutive
observed motion boundaries, subtracting successive `hostNs` includes the earlier boundary's binding,
holds, verification, delivery work and the next command/adapter tick/socket wait. Initial unit connection
and fault arming precede the first sample and are excluded. This is not pure CARLA computation time or a
simulator deadline. The last boundary has no invented duration to a nonexistent next boundary, and the
terminal response is not a motion boundary. The later D-4c extractor must select the admitted fault-free
and message-only valid traces, handle gaps/aborts and keep handshake treatment separate. This change
chooses no bound and does not measure D-4c.

The host values and all join metadata are never consulted by runtime decisions. Command/tick order,
actuator and tick ownership, delivery scheduling, simulator clocks, deadlines, fault holds, adapter
protocol, Phase 7 path and rc.1 inputs are unchanged. The export contains no pixels or observer ground
truth. Persist it explicitly with `json.dump(result.frame_trace(), stream, allow_nan=False)`; this API
does not open files or publish artifacts automatically. After an exception, use `hub.result.frame_trace()`.
