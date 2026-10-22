# Review log: Thesis Lite Phase 4b (CARLA client adapters)

Candidate: `candidate/phase4b-carla-client-20261022` from `xverse-compat` main `39ae980`.

Specification (thesis `specs/028-lite-carla-client-adapters`): planning rev 5a (five planning
reviews; environment location amended to loop10) and detailed design rev 1 (under review).

Decisions: DLG-1 (pinned `carla 0.9.15` cp310 client, out of process) and DLG-2 (owned adapters,
bridge unchanged). CARLA, the bridge and zenohd are never executed; there is no live session. Every
log edit is committed immediately.

1. Opening (2026-10-22). P4b-T01 first: `tools/carla/make-client-env.sh` creates the pinned
   environment on loop10 and writes `env-record.json`. Then P4b-T02–T05 follow the detailed design
   once its review passes.
