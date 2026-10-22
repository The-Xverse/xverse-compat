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

2. P4b-T01 first attempt (2026-10-22). The environment was created on loop10 (195 MB) and the
   pinned wheel was verified and installed with `--no-deps`. The offline `import carla` aborted
   (rc 134): `std::logic_error: basic_string::_M_construct null not valid`. Under `env -i` the
   variable `HOME` is unset, and the CARLA extension evidently builds a `std::string` from it at
   import.

   With `HOME=/nonexistent-carla-home` (a deliberately absent directory, so no user configuration
   can be read), the import succeeds: version `0.9.15`, `carla.Client` present.

   Repair (recorded before the change):
   - The script and every adapter launch use
     `env -i PATH=/usr/bin HOME=/nonexistent-carla-home … -s`.
   - The thesis contract rule 5 and FR-001a launch command are amended accordingly. This is an
     engineering amendment under the author's delegation.
   - The script recreates the environment it created in the first attempt.
