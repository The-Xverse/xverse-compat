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

4. Repairs (2026-10-22). M2: `test_v06_adapter_items_through_the_platform_receiver_with_hand_computed_ages`
   (hand-computed ages and deadline events through `xverse.flows.FlowReceiver`). L6: the
   `seconds_to_ns` pins are compared live with the platform function. The test environment is
   `/dev/shm/compat-p6-venv`, which holds the candidate platform wheel. Result: 16/16
   `test_bridge_route.py`. The full suite gives 90 passed and 1 failed (the content lock awaiting
   the post-merge re-pin, finding 2).

5. Re-pin after the platform Phase 6 merge (2026-10-22). Platform main is now `8b3d8c8e8` (Phase 6
   accepted and pushed, platform finding 15). The content lock still pins `744b66f9c`
   (`def80396…`), so `test_platform_dependency_source_matches_content_lock` fails, as recorded in
   finding 2.

   Planned repair, following the Phase 4 practice:
   1. Run `scripts/admit_phase4.py --platform-main 8b3d8c8e8` with an interim log; this rebuilds the
      admission record and re-pins `platform-api.lock.json`.
   2. Run the full owner suite.
   3. Rebuild the record with the passing log and the review and acceptance fields.

   Nothing in the platform or in any legacy repository is executed.

6. Independent review of the re-pin (2026-10-22): **PASS**.
   - The recomputed `platform_tree_digest` of the sibling platform at `8b3d8c8e8` is
     (26, `2696645d…`), equal to the lock.
   - The only change in the locked surface between `744b66f9c` and `8b3d8c8e8` is `pyproject.toml`
     (the faults and flows force-includes).
   - The admission diff is limited to the platform, verification, lock and timestamp fields;
     execution authority stays absent, and pins, descriptors, contracts and blockers are unchanged.
   - The adapter code is unchanged since `932f251`.

   Findings: MEDIUM, the interim verification block (log a, "passed 90" against 91 in the log,
   pre-re-pin) must not be committed; LOW, the rebuild must supply the Phase 6 review and
   acceptance flags; LOW, log b lacks a command header.

7. **Acceptance decision, Phase 6 `xverse-compat` delivery (P6-T04), recorded before merge**
   (2026-10-22).
   - **Basis:** the author's goal and delegation (thesis `delegated-decisions-20261022.md`), and the
     platform acceptance (platform finding 15, main `8b3d8c8e8`).
   - **Evidence:** the adapter, reviewed in platform reviews 1 (FAIL, repaired) and 2 (PASS);
     findings 3–4 here; the re-pin review PASS (6); the owner suite 92 passed against platform
     main `8b3d8c8e8`.
   - **Decision:** rebuild the admission record with the passing log and these review and
     acceptance fields, rerun the suite once on the final record, then merge `--no-ff` into
     `xverse-compat` main and push.
   - **Limits:** recorded samples only, no network session, and CARLA, the bridge and zenohd are
     never executed. The bridge age excludes publication latency (D6-3). G1–G6 are unchanged
     except where Phase 4b changes them.
