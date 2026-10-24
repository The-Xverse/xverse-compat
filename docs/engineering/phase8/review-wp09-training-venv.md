# Review log: Phase 8 WP-09 increment #3, the pinned offline training venv (xverse-compat)

Candidate `candidate/phase8-wp09-training-venv-20261024`, base main `b2ff3e7` (WP-10 #2 merged). Specification:
- thesis `specs/002-assured-aeb/design/wp09-training-pipeline.md` §4 (the training venv: CPU `torch`, `onnx` and
  `numpy`, the full closure hash-locked, on loop10, never used by a unit) and §5 (export: IR 8 and opset 13, V-1
  operators only, logits only);
- the `decisions.md` row "WP-09 training pipeline" (15:15, under the author's delegation), which authorizes the
  separate pinned PyTorch CPU training venv and its wheels downloaded to a loop10 wheelhouse;
- the WP-08 pattern (`tools/inference/make-inference-env.sh`, compat review-wp08 findings 1–7);
- compat review-wp09-preprocess R-2: the same `numpy==2.5.4` as the U4 lock.
Findings are recorded before repairs. This is offline engineering tooling, never a unit; no thesis model is trained.

## Findings

1. **Design record: the training venv (2026-10-24 15:27:52, before any download).**
   - **Selection rule.**
     - `torch`: the newest release with a `cp313` `manylinux` x86_64 **CPU** wheel (local version `+cpu`) on the
       official PyTorch CPU index, `https://download.pytorch.org/whl/cpu`.
     - `onnx`: the newest release with a `cp313` `manylinux` x86_64 wheel on `https://pypi.org/simple`.
     - `numpy==2.5.4` (the U4 lock).
     - Every dependency of these, as declared in their wheel metadata (`Requires-Dist` without an extra marker), is
       resolved once by `pip download` for CPython 3.13 manylinux x86_64, with binary wheels only, and pinned at the
       resolved version. Each wheel's SHA-256 is checked against its index: the `#sha256=` fragment of the PyTorch
       simple index for `torch`, and the PyPI JSON `digests.sha256` for the rest. The source index of every wheel
       is recorded.
     - **Dependency confusion is avoided:** `torch` is downloaded alone, with `--no-deps`, from the CPU index, and is
       requested as `torch==<v>+cpu`, a local version that exists only there and in the local wheelhouse. Everything
       else comes from PyPI.
   - **Space.** Free space is checked before the download; loop10 had 32 GB. The script refuses below 2 GB, as the
     WP-08 script does. The wheelhouse and venv sizes are recorded.
   - **Lock** (`tools/training/training.lock`): every wheel as `name==version --hash=sha256:<h>`, with the source
     index in a comment per line.
   - **Wheelhouse:** `.x-verse-build/cache/xverse-aeb-training-wheels-20261024/`, filled once.
   - **Build script** (`tools/training/make-training-env.sh`), on the `make-inference-env.sh` pattern:
     1. the same refusals (a missing or mismatched wheel, an existing target, less than 2 GB free);
     2. `venv --without-pip` with the pyenv 3.13.13 interpreter;
     3. the base pip with `--python`, `--no-index --find-links --require-hashes --no-deps --no-compile`;
     4. an import check under `env -i` and `-s -B`, with `OMP_NUM_THREADS=1`;
     5. refuse if any `__pycache__` or `.pyc` exists afterwards;
     6. the identity record `xverse-compat.training-env-record/1`: wheels, the lock path and hash, the installed set,
        site-packages and venv tree digests, the interpreter, `libpython` and stdlib digests, the installer pip,
        glibc and CPU.
   - **Venv:** `.x-verse-build/cache/xverse-aeb-training-20261024/`. The U4 venv is only ever run read-only, with
     `-B`.
   - **Checks.** A probe module, `tests/training/train_probe.py`, runs in the venv; compat tests run it and skip
     cleanly when the venv is absent.
     - **CPU only:** `torch.version.cuda is None`, `torch.cuda.is_available() is False`, and `+cpu` in the version.
     - **Deterministic training:** a tiny `Conv → ReLU → AdaptiveAvgPool(1) → Flatten → Linear` network on synthetic
       data from a seeded generator. It uses `torch.manual_seed`, `torch.use_deterministic_algorithms(True)`,
       `torch.set_num_threads(1)`, `OMP_NUM_THREADS=1` and a fixed number of SGD steps. The weights digest is the
       SHA-256 of the state-dict tensors in key order. Two fresh processes must give the same digest.
     - **Export:** `torch.onnx.export` in eval mode, opset 13, static shapes, logits only. An operator check with `onnx`
       allows only `Conv`, `Relu`, `GlobalAveragePool`, `Flatten` and `Gemm`.
     - **ONNX Runtime equivalence:** the exported file runs through the WP-08 `load_model` in the U4 venv (read-only,
       `-B`, telemetry off). The maximum absolute difference from PyTorch on fixed inputs is measured and recorded as
       an **observation**, not a protocol value. The test bound is that observation's order of magnitude, stated as a
       test-only bound.
     - **Network and telemetry:** imports and a training step under `unshare -rn` with `strace -f` (`socket`,
       `connect`, `openat`). Any `AF_INET` or `AF_INET6` attempt, or any host-fingerprint read, is a finding to
       mitigate, as in WP-08. A static scan of the wheels for telemetry endpoints and controls follows the WP-08
       method.
