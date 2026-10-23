# Contract note: `xverse-compat.carla-items/2` (Phase 7 successor; candidate)

Status: CANDIDATE. It is not accepted, and it is not part of the accepted Phase 4b contract
(thesis `specs/028-lite-carla-client-adapters/contracts/item-protocol.md`, protocol 1).

Protocol 2 is protocol 1 with the following differences:

1. **Transport.** One Unix stream socket instead of the standard streams. The platform side
   (`SocketAdapterLink`) listens and creates the socket with mode 0600 under umask 0177. The adapter connects
   with `--connect unix:<path>`, retrying until `--connect-timeout-s`. Messages, the line limit and the strict
   UTF-8 decoding per line are unchanged.
2. **Handshake.** `hello.protocol` is `xverse-compat.carla-items/2`.
3. **Command.** `{type: command, commandId, brake, throttle, deadlineFrames}`, with `throttle` required and in
   [0, 1]; otherwise the refusal is `COMMAND`. The live actuation is
   `VehicleControl(throttle, brake, steer=0)`. Steering and the reverse gear are not carried. The echo check is
   still on `brake`, and an echo is not braking evidence.
4. **Owned scenario (live, optional).** `--source live:<host>:<port>:scenario --scenario <file>`. The adapter
   spawns the declared ego vehicle and sensors with `role_name` `xverse-lite-*`. It ticks once before binding,
   so it is the only tick owner, actuator writer and actor owner. At close it holds the ego with throttle 0,
   brake 1 and the hand brake, stops the sensors, destroys its actors, restores the saved settings and commits
   them with one tick. A bound (non-scenario) vehicle is released to neutral at close.
5. **Unit options.** These are entry-point options, not protocol messages:
   - `--carla-site <dir>` adds the pinned environment's site-packages when the unit runs on the plain
     interpreter.
   - `--linger` keeps the process alive after a successful end, so Maestro sees a healthy unit until its stop
     step; after a failure the process exits.
   - `--marker <file>` writes the exit code, which Maestro collects.
   - `--stderr <file>` redirects diagnostics, because Maestro gives units `/dev/null` streams.
   - In live mode the CARLA client timeout is 5 s.
6. **Termination.** The exit codes stay 0, 2 and 3. Only exit 2 is bound to a single stderr line.

Protocol 1 over stdio is unchanged on the wire. Its live path gains the 5 s client timeout, the commit tick and
the control release at close.
