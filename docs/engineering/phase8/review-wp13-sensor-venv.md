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
