# Review log: Phase 8 WP-13 increment #4a, the U2/U3 sensor numpy venv (xverse-compat)

**Candidate.** `candidate/phase8-wp13-sensor-venv-20261024`, from main `34b514d` (WP-09 #2 merged).

**Specification.**
- Thesis `specs/002-assured-aeb/design/wp13-logic-ml-binding.md` §5 (DRAFT; §9 R-7 decided).
- The `decisions.md` rows:
  - "U2/U3 numpy": a pinned numpy 2.5.4 venv for U2 and U3 under WP-13, built from the U4 wheelhouse, with no new
    download. The standard-library image operations stay as test references.
  - "WP-09 #3 unit isolation" R-1: units run `-S -s -B` with `PYTHONDONTWRITEBYTECODE=1`.
  - "WP-13 R-1 to R-7" R-7: the numpy port is used only if it is bit-exact.

**The companion blueprints increment.** `candidate/phase8-wp13-imageops-np-20261024` holds the numpy port and its
bit-exact tests (blueprints `docs/review-wp13-imageops-np.md`).

**Scope.**
- No download: the only wheel is already in the U4 wheelhouse.
- The build runs inside `unshare -rn`.
- No CARLA, Maestro or unit is started. No other venv is touched.
- The soak's loop10 paths are never touched: `.x-verse-build/cache/xverse-lite-live-20261022` and
  `.x-verse-build/worktrees/*` are neither read nor written.
- The only loop10 path read is the U4 wheelhouse, read-only.
- This is engineering evidence only.

## Findings

1. **Design record (2026-10-24 15:56:47, before any code or build).**
   - **Lock** (`tools/sensor/u2u3-sensor.lock`).
     - Exactly one requirement: `numpy==2.5.4 --hash=sha256:6ffa0766…62c0`, byte-identical to the numpy line of
       `tools/inference/u4-inference.lock`.
     - A test asserts this equality, so the two pins cannot drift apart.
     - The wheel `numpy-2.5.4-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` in
       `.x-verse-build/cache/xverse-aeb-inference-wheels-20261024/` has that SHA-256 (checked read-only
       before this record: `6ffa07666f8da0eef81d149934a626d0d95fbd6838432a33e66245423a9062c0`).
   - **Build script.** `tools/sensor/make-sensor-env.sh [--record-only] <envdir> <wheeldir> <lock> <record-out>`,
     on the WP-09 #3 `make-training-env.sh` pattern:
     1. **Refusals:**
        - unless no non-loopback interface is visible in `/proc/self/net/dev` (run it inside `unshare -rn`);
        - below 2 GB free;
        - if `<envdir>` exists (with `--record-only`, unless it exists);
        - if a locked wheel is missing or differs from its lock hash.
     2. **Creation and install:**
        - `env -i PATH=/usr/bin HOME=/nonexistent-sensor-home PYTHONDONTWRITEBYTECODE=1` for every step;
        - the pyenv CPython 3.13.13 interpreter, the U4 one, creates the venv with `-m venv --without-pip`;
        - that interpreter's own pip installs with `--python <venv> --no-index --find-links <wheeldir>
          --require-hashes --no-deps --no-compile -r <lock>`.

        The wheelhouse also holds onnxruntime. Only the locked numpy is installed: the lock is the only requirement
        list, and `--no-deps` is set.
     3. **Import check in the unit pattern:** the real interpreter with `-S -s -B`, `PYTHONPATH` to site-packages,
        and `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1`. It prints the numpy version.
     4. `pip freeze --all`. **The bytecode check then comes after every step that runs an interpreter on the venv**
        (R-9 ordering): it refuses any `__pycache__` or `.pyc`.
     5. **A JSON identity record**, `xverse-compat.sensor-env-record/1`, written by the training script's code:
        - lock hash and repository path;
        - the hash and size of every wheelhouse file;
        - `installed`;
        - the site-packages and venv tree digests;
        - interpreter, `libpython` and stdlib digests;
        - installer pip and the base `.pth` hooks;
        - network interfaces, glibc, CPU, the import result and the size.
   - **Location of the build in this increment.**
     - **`/dev/shm/xverse-aeb-sensor-20261024/`, not loop10.** Today loop10 is 98% full (31 GB free) with the soak
       armed for 00:00, and the bit-exact verification does not need the build on loop10.
     - The build for unit use, `.x-verse-build/cache/xverse-aeb-sensor-20261024/` next to the U4 venv (design §5), is
       the same command with that `<envdir>`. **It is not run here.** It is recorded as a deployment step for the
       run-command increment (WP-10 #5) or a separate go-ahead.
     - The venv is not relocatable, so the loop10 build gets its own identity record.
   - **Tests** (`tests/sensor/test_sensor_env.py`):
     - the lock is one hashed requirement, identical to the U4 numpy line;
     - `bash -n` on the script, and the script contains the required flags (`--no-index`, `--require-hashes`,
       `--no-deps`, `--no-compile`, `--without-pip`, `-S -s -B`, `PYTHONDONTWRITEBYTECODE=1`, and the network
       refusal);
     - **when `XVERSE_COMPAT_SENSOR_ENV` names a built env, otherwise skipped:**
       - the identity record matches the lock and the venv on disk;
       - there is no bytecode;
       - `installed == ["numpy==2.5.4"]`;
       - an import in the unit pattern (`-S -s -B`) shows numpy 2.5.4 loaded from the venv and nothing from the base
         site-packages.
   - **Expected residuals:**
     - the loop10 build (above);
     - the U2/U3 unit command templates (`-S -s -B`, `PYTHONPATH` order) belong to the unit-entry increments
       (WP-10 #5, WP-13 #6);
     - `libm` reproducibility of the noise tables is unchanged: those tables are computed by the standard-library
       code in both implementations.

2. **Implementation and verification build (2026-10-24 15:59:35; code commit `b395644`).**
   - **Files:**
     - `tools/sensor/u2u3-sensor.lock`: the comment header plus the U4 numpy line, appended from
       `tools/inference/u4-inference.lock` by `grep`;
     - `tools/sensor/make-sensor-env.sh`: the WP-09 #3 script body, with only these changes (checked by `diff`):
       - the home directory name;
       - the import probe (numpy version, numpy file, and `site` not imported);
       - the record schema `xverse-compat.sensor-env-record/1`;
       - comments;
     - `tests/sensor/test_sensor_env.py`: five tests.
   - **Build** (15:57:36):
     - command: `unshare -rn bash tools/sensor/make-sensor-env.sh /dev/shm/xverse-aeb-sensor-20261024
       <U4 wheelhouse> tools/sensor/u2u3-sensor.lock <record>`;
     - result: `import=0`, 57 384 KiB, about 3 s;
     - `installed` is `["numpy==2.5.4"]`, and onnxruntime was not installed although its wheel is in the wheelhouse;
     - there is no pip in the venv and no bytecode;
     - the import output is `numpy 2.5.4`, with the file under the venv's site-packages and `noSite True`;
     - `networkInterfaces` is `["lo"]`.
   - **Identity record.** It was regenerated with `--record-only`, inside `unshare -rn`, after the code commit, so it
     binds `repositoryRevision` `b395644`.
     - Its `venvTree` (940 entries, `3bdb8172…5894`) and its `sitePackagesTree` (928 entries) equal the first build's
       record.
     - The record file is `/dev/shm/xverse-aeb-sensor-20261024/identity.json`, SHA-256 `4451e9cc…7a91`.
   - **Refusal outside the namespace.** The script was run once outside `unshare -rn`, with a scratch `<envdir>`. It
     refused with exit 6 and listed the host interfaces. Nothing was created. The test
     `test_wp13_script_refuses_with_a_visible_network` covers this.
   - **Commands:**
     - `tests/sensor` with `XVERSE_COMPAT_SENSOR_ENV` set: 5 passed;
     - `tests/sensor` without it: 3 passed, 2 skipped;
     - the whole suite (`env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src /dev/shm/compat-p6-venv/bin/python -B -m
       pytest tests -q -p no:cacheprovider`, with `XVERSE_COMPAT_SENSOR_ENV` set): 540 passed, 39 subtests passed;
     - `__pycache__` removed.
   - **Loop10.** The only loop10 path touched was the U4 wheelhouse, read-only. Nothing on loop10 was written, and the
     soak's paths were not touched.
   - **Residuals:**
     1. The build for unit use in `.x-verse-build/cache/xverse-aeb-sensor-20261024/` is the same command and is **not
        run**. It needs a go-ahead, after the soak or with the run-command increment.
     2. The `/dev/shm` build disappears at reboot. It exists for the blueprints bit-exact tests only.
     3. The U2/U3 unit command templates (`-S -s -B`, `PYTHONPATH` to this site-packages first) belong to the
        unit-entry increments.
     4. The script duplicates the WP-09 #3 script body. A shared helper would remove the duplication, but would touch
        two reviewed scripts, so it is not done here.
   - **Status.** Candidate only. The independent review, acceptance and the merge are pending.

3. **Independent read-only review by Codex (2026-10-24), PASS WITH NOTES.**
   - **Input.** Candidate `efd5b6a9330b1b32bf4acaf91b60e0885a107c4d` (product `b395644`), the entire change from
     `34b514d`, the WP-13 design §5, the decided "U2/U3 numpy" and "WP-09 #3 unit isolation" rows, and findings 1–2.
     No product repair was made. The NumPy port is a separate blueprints increment; its acceptance does not substitute
     for this environment review.
   - **Lock and install:** the sole requirement is byte-identical to the U4 numpy 2.5.4 line and uses the same SHA-256.
     The script admits exactly one matching wheel per requirement and installs only the lock under `--no-index
     --require-hashes --no-deps --no-compile`, into a venv created without pip. The other files in the reused U4
     wheelhouse are provenance inventory, not extra install requirements.
   - **Isolation and provenance:** the import uses the real CPython 3.13.13 with `-S -s -B`, an explicit site path,
     bytecode disabled, and fixed NumPy thread settings. The network refusal precedes creation/import. Freeze runs
     before the bytecode check. The identity schema records lock/wheels, interpreter and runtime library, the
     environment trees, installing pip and base `.pth` hooks, with those host hooks explicitly outside unit imports.
     `--record-only` does not install or rebuild the existing venv.
   - **Checks performed independently now:** `bash -n tools/sensor/make-sensor-env.sh`, Python AST parsing of
     `tests/sensor/test_sensor_env.py`, and `git diff --check`; all pass. Exercised the script's early network refusal
     on this host using `--record-only` and deliberately nonexistent environment/wheel paths: **exit 6** with the
     expected refusal diagnostic and **no record created**. This did not reach a NumPy import or touch a venv.
   - Read the existing `/dev/shm/xverse-aeb-sensor-20261024/identity.json` without rewriting it. Its lock hash matches
     this candidate, and every small recorded `.pth` hash matches the current file. It records schema
     `xverse-compat.sensor-env-record/1`, import return code 0, interfaces `["lo"]`, only `numpy==2.5.4` installed,
     and repository revision `b39564466674b9a2ff2de1f778cc4dda38b67e62`. This is an inspection of the existing
     identity metadata, not a new import or whole-tree rehash.
   - **Verification explicitly deferred:** no pytest, NumPy/torch/ONNX Runtime import, full wheel/environment rehash,
     venv build or live run was performed while the platform full regression is active. Finding 2's **5 sensor tests**,
     **540 full-suite tests / 39 subtests**, and no-venv skips remain its recorded evidence. After assembling with
     current compat main, run `tests/sensor` and the complete owning suite on the quiet host with
     `XVERSE_COMPAT_SENSOR_ENV=/dev/shm/xverse-aeb-sensor-20261024`; the two environment tests must execute and recheck
     their tree/import evidence, rather than silently skip. The separate NumPy-port equivalence probe must continue
     using this exact NumPy pin.
   - **Carried:** finding 2 residuals 1–4, especially the unbuilt durable loop10 environment, its distinct identity at
     that build path, and the U2/U3 command/evidence selection. The unit-entry increment must declare its thread
     settings consistently with this verification environment; no per-frame D-4c budget is inferred.
   - No issue requiring a source repair was found. This finding is **not acceptance, a merge, a push, approval to
     build the loop10 cache now, a unit-launch result or a scientific claim**. The next step is the coordinator's
     acceptance/assembly decision, followed by the deferred assembled-suite verification when the host is available.

## Delegated engineering acceptance for isolated main assembly (Codex, 2026-10-24)

Independent re-review findings above and the now-completed source-bound owning suite support acceptance under the author's recorded engineering delegation, flagged for author review. Reviewed revision `f09e5181c6b6e637ad80ea8e4d619eb1366aa381`; actual full-suite result: **598 passed, 1 skipped, 39 subtests passed in 34.59s**. Evidence is the thesis-owned `specs/002-assured-aeb/review/codex-serial-verification-20261024/sensor-environment/receipt.json` and companion `pytest.log` (SHA-256 `52c43da6800f8feef46ac83ca82b53ad8181d4461bf4eb579ad536f7bc572954`). No failed, missing or skipped required behavior is treated as a pass.

Scope: Pinned sensor environment mechanism only. The only full-suite skip is host-network refusal, separately independently exercised on host with exit6/no record (finding3). Durable loop10 cache and unit-entry thread settings remain pending. All previously carried review limits remain. Assemble only accepted increments in an isolated main worktree and run its complete owning suite before delivery. This finding is acceptance of this engineering increment; it is not an assembled-main test or live/scientific acceptance.

## Accepted main assembly verification (Codex, 2026-10-24)

Isolated combined source `bc13de5b419cca5acc218844ceb2c67ce658433b` passed **605 passed, 2 skipped, 39 subtests passed in 72.29s (0:01:12)**. Both skips are host-visible-network refusal controls because the owning suite itself is network-isolated; independent host refusal checks above already returned exit6/no record. Training and sensor identity/tree/import tests executed. Full receipt/log: thesis `specs/002-assured-aeb/review/codex-assembled-verification-20261024/compat-assembled/`, log SHA-256 `b2e5f5f4b4e5b134142ba3174411ecf769dc29ced93a714f9c2d0a88eb6a9ecb`. All accepted source increments are present, no unaccepted candidate included. Subsequent delivery-record changes are documentation only. This satisfies the assembled engineering-suite gate; previously stated scientific/live/unit-entry/durable-cache limits remain.
