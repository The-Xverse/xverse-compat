# Review log: Thesis Lite Phase 6, P6-T04 (bridge route adapter)

Candidate: `candidate/phase6-bridge-route-20261022` from `xverse-compat` main `ee9db2a`.

Specification (thesis `specs/027-lite-flow-runtime`): contract rule 16 (rev 8b), detailed design
§10 (rev 3a). The platform side is `candidate/flows-lite-20261022` (`review-flows-lite.md`).

1. Opening (2026-10-22). The planned work:
   - `src/xverse_compat/adapters/bridge_route.py`: `BridgeRouteAdapter(flow_id, key,
     sender_domain="bridge-recorder-monotonic")` and a `seconds_to_ns` copy with the platform
     rule.
   - `tests/test_bridge_route.py`: V06, the origin-first refusal, the key filter, a fresh decoder
     without `now`, and a cross-test pinning ten values.

   `bridge_samples.py` stays unchanged. No network session is opened, and CARLA, the bridge and
   zenohd are never executed.

2. Adapter implemented (2026-10-22): `adapters/bridge_route.py` and `tests/test_bridge_route.py`.
   All 6 new tests pass. They cover V06, the origin-first refusal, the decoder value rules without
   its stale or duplicate policy, the key filter, and the cross-test pinning ten values computed
   with the platform `seconds_to_ns` at `flows-lite` `17d4b1c8a`.

   **Cross-repository finding.** The suite gives 90 passed and 1 failed:
   `test_platform_dependency_source_matches_content_lock` fails against the sibling
   `~/xverse-platform` at main `2d556ff24`. The lock (`platform-api.lock.json`, revision
   `744b66f9c`, 26 files, `def80396…`) includes the platform `pyproject.toml`. Phase 5's merge
   changed that file (force-include `xverse.faults`), and Phase 6 changes it again
   (`xverse.flows`). The locked roots `src/xverse_xdl`, `xdl/schemas` and `xdl/profiles` are
   unchanged between `744b66f9c` and `2d556ff24`.

   Consequence: `xverse-compat` main fails this test against platform main since the Phase 5
   merge. Phase 5's acceptance did not run the `xverse-compat` suite.

   Repair order: merge the platform Phase 6 first, then re-pin this lock to the resulting
   platform main, re-run this suite, review, and merge `xverse-compat`.

3. Independent implementation review 1 (2026-10-22): FAIL (platform finding 8). The items that
   concern this repository:
   - **M2:** the V06 claim "They cover V06" was an overclaim. There is no receiver-in-loop test and
     no hand-computed ages.
   - **L6:** the `seconds_to_ns` pins are constants, not a cross-test.

   Repair: the test environment gets the candidate platform wheel. The V06 test then feeds the
   adapter's items through `xverse.flows.FlowReceiver` with hand-computed ages, a deadline check
   and a final poll, and the pins compare directly against `xverse.flows.seconds_to_ns`.
