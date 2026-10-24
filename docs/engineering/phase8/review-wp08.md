# Review log: Phase 8 WP-08, U4 inference venv (xverse-compat)

Candidate `candidate/phase8-wp08-inference-venv-20261024`, base main `34cc046` (WP-03 merged).
Specification: thesis `specs/002-assured-aeb/design/wp08-inference-stack.md` (DRAFT, PROPOSED) and the
`decisions.md` row "WP-08 inference stack" (11:17, under the author's delegation, flagged for review):
- ONNX Runtime CPU, single-threaded, in a new pinned CPython 3.13.13 venv for U4;
- built from a hash-locked local wheelhouse with `--no-index --require-hashes --no-deps` and an identity
  record, in the loop10 cache;
- the model is one SHA-256-bound artifact, which U4 verifies fail-closed before readiness;
- the fallback is an owned NumPy forward pass, if V-1, V-3 or V-4 fails.
Downloading the pinned wheels into a loop10 wheelhouse is authorized. Findings are recorded before
repairs. The maturity is an engineering increment: the environment and its checks only, not M1, not AEB
evidence, and no model of the thesis (GA-35).

## Findings

1. **Design record: the inference venv and the loader (2026-10-24 11:19:22, before any code or download).**
   - **Lock** (`tools/inference/u4-inference.lock`). Exactly two requirements in pip hash-lock form,
     `onnxruntime==<v> --hash=sha256:<h>` and `numpy==<v> --hash=sha256:<h>`. The versions are the newest
     releases on PyPI with a `cp313` `manylinux` x86_64 wheel compatible with the host glibc 2.35 at
     download time. The hashes are the downloaded wheels' SHA-256, cross-checked against the hashes PyPI
     publishes. The lock is the single source of the pins.
   - **Wheelhouse** (`.x-verse-build/cache/xverse-aeb-inference-wheels-20261024/`). Filled once by
     `pip download --only-binary=:all: --no-deps --python-version 3.13 --implementation cp --abi cp313
     --platform <manylinux tag>`. This runs the pyenv 3.13.13 interpreter's own pip, which writes only to
     the target directory and installs nothing. The source index (`https://pypi.org/simple`), the versions,
     file names, sizes and hashes are recorded in finding 2.
   - **Build script** (`tools/inference/make-inference-env.sh <envdir> <wheeldir> <lock> <record-out>`), on
     the `make-client-env.sh` pattern:
     1. refuse with less than 2 GB free (the same bound as the CARLA script), if `<envdir>` exists, if a
        locked wheel is missing, or if its SHA-256 differs from the lock;
     2. `env -i` `python3.13 -m venv` with the pyenv 3.13.13 interpreter that runs U4;
     3. `pip install --no-index --find-links <wheeldir> --require-hashes --no-deps -r <lock>`;
     4. an offline import check under `env -i`, `-s -B`, with `OMP_NUM_THREADS=1` and
        `OPENBLAS_NUM_THREADS=1`, through the U4 pattern: the real interpreter with `PYTHONPATH` to the
        venv's `site-packages`, never the venv's symlinked interpreter;
     5. an identity record, `xverse-compat.inference-env-record/1`, holding: per-wheel name, SHA-256 and size;
        the lock's SHA-256; `pip freeze --all`; a tree digest of `site-packages` (sorted relative paths and
        file SHA-256, excluding `__pycache__`); the interpreter path and SHA-256; the CPU model and flags
        from `/proc/cpuinfo`; the glibc version; the import-check output; and the sizes.
   - **Venv** at `.x-verse-build/cache/xverse-aeb-inference-20261024/` (`venv/` and `identity.json`). No
     existing venv is touched; `.x-verse-build/cache/xverse-lite-live-20261022` and
     `.x-verse-build/worktrees/*` are not read or written.
   - **Loader** (`src/xverse_compat/inference/loader.py`, standard library at import; ONNX Runtime is
     imported only after the digest check):
     - `load_model(path, expected_digest, *, expected_inputs=None, expected_outputs=None)` reads the file
       once and compares `sha256:<hex>` with `expected_digest`, which must be an exact
       `sha256:<64 hex>`. On a mismatch, an ill-formed digest or an unreadable file it raises
       `ModelRefused` before ONNX Runtime is imported, so before any readiness.
     - The session is created from the **verified bytes in memory**, not by re-opening the path, so the
       file cannot change between the check and the load.
     - Session options: `intra_op_num_threads = 1`, `inter_op_num_threads = 1`, sequential execution, a
       recorded graph-optimisation level (basic), `use_deterministic_compute = True`, and only
       `CPUExecutionProvider`. An optional input and output name, shape and type check refuses a model
       that does not match the declared schema.
     - It has no training or write path, and returns the session with a record of the digest, the options
       and the provider list.
   - **Test model for V-1 and V-4.** No `onnx` package is added to the U4 venv. A standard-library ONNX
     protobuf writer in the tests (`tests/inference/minimal_onnx.py`) builds a tiny CNN-shaped model:
     `Conv`, `Relu`, `GlobalAveragePool`, `Flatten`, `Gemm` and `Sigmoid`, at IR version 8 and
     opset 13, with fixed float32 weights from a closed-form formula. The bytes are deterministic, and
     the generated file is checked in as `tests/inference/fixtures/tiny-cnn.onnx` with its SHA-256. A test
     regenerates it and compares the bytes.
   - **Checks.**
     - V-1: under the U4 pattern, `onnxruntime` imports and runs the tiny model with only `numpy`
       installed `--no-deps`, and its output agrees with an independent NumPy computation of the same
       network (tolerance `1e-5`, absolute and relative, a test bound for float32 rounding only).
     - V-4: bit-exact repeats of a fixed input, 100 runs in one process and 5 fresh processes, comparing
       the output bytes' SHA-256.
     - V-6: a model whose digest mismatches is refused by `load_model` before ONNX Runtime is imported.
   - **Tests in the compat suite.** `tests/inference/`:
     - the loader refusals and the protobuf writer run everywhere: standard library only, no ONNX Runtime;
     - V-1 and V-4 run as subprocesses of the real 3.13.13 interpreter with `PYTHONPATH` to the inference
       venv, and **skip cleanly** when the venv is absent, located by `XVERSE_COMPAT_INFERENCE_ENV` or the
       default cache path.
     The main suite must stay at least 359 passed.
   - **Not in scope.** The U4 unit and V-2 (Maestro launch) belong to the blueprint increment with WP-12;
     V-3 (the readiness budget) and V-5 (inference time) need the real model and host load, and are
     NEEDS DATA; the NumPy fallback; any thesis model.
