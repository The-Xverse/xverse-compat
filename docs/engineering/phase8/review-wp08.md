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
