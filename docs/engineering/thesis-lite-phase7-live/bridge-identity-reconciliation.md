# Bridge identity reconciliation (2026-10-23, read-only git and sha256 only)

| | Phase 4 selected bridge | Running virtual-vehicle bridge (author baseline 2026-10-22 23:21) |
| --- | --- | --- |
| Checkout | /home/jefferson/carla-simulator-bridge | /home/jefferson/autoverse/bridges/carla (installed copies in ~/carla-api/PythonAPI/examples) |
| Revision | eef3f71 (1 dirty file: examples/manual_control_steeringwheel_zenoh.py, dated 2025-10-25) | b10e6d8 (clean) |
| Ancestry | eef3f71 is NOT an ancestor of b10e6d8; merge-base 6136ce2; they are divergent lines | |
| Vehicle program | examples/automatic_control_zenoh.py (sha256 37b6b6be6ac84347..., identical in both trees): own agent drives the ego | examples/virtual_vehicle.py (sha256 c95f11e115119efc..., absent at eef3f71; installed copy identical): applies VCU throttle/brake/steer commands |
| Speed output | zenoh key ego_vehicle/speed, payload int km/h text | vehicle/status/velocity_status, float km/h text |
| Clock output | none | vehicle/status/clock_status, absolute World elapsed_seconds (signals_config.json declares "delta ms": contract text and code differ) |
| Actuation input | none (internal agent) | vcu/control/throttle_cmd, vcu/control/brake_cmd [0,1], vehicle/command/steer_sts, vcu/control/reverse_sts |
| Spawn | per its agent | random spawn point (random.choice), rolename ego_vehicle, filter vehicle.audi.etron |
| Throttle mapping | n/a | applied throttle = VCU throttle_cmd / THROTTLE_DAMPING_FACTOR (1.2) (review 1 R-3/R-4) |

Conclusion: the two bridges are different programs with different topic contracts and are not interchangeable.
The Phase 4 selection record (xverse-compat aeb-sim-selection.json) still names only the eef3f71 speed feed.
The Phase 7 live integration targets the running virtual-vehicle contract (b10e6d8): the Lite driver
publishes velocity_status (km/h) and clock_status (absolute elapsed seconds) from runtime motion items and
consumes the same VCU command topics, and the baseline runs b10e6d8's virtual_vehicle.py. It does NOT
reproduce the legacy throttle damping (/1.2): the Lite adapter applies the VCU command undamped (correction
after review 1 R-4). A successor selection record for the
b10e6d8 contract is a recommended follow-up; it is not made here.