2. **Implementation of finding 1 and results (2026-10-24 11:25:09).**
   - **Wheelhouse.** `.x-verse-build/cache/xverse-aeb-inference-wheels-20261024/`, filled at 11:19 with
     `pip download --no-cache-dir --only-binary=:all: --no-deps --python-version 3.13 --implementation cp
     --abi cp313 --platform manylinux_2_28_x86_64 --index-url https://pypi.org/simple`. This ran the pyenv
     3.13.13 interpreter's pip 26.1.1 under `env -i` and installed nothing. The versions were the newest on
     PyPI with a cp313 manylinux x86_64 wheel (PyPI JSON API, `info.version`). Each downloaded SHA-256
     and size equals the PyPI-published value.

     | Wheel | Size (bytes) | SHA-256 | PyPI upload |
     | --- | --- | --- | --- |
     | `onnxruntime-1.31.0-cp313-cp313-manylinux_2_28_x86_64.whl` | 23760708 | `37fd78cee5160c7a43a1730ccb3682ffd880af9c9e80385d625c0c2f8b125809` | 2026-10-09T04:18:40Z |
     | `numpy-2.5.4-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | 16718044 | `6ffa07666f8da0eef81d149934a626d0d95fbd6838432a33e66245423a9062c0` | 2026-10-10T20:03:21Z |

     PyPI metadata at download:
     - `onnxruntime`: licence "MIT License"; `requires_dist` `flatbuffers`, `numpy>=1.21.6`,
       `packaging`, `protobuf>=4.25.8`, with `sympy` and `ml_dtypes` only as extras.
     - `numpy`: licence expression `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`.
     - Both need Python ≥ 3.11 or ≥ 3.12, and the manylinux tags need glibc ≤ 2.28; the host has 2.35.
   - **Lock.** `tools/inference/u4-inference.lock` (SHA-256 `8d0689ee070344da55b9569ee90c25c8987a03236fa9c93d2a353666a3582367`)
     holds exactly the two pins with their hashes.
   - **Build script.** `tools/inference/make-inference-env.sh`, as in finding 1, with one addition: the
     import check sets `ORT_DISABLE_TELEMETRY=1` (see the telemetry finding below). The venv was built
     twice. The first build, made before the telemetry finding, was removed by its exact path, a directory
     this task had created; the second is the venv kept. Both gave the **same `site-packages` tree
     digest**, so the build is reproducible on this host.
   - **Venv and identity record.** `.x-verse-build/cache/xverse-aeb-inference-20261024/`, 151952 KiB,
     with `identity.json`:
     - `pipFreeze`: `numpy==2.5.4`, `onnxruntime==1.31.0`, and `pip==26.0.1` from `ensurepip`;
     - `sitePackagesTreeSha256` `16c8546d3451b1b50321ed6dbb307410c715ff4db849020caeb266938299f5cd`;
     - interpreter `/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13`, SHA-256
       `9907c621375bc585b55087a939f30310d5bc6e3b6b15a986f734dc24077cf968`;
     - glibc 2.35; CPU Intel Core i9-14900HX, with its flags;
     - import check return code 0.
     The build took about 6 s. No other venv was touched, and `.x-verse-build/cache/xverse-lite-live-20261022`
     and `.x-verse-build/worktrees/*` were neither read nor written.
   - **Finding during V-1: the ONNX Runtime 1.31 Linux wheel embeds Microsoft 1DS telemetry.**
     - Evidence, by static inspection of the installed binaries:
       - `libonnxruntime.so.1.31.0` and the pybind module contain `telemetry_1ds.cc`, a `OneDsTelemetry`
         class, the collector URL `https://mobile.events.data.microsoft.com/OneCollector/1.0`, and the
         environment variable name `ORT_DISABLE_TELEMETRY`;
       - the Python API exposes `disable_telemetry_events()`.
     - At import with defaults it logs "Failed to persist telemetry device ID; using an in-memory
       identifier".
     - **Probe.** A session on the test model and 10 runs, with a 2 s wait, traced with `strace -f` for
       `socket`, `connect`, `sendto`, `sendmsg` and `openat`. It ran in an unprivileged network
       namespace with no network (`unshare -rn`), so nothing could leave the host. Results:
       - **defaults**: no `AF_INET` or `AF_INET6` socket and no `connect`. The process read host
         fingerprint files that the disabled run does not read: `/sys/class/dmi/id/{board_vendor,
         product_name,sys_vendor}`, `/proc/sys/kernel/osrelease`, `/proc/1/cgroup`, `/.dockerenv`,
         `/run/.containerenv`, `/run/systemd/container` and `/sys/devices/system/cpu/online`. It logged the
         device-ID warning;
       - **`ORT_DISABLE_TELEMETRY=1`**: none of those reads and no warning, so the 1DS initialisation is
         skipped;
       - **`disable_telemetry_events()` only**: the warning is still logged, because initialisation
         happens at import, before the call;
       - **both**: as with the variable alone.
     - **Limit.** With no network, absence of a socket does not show what the default build does on a
       networked host; that was deliberately not tried.
     - **Mitigation, implemented.** The loader refuses unless `ORT_DISABLE_TELEMETRY=1` is set before
       ONNX Runtime is imported, and calls `disable_telemetry_events()` as a second line. The U4 unit
       environment must set the variable (R-5).
     - **Also present in the wheel:** an `AzureExecutionProvider` (`get_available_providers()`). The
       loader passes only `CPUExecutionProvider` and refuses unless the session's providers are exactly
       that.
   - **Loader.** `src/xverse_compat/inference/loader.py` (`verified_bytes`, `load_model`,
     `ModelRefused`, `LoadedModel`), as in finding 1, plus the telemetry and provider checks. Session
     options: one intra-op thread, one inter-op thread, `ORT_SEQUENTIAL`, `ORT_ENABLE_BASIC`,
     `use_deterministic_compute`. It imports only the standard library at import time.
   - **Test model.** `tests/inference/minimal_onnx.py` (standard library) writes
     `tests/inference/fixtures/tiny-cnn.onnx`: 497 bytes, SHA-256
     `29f7e86bd6ab25f3dcf6abc7dd9785025101d44c9aba32620b63112458a89d64`, IR 8, opset 13,
     `Conv`-`Relu`-`GlobalAveragePool`-`Flatten`-`Gemm`-`Sigmoid`. No `onnx` package was used or
     installed. `tests/inference/probe.py` runs it through the loader in the U4 pattern.
   - **V-1: met.** In the U4 pattern (`env -i`, the real 3.13.13 interpreter with `-s -B`,
     `PYTHONPATH` to the venv's `site-packages` plus compat `src`, single-threaded, telemetry off),
     `onnxruntime` 1.31.0 imports and runs the test model with **only numpy installed, `--no-deps`**. The
     declared `flatbuffers`, `packaging` and `protobuf` are not needed for this path. Output
     0.4240870177745819 (float32) against the independent NumPy reference 0.4240870215725029; providers
     `["CPUExecutionProvider"]`; no telemetry message.
   - **V-4: met for this model on this host.** 100 repeats in one process and 10 in each of four further
     fresh processes give one output hash,
     `cd42b6e6fece44ab0546c3ceebc5764955d95b4ba9830db7cea3e00b7de6d2b8`. Three manual runs of 100 repeats
     gave the same hash.
   - **V-6: met.**
     - A model with one changed byte is refused with "model digest ... differs from the declared ...",
       with `onnxruntime` not imported, both in the compat test venv and in the U4 pattern.
     - Ill-formed declared digests (7 cases), a missing file, and a telemetry variable that is unset or
       `0` are refused before the import.
     - A declared input schema that the model does not match is refused after the session is created.
   - **Tests.** `tests/inference/test_inference_env.py`, 16 tests:
     - 12 run everywhere: the fixture determinism, the digest forms, V-6 before import, the telemetry guard,
       the loader's standard-library imports, and the lock and script;
     - 4 need the venv and skip cleanly without it (`XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`:
       12 passed, 4 skipped): the identity record against the lock, V-1, V-4, and V-6 in the venv with the
       schema refusal.
   - **Mutation checks (not committed; restored).** Bypassing the digest comparison fails 2 tests;
     removing the telemetry guard fails 2 tests.
   - **Suite.** 375 passed, 39 subtests (base `34cc046`: 359).
   - **Residuals.**
     - R-1 (telemetry). The 1.31 wheel embeds 1DS telemetry, and by default fingerprints the host.
       `ORT_DISABLE_TELEMETRY=1` demonstrably skips its initialisation, and the loader enforces it. The
       egress behaviour of the default build on a networked host is unknown. Unit-level network isolation
       for U4 would be a platform matter. The author may prefer to review this dependency; it is flagged.
     - R-2. V-1 covers the import and six operators at opset 13. A code path that imports `packaging`,
       `protobuf` or `flatbuffers` (tooling, quantisation, model-editing APIs) would fail closed with
       `ImportError`; the real WP-09 model must pass V-1 again.
     - R-3. V-4 holds per host and only for the test model. The real model repeats V-4 under WP-09 and
       WP-13. `ORT_ENABLE_BASIC` is an engineering choice; `ORT_ENABLE_ALL` was not assessed.
     - R-4. V-2 (Maestro launch), V-3 (readiness budget, NEEDS DATA) and V-5 (inference time) are not done.
       They need the blueprint U4 unit and the real model.
     - R-5 (blueprint wiring). The U4 environment is `PATH=/usr/bin`, `HOME=<run>/home`,
       `ORT_DISABLE_TELEMETRY=1`, `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1`, with `PYTHONPATH` set
       to `<venv>/lib/python3.13/site-packages:<compat src>`. Arguments: `-s -B`. The run records the
       identity-record digest; the descriptor's environment identity (thesis WP-08 record F-5) is a
       WP-12 / harness item.
     - R-6. The thesis record `design/wp08-inference-stack.md` needs a thesis-side correction, not made
       here:
       - its dependency list for ONNX Runtime (`coloredlogs` and `sympy` are no longer required);
       - its licence line for NumPy (the full expression above);
       - the new telemetry finding R-1.
     - R-7. The loader reads the whole model into memory. That suits the small AD-02 network; a large model
       would need a streamed digest.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 11:28:12).**
   - **Reviewer and method.** An independent reviewer who did not write this increment.
     - Read `28b400f` and `be20f79` against base `34cc046`, the thesis `decisions.md` row "WP-08 inference
       stack" (280) and `design/wp08-inference-stack.md`, including its correction section of 11:25.
     - The built artifacts in `/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/`
       were only read.
     - `xverse-lite-live-20261022` and `.x-verse-build/worktrees/*` were not touched. There was no
       download or install, and no CARLA.
     - Processes ran one at a time. The worktree was not changed except for this entry.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** MEDIUM-1 should be repaired before a U4 unit
     uses the loader, preferably on this branch, because the thesis correction section already calls the
     mitigation "enforced". The merge still awaits the author's acceptance.
   - **Evidence.**
     - **Wheel hashes.** `sha256sum` of the two wheelhouse files equals the lock (`37fd78ce…5809`,
       `6ffa0766…62c0`), and the sizes equal finding 2's (23760708 and 16718044).
     - **Tree digest.** A read-only rehash of `venv/lib/python3.13/site-packages`, with the script's
       algorithm (sorted relative paths and file SHA-256, `__pycache__` excluded), gives
       `16c8546d…f5cd`, equal to `identity.json`. It covers 1726 files.
       - `identity.json` `lockSha256` equals the worktree lock, and `interpreterSha256` equals a rehash of
         `/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13`.
       - `pipFreeze` is numpy, onnxruntime and pip, and `importReturnCode` is 0.
       - There is no symlink and no `.pth` file in `site-packages`.
     - **Build script.** The lock pre-check loop (make-inference-env.sh 18–23) runs in a pipeline
       subshell, but `set -euo pipefail` propagates its `exit 3`. The install line is `--no-index
       --find-links <wheels> --require-hashes --no-deps -r <lock>`.
     - **Loader** (loader.py 38–86).
       - The file is read once (44–45), digested and compared. The session is built from those bytes
         (74), and the path is never reopened, so there is no TOCTOU.
       - The ill-formed-digest, unreadable, mismatched and telemetry-variable refusals all come before
         `import onnxruntime` (61–64).
     - **Telemetry probe, reproduced** under `unshare -rn` with `strace -f`, using a session and 10 runs.
       - Defaults: 0 `AF_INET`/`AF_INET6` sockets and 0 `connect`, but 3 `/sys/class/dmi` reads, plus
         `/.dockerenv` and `/proc/1/cgroup`.
       - `ORT_DISABLE_TELEMETRY=1`: none of these.
       - This agrees with finding 2.
     - **Suite.** With the venv present: 375 passed, 39 subtests, so V-1, V-4 and the in-venv V-6 ran. With
       `XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`, `tests/inference` gives 12 passed and 4 skipped,
       each with the reason "U4 inference venv absent".
     - **V-1, V-4 and V-6.**
       - The tests check the providers (`CPUExecutionProvider` only), the version, float32 output within
         1e-5 of an independent NumPy reference, and no telemetry message (V-1).
       - V-4: one output hash within each of 5 fresh processes (100 + 4 × 10 runs), and one across them.
       - V-6: a tampered model and an unset telemetry variable are refused with `onnxruntime` not
         imported, in the U4 pattern, and a schema mismatch is refused.
       - The evidence is sound for this test model and host, as R-2 and R-3 state.
   - **Issues (none blocks the merge).**
     - **MEDIUM-1: the telemetry guard can be bypassed by an earlier import, and the record then reports
       telemetry as disabled.**
       - Where: loader.py 62–66 and 85.
       - The guard reads `os.environ` when `load_model` is called. It does not check whether ONNX Runtime
         was already imported, which is when 1DS initialises.
       - Probe, run under `unshare -rn` in the U4 pattern: `import onnxruntime` with the variable unset,
         then `os.environ['ORT_DISABLE_TELEMETRY'] = '1'`, then `load_model(fixture, digest)`. The 1DS
         warning `telemetry_1ds.cc:600 … Failed to persist telemetry device ID` was logged at the first
         import. **`load_model` succeeded anyway, with `record["telemetry"] == "disabled"`.**
       - So any code path in U4 that imports `onnxruntime` before the loader runs initialises telemetry
         and fingerprints the host. Examples: a module-level import in a perception module, a type
         import, or a dependency. The record then states the opposite.
       - Repair:
         - refuse when `onnxruntime` or `onnxruntime.capi` is already in `sys.modules` at the guard;
         - in WP-13, check the variable at U4 entry, before any application import, rather than only in
           the loader;
         - add the test above, run as a subprocess.
       - The thesis correction section ("refuses unless that variable is set before import") then holds
         as written.
     - **MEDIUM-2: the tree digest excludes the bytecode the interpreter actually runs.**
       - Where: make-inference-env.sh 25 and 38.
       - `pip install` compiles 123 `__pycache__` directories into `site-packages`, and the digest
         excludes them. `-B` only stops Python writing bytecode. It still reads a `__pycache__/*.pyc`
         whose header matches the source's mtime and size.
       - A modified `.pyc` with an intact header therefore runs while `sitePackagesTreeSha256` still
         matches. The identity record does not bind the executed Python code.
       - Repair options:
         - install with `pip install --no-compile`, assert that no `__pycache__` exists, and digest
           everything. Note the effect on the V-3 readiness budget: every import then compiles in memory;
         - or include the `.pyc` files and record the build as host-reproducible only.
       - R-5 or R-1 should say which was chosen.
     - **LOW-1: the identity record binds the interpreter binary only.**
       - The pyenv standard library, a `libpython` if built shared, and the `ensurepip`-bundled pip that
         performed the install are not digested, and `pip 26.0.1` itself is unlocked content in the venv.
       - This is acceptable for an engineering record, but the record supports "these site-packages on this
         interpreter binary", not a full-environment claim.
       - Optional: digest the interpreter's `lib/python3.13` tree too, or state the limit in R-5.
     - **LOW-2: refusal boundaries.**
       - The module docstring (loader.py 4) says every refusal comes before the import. Session creation,
         provider and schema refusals (73–82) necessarily come after it. They still come before
         readiness, as the design requires, but the docstring should say so.
       - A failing `import onnxruntime` raises `ImportError`, not `ModelRefused`. That is fail-closed but
         a different type; U4 should treat both as refusals.
       - `expected_inputs` and `expected_outputs` are optional. WP-13 should make them mandatory for the
         frozen model.
     - **LOW-3: the identity record names a worktree path.** `identity.json` `lock` is
       `/home/jefferson/xverse-compat-worktrees/phase8-wp08-20261024/tools/inference/u4-inference.lock`,
       which disappears after the merge. Its `lockSha256` is the binding value; the path is informational.
   - **Residuals R-1 to R-7.**
     - R-2, R-3, R-4 and R-7 are accurate.
     - R-1 is accurate on what was probed, and honest about the untested networked default. It should add
       the earlier-import bypass of MEDIUM-1 until that is repaired.
     - R-5 is accurate. It should state that the U4 entry point checks the variable first (MEDIUM-1) and
       the bytecode choice (MEDIUM-2).
     - R-6 has since been addressed on the thesis side: `design/wp08-inference-stack.md`, "Correction,
       11:25". That correction should be amended for MEDIUM-1.
     - Missing: MEDIUM-2 and LOW-1.
   - **Recommendation.**
     - Repair MEDIUM-1, with a subprocess test, on this branch.
     - Decide MEDIUM-2 (`--no-compile` and digest everything, or include the `.pyc` files) and rebuild only
       if the author authorizes it.
     - Record LOW-1 to LOW-3.
     - Then a focused re-review, followed by acceptance.
4. **Disposition of finding 3 (2026-10-24 11:29:32; decided by the coordinator under the author's delegation of
   2026-10-24, flagged for the author's review). Recorded before repair.**
   - **MEDIUM-1, repair.** `load_model` refuses with `ModelRefused` when `onnxruntime` is already in
     `sys.modules`. A subprocess test covers the earlier-import bypass, and any probe that runs with
     default telemetry runs only inside `unshare -rn`. R-5 records that the U4 entry point (WP-13) checks
     `ORT_DISABLE_TELEMETRY` before any other import.
   - **MEDIUM-2, repair.** Install with `pip --no-compile`, assert that no `__pycache__` directory or
     `.pyc` file exists after the build, and digest every file. Rebuilding the venv from the existing
     local wheelhouse is authorized, with no new download; the old venv is removed only at its exact path.
     The import-time cost is recorded as an input to V-3.
   - **LOW-1.** `identity.json` gains a standard-library tree digest (the pyenv 3.13.13 `lib/python3.13`,
     excluding `site-packages` and `__pycache__`), the `libpython` hash if one exists, and the venv pip's
     version and hash.
   - **LOW-2.** The docstring is corrected: the session, provider and schema refusals come after the import
     and before readiness. An import failure maps to `ModelRefused`. WP-13 makes the input and output
     schema checks mandatory (recorded).
   - **LOW-3.** `identity.json` binds the lock by its hash and its repository-relative path.
   - The thesis correction section is amended by the coordinator, not here.
5. **Repair of finding 4 (2026-10-24 11:33:46).**
   - **MEDIUM-1, the earlier-import bypass.** After the variable check, `load_model` refuses when any
     `onnxruntime` module is already in `sys.modules` ("onnxruntime was imported before the loader's
     telemetry guard"). Its 1DS telemetry would have initialised at that import, outside the guard.
     - Test `test_wp08_an_earlier_onnxruntime_import_is_refused`: the probe imports `onnxruntime` with
       the variable unset, sets it, and calls `load_model`, which refuses. The probe's stderr shows that
       the earlier import did initialise telemetry. Because this probe runs with default telemetry, the
       test runs it only inside `unshare -rn` (no network), and skips if network namespaces are
       unavailable.
     - Removing the guard fails this test (probe, restored).
   - **MEDIUM-2, bytecode.**
     - The venv is now created `--without-pip`. The base interpreter's pip 26.1.1 installs into it through
       `--python` with `--no-index --find-links --require-hashes --no-deps --no-compile`, so the venv holds
       neither pip nor bytecode.
     - The build refuses (exit 5) if any `__pycache__` or `.pyc` exists after the import check. The
       identity record digests every file of `site-packages` and of the whole venv; a symlink contributes
       its target.
     - A test recomputes both digests from disk and asserts that no bytecode exists, so a `.pyc` written
       later, or any other change, fails it. U4 must run with `-B` (R-5).
     - The old venv was removed at its exact path and rebuilt from the existing wheelhouse, with no
       download, in about 4.5 s:
       - `sitePackagesTree` `eb7d164d17a3f39f49df11f14438b747cce78609237d46103e87102fa5e0c0b3`
         (1252 files);
       - `venvTree` `9f79dcc7f3fd147dad99f309b335534e1c1b91e0737fb2b2290f279ce647d0a9` (1265 entries);
       - 121740 KiB; installed `numpy==2.5.4` and `onnxruntime==1.31.0` only.
     - **Reproducibility.** A second build at another path, in the scratchpad and deleted afterwards,
       differed only in `numpy-2.5.4.dist-info/RECORD` and `onnxruntime-1.31.0.dist-info/RECORD`. These
       hold the hashes of the console-script wrappers in `bin/` (`f2py`, `numpy-config`,
       `onnxruntime_test`), whose shebang embeds the venv path. All other files were identical. The tree
       digests are therefore path-dependent through those two files.
     - **Import-time cost, an input to V-3.** `import numpy, onnxruntime` in the U4 pattern, 5 runs each,
       host load about 4.5 to 5.3:
       - with bytecode (the finding 2 venv, before removal): 0.096 to 0.131 s;
       - without bytecode (this venv): 0.221 to 0.289 s.
       This is the import only; model load, session creation and warm-up stay NEEDS DATA with the real model.
   - **LOW-1.** `identity.json` (schema `xverse-compat.inference-env-record/2`) adds:
     - **`interpreter.libpython`**: the interpreter is built shared, and `python3.13` loads
       `libpython3.13.so.1.0`, SHA-256
       `169a1f5d8a1692162da9a4dce105bc6cbd58f8a60f2bf2f78bac66ad6d9b4685`. Most of the interpreter is in this
       library, not in the sealed executable, which still has SHA-256 `9907c621…cf968`;
     - **`interpreter.stdlibTree`**: `lib/python3.13` without `site-packages` and `__pycache__`,
       `ccf0cbaf99d50035da7a556f6680c9e5e8b5784687b175599c7eaac8b19a7f73` (2398 entries);
     - **`installer`**: pip 26.1.1, with its package tree `298f3a1a…c985` (439 entries) and
       `pip-26.1.1.dist-info` `85f48358…c32d`.
   - **LOW-2.** The docstring now separates the refusals made before the import (digest, file, variable,
     earlier import) from those made after it and before readiness (import failure, session, providers,
     schema). An import failure maps to `ModelRefused`; tested in the compat venv, which has no
     `onnxruntime`. WP-13 makes the input and output schema arguments mandatory for the frozen model
     (recorded in the docstring and R-5).
   - **LOW-3.** `identity.json` `lock` is `{"repositoryPath": "tools/inference/u4-inference.lock",
     "sha256": "8d0689ee…2367", "repositoryRevision": "76b4750…"}`. The binding value is the hash; the
     revision is the build-time checkout, recorded for information only.
   - **Tests.** `tests/inference/test_inference_env.py`: 18 tests, 2 new. The identity test is extended
     (schema 2, lock path, no pip, no bytecode, tree digests recomputed, interpreter, libpython, stdlib and
     installer). The probe gains the `import-first` mode.
   - **Suite.** With the venv: 377 passed, 39 subtests. Without it (`XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`):
     372 passed, 5 skipped, 39 subtests. No bytecode is in the venv after either run.
   - **Residuals, updated.**
     - R-1: the earlier-import bypass is repaired in the loader. A network-attached default build remains
       untested by design.
     - R-5, amended: the U4 entry point (WP-13) checks `ORT_DISABLE_TELEMETRY=1` before any other import,
       treats `ModelRefused` as a refusal before readiness, makes the schema arguments mandatory, and runs
       with `-s -B`, so that no bytecode is written into the venv.
     - R-8 (new): the tree digests are path-dependent through the two `RECORD` files, so the venv is
       reproducible at its build path, not relocatable. Rebuilding means rebuilding at the same path, or
       re-recording.
     - R-6 is amended on the thesis side by the coordinator.
   - **Status.** Candidate for a focused re-review and the author's acceptance. Not accepted, not merged,
     not pushed.
6. **Independent re-review of the repair, findings 4 and 5 (2026-10-24 11:35:49).**
   - **Reviewer and method.** The finding 3 reviewer.
     - Read `76b4750` and `f28fec6` against `5e21d56`.
     - The rebuilt venv and `identity.json` were only read. I rehashed every recorded tree with my own
       implementation of the record's rule: sorted relative paths, a file's SHA-256 or a symlink's target.
     - Ran the compat suite one process at a time, with the venv and with
       `XVERSE_COMPAT_INFERENCE_ENV=/nonexistent-env`.
     - There was no download or install, and no CARLA. `xverse-lite-live-20261022` and
       `.x-verse-build/worktrees/*` were not touched. The worktree was not changed except for this entry.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** The merge still awaits the author's
     acceptance.
   - **Evidence.**
     - **Suite.** With the venv: 377 passed, 39 subtests. Without it: 372 passed and 5 skipped, each with
       the reason "U4 inference venv absent". After both runs the venv still has 0 `__pycache__`
       directories and 0 `.pyc` files, and its trees still equal the record.
     - **Read-only rehash against `identity.json` (schema 2).** Every one of these is equal:
       - `sitePackagesTree` (1252 entries, `eb7d164d…c0b3`);
       - `venvTree` (`9f79dcc7…d0a9`);
       - `interpreter.stdlibTree` (2398 entries, `ccf0cbaf…7f73`);
       - `interpreter.libpython` (`/home/jefferson/.pyenv/versions/3.13.13/lib/libpython3.13.so.1.0`,
         `169a1f5d…4685`);
       - the interpreter executable (`9907c621…`);
       - `installer.pipTree` and `pip-26.1.1.dist-info`;
       - `lock.sha256` against `tools/inference/u4-inference.lock`.

       `lock.repositoryRevision` `76b4750…` is a commit of this branch.
   - **Items.**
     - **MEDIUM-1: closed** (loader.py 70–72).
       - After the variable check, any `onnxruntime` or `onnxruntime.*` entry in `sys.modules` is refused.
       - `test_wp08_an_earlier_onnxruntime_import_is_refused` runs the probe's `import-first` mode under
         `unshare -rn` only. It skips when network namespaces are unavailable, so a default-telemetry
         probe never runs with a network.
       - It asserts the refusal, and it asserts the telemetry line in stderr, which proves the bypass was
         real. My finding 3 probe now fails as intended.
     - **MEDIUM-2: closed.**
       - The venv is created `--without-pip` (make-inference-env.sh 28). The base interpreter's pip
         installs through `--python` with `--no-index --find-links --require-hashes --no-deps
         --no-compile` (30).
       - The build refuses (exit 5) if any `__pycache__` or `.pyc` exists after the import check.
       - `sitePackagesTree` and `venvTree` digest every file, symlinks included. The identity test
         recomputes both from disk and asserts that no bytecode exists.
       - The import-cost figures (0.10–0.13 s with bytecode, 0.22–0.29 s without) are correctly passed to
         V-3 as an input, not a result.
     - **LOW-1: closed.** The record gains libpython (the interpreter is built shared, so most of it is in
       this library), the standard-library tree and the installing pip's identity, and the rehash matches.
       See LOW-A for the standard-library bytecode.
     - **LOW-2: closed.**
       - The docstring separates the refusals made before the import (digest, file, variable, earlier
         import) from those made after it and before readiness (import failure, session, providers,
         schema).
       - An import failure maps to `ModelRefused` (75), tested in the compat venv, which has no
         `onnxruntime`.
       - The mandatory schema arguments are recorded for WP-13 (R-5).
     - **LOW-3: closed.** `lock` is `{repositoryPath, sha256, repositoryRevision}`, and the hash is the
       binding value.
     - **Residuals.**
       - R-1, R-2, R-3, R-4, R-6 and R-7 are accurate. R-5 (amended) is accurate.
       - R-8 is accurate for `sitePackagesTree`, but understated for `venvTree` (LOW-B). Both trees are
         reproducible at the build path and not relocatable, which is the right statement.
   - **New notes (LOW, none blocking).**
     - **LOW-A: the standard-library tree excludes the bytecode the U4 interpreter reads.**
       - Where: make-inference-env.sh 82.
       - `stdlibTree` skips `__pycache__`, and the pyenv `lib/python3.13` holds 5265 `.pyc` files outside
         `site-packages`. U4 runs with `-B`, which stops writing bytecode, not reading it. So a modified
         standard-library `.pyc` with an intact header would run unrecorded. This is the MEDIUM-2 class
         one level down.
       - It is lower risk: the files are the shared, install-time pyenv tree, which this increment does not
         own.
       - Either include the standard-library `.pyc` files in `stdlibTree`, which is stable while the pyenv
         install is unchanged and gets no new writes under `-B`, or state in R-5 that the
         standard-library bytecode is not bound.
     - **LOW-B: `venvTree` depends on the build path in more places than R-8 names.**
       - Besides the two `RECORD` files, `venv/pyvenv.cfg` `command = … -m venv --without-pip
         /media/…/xverse-aeb-inference-20261024/venv`, the `bin/` console-script shebangs and the
         `bin/python3.13` symlink target embed paths. The `sitePackagesTree` statement in R-8 is exact.
       - Amend R-8 to cover `venvTree`.
     - **LOW-C: the identity test does not recompute two of the recorded trees.** It checks `stdlibTree`
       only for `entries > 0` and the installer by version only. My rehash shows they match. Optional:
       recompute them as is already done for the venv trees.
     - **LOW-D: the earlier-import guard relies on `sys.modules`.** A module deliberately removed from
       `sys.modules` after import would pass it. This is tampering, not an accidental code path. The WP-13
       entry-point check before any import (R-5) is the primary control, and the loader guard is a second
       line. No change is needed.
   - **Recommendation.** Ready for the author's acceptance. LOW-A and LOW-B are one-line record or residual
     amendments, best made before the merge or recorded in the acceptance. LOW-C and LOW-D are optional or
     informational.
