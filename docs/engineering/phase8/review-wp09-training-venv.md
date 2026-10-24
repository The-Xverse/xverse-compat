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
2. **Implementation of finding 1 and results (2026-10-24 15:38:55).**
   - **Versions.**
     - `torch==2.14.1+cpu`: the newest cp313 CPU wheel on the CPU index (2.12.1, 2.13.0, 2.14.0 and 2.14.1 were listed).
       Its declared runtime dependencies are `filelock`, `typing-extensions>=4.10.0`, `setuptools>=77.0.3`,
       `sympy>=1.13.3`, `networkx>=2.5.1`, `jinja2` and `fsspec>=0.8.5`.
     - `onnx==1.23.2`: the newest on PyPI, a `cp312-abi3` wheel (valid for CPython 3.13). It declares `numpy`,
       `protobuf>=6.31.1`, `typing_extensions` and `ml_dtypes`.
     - `numpy==2.5.4`: the wheel is byte-identical to the U4 one.
   - **Download.** At 15:28, the pyenv 3.13.13 pip 26.1.1 under `env -i` installed nothing:
     1. `torch` alone: `--no-deps --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1+cpu"`;
     2. the rest: `--index-url https://pypi.org/simple --find-links <wheelhouse>`, with binary wheels, CPython 3.13 and the
        ABIs `cp313`, `abi3` and `none`, on the manylinux 2.28, 2.27, 2.17, 2014 and `any` platforms. `torch` resolved
        from the wheelhouse only, because the `+cpu` version exists nowhere on PyPI.
     There are 14 wheels, 233 048 639 bytes in total. **Every SHA-256 equals its index** (the CPU index `#sha256`
     fragment; the PyPI JSON digest and size). Free space was 32 GB before and 31 GB after the build.

     | Wheel | Bytes | SHA-256 | Index |
     | --- | --- | --- | --- |
     | `filelock-4.2.4-py3-none-any.whl` | 162475 | `301241438c57936ef93f4243a94f2559022268bfcf9b375a9a72eb0f8db8358e` | pypi.org/simple |
     | `fsspec-2026.9.0-py3-none-any.whl` | 221738 | `8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f` | pypi.org/simple |
     | `jinja2-3.1.6-py3-none-any.whl` | 134899 | `85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67` | pypi.org/simple |
     | `markupsafe-3.0.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | 23017 | `434139499bb20b502ed3baa1f169e618f924a97e7a777fea1a49446d80106cf6` | pypi.org/simple |
     | `ml_dtypes-0.6.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | 410169 | `26b1f1fa4f0435a2946859823f6e2bf06796f1e9f10f5a05b08a5e3c8f46ff69` | pypi.org/simple |
     | `mpmath-1.3.0-py3-none-any.whl` | 536198 | `a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c` | pypi.org/simple |
     | `networkx-3.7-py3-none-any.whl` | 2142205 | `e3fd2c13a7814cee3746340d8d7f8598a67f16a58bf47fb7f8793fab6efca1b0` | pypi.org/simple |
     | `numpy-2.5.4-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | 16718044 | `6ffa07666f8da0eef81d149934a626d0d95fbd6838432a33e66245423a9062c0` | pypi.org/simple |
     | `onnx-1.23.2-cp312-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | 8881633 | `7abf381d278f31ac62487fddedc9dd42da842dce94d5d43536836ee3efdf4a2b` | pypi.org/simple |
     | `protobuf-7.36.2-cp310-abi3-manylinux2014_x86_64.whl` | 343223 | `89f23aa53c24553a2416fd4fd1ec06f74fa42b14b546d8883128813f775bbfd2` | pypi.org/simple |
     | `setuptools-84.2.1-py3-none-any.whl` | 876263 | `ca140b45d5325a9478f880e351484f62fef15f336462e449ca0c03c873d589c2` | pypi.org/simple |
     | `sympy-1.14.0-py3-none-any.whl` | 6299353 | `e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5` | pypi.org/simple |
     | `torch-2.14.1+cpu-cp313-cp313-manylinux_2_28_x86_64.whl` | 196253851 | `331fa474e26e428e2e6af1143b2fdab19cee492d7d21897b8899ce1c14755662` | download.pytorch.org/whl/cpu |
     | `typing_extensions-4.16.0-py3-none-any.whl` | 45571 | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` | pypi.org/simple |

     Licences from the index or wheel metadata:
     - `torch`: `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`;
     - `onnx`, `ml_dtypes`: Apache-2.0;
     - `numpy`: as in WP-08;
     - `fsspec`, `markupsafe`, `networkx`: BSD-3-Clause; `mpmath`, `sympy`: BSD; `protobuf`: 3-Clause BSD;
     - `filelock`, `setuptools`: MIT; `typing_extensions`: PSF-2.0;
     - `jinja2`: the PyPI license field is empty (`TODO: engineering verification` from its wheel metadata).
   - **Lock.** `tools/training/training.lock`, SHA-256 `95109db70c7e20931330423e15c68cd24af93629c812523cca3612d91dc78b6b`: 14
     pins with hashes and a source-index comment per line.
   - **Build.** `tools/training/make-training-env.sh`, run inside `unshare -rn`, so no step had a network.
     - Venv `.x-verse-build/cache/xverse-aeb-training-20261024/`: 868 300 KiB, 17 363 site-packages files, no pip and no
       bytecode, installed set = the 14 locked distributions.
     - `sitePackagesTree` `426014798b5fa2279a5ec05114af39b4dc6985d6a53c45ed4c4ca38100a0d727`; `venvTree`
       `0ec2814cb2227dc8e1df8b70a3f7657b49d19eec84c2a3f14c41ecd586e6b52b`.
     - The interpreter, `libpython` and stdlib digests are those of the U4 record.
     - Two builds at the same path gave the same tree digests.
   - **Defect found during the first build, repaired before commit.**
     - setuptools installs `distutils-precedence.pth`. When the venv's own interpreter runs, which the script's `pip
       freeze` (through `--python`) does, it imports `_distutils_hack` and writes `__pycache__/__init__.cpython-313.pyc`.
     - That happened **after** the script's bytecode check, so the first identity record digested one `.pyc`.
     - Repair: `PYTHONDONTWRITEBYTECODE=1` for every step, and the bytecode check moved after `freeze`, immediately
       before the record. The venv was removed at its exact path (created by this task) and rebuilt: no bytecode.
     - The WP-08 inference script has the same ordering. It is unaffected only because its lock has no package with a
       `.pth` (R-9).
   - **Finding: the base interpreter's site-packages is not isolated by `-s`** (cross-cutting).
     - The pyenv 3.13.13 base `lib/python3.13/site-packages` holds unpinned packages (`jinja2`, `attrs`, `coverage`,
       `lxml`, `eclipse_zenoh` 1.9.0, …), `.pth` hooks that run at start-up (`a1_coverage.pth`), and **editable
       installs** that put `/home/jefferson/xverse-t007-t020-queue/src` on `sys.path` (`_editable_impl_xverse_xdl.pth`,
       `__editable__.xverse_hwsim-0.1.0.pth`). Seen in the strace of the network probe.
     - With `-s` (no user site) and `PYTHONPATH`, they still follow the venv on `sys.path`, so any module missing from
       a venv silently comes from there.
     - With `-S` they are gone. The training and U4 venvs both import with `-S -s -B`. The training script's import
       check and every probe here use `-S`.
     - **Consequence found:** under `-S`, `import xverse_compat.inference.loader` fails in the U4 venv with
       `ModuleNotFoundError: xverse_xdl`. The package `__init__` imports `provider`, which needs `xverse_xdl`, which
       only the editable base install provided. The WP-08 U4-pattern tests (`-s` without `-S`) therefore imported
       `xverse_xdl` from an unrelated checkout. Here the comparison probe loads `loader.py` (standard library only) by
       file path. See R-1 and R-2.
   - **Checks.** Each runs in `unshare -rn`, with `-S -s -B` and a test `TMPDIR`.
     - **CPU only:** `{"version": "2.14.1+cpu", "cuda": null, "cudaAvailable": false, "threads": 1, "deterministic": true}`.
     - **Deterministic training:** `Conv(3→4, 3×3) → ReLU → AdaptiveAvgPool(1) → Flatten → Linear(4→2)`, 20 SGD steps
       with batches of 8 on seeded synthetic data (seed 1234; test-only). Two fresh processes give the same weights digest,
       `7b76c81ebe3476851d4292969fad1078320e1ffffa8e2f3a4db6d4096502134a`.
     - **Export:** `torch.onnx.export(..., opset_version=13, dynamo=False)` gives the operators `{Conv, Flatten, Gemm,
       GlobalAveragePool, Relu}` (all V-1), opset 13, **IR version 7**, and passes `onnx.checker`.
     - **ONNX Runtime equivalence:** through the WP-08 `load_model` in the U4 venv (read-only), against PyTorch on four
       fixed inputs. **Observed maximum absolute difference: 2.9802322387695312e-08**, the same in two runs. This is an
       observation, not a protocol value; the test bound is 1e-6 (test-only).
     - **Network and telemetry:** strace of import, a training step and an export:
       - no `AF_INET` or `AF_INET6` socket and no IP `connect`;
       - two `AF_UNIX` connects to `/var/run/nscd/socket` (absent, `ENOENT`) and a read of `/etc/passwd`: a local
         user lookup;
       - one temporary file in `TMPDIR`;
       - no host-fingerprint reads of the WP-08 kind.
       A static scan of `torch/lib` and `onnx` for telemetry endpoints found none (two hits were the symbol
       `…11dstack…`). No mitigation is needed beyond a run-scoped `TMPDIR`.
   - **Tests.** `tests/training/test_training_env.py`: 7 tests.
     - 2 run everywhere: the lock (CPU `torch` from the CPU index, PyPI for the rest, numpy equal to U4, every hash
       64 hex), and the script flags with the freeze-before-check order.
     - 5 need the venvs and skip cleanly without them:
       - the identity record against the lock and the disk (tree digests recomputed, no bytecode, no pip);
       - CPU only;
       - reproducible training;
       - V-1 export;
       - ONNX Runtime equivalence, which also checks that the U4 venv stays bytecode-free.
     - Probes (restored): removing the seed fails the reproducibility test; adding a `Sigmoid` fails the operator test.
   - **Suite.** With the venvs: 477 passed, 39 subtests (base `b2ff3e7`: 470). Without them
     (`XVERSE_COMPAT_TRAINING_ENV` and `XVERSE_COMPAT_INFERENCE_ENV` set to `/nonexistent`): 467 passed, 10 skipped.
   - **Residuals.**
     - R-1 (cross-cutting, for the coordinator). The K-11 unit pattern (`-s` plus `PYTHONPATH`) includes the unpinned base
       pyenv site-packages and its `.pth` hooks: U4 (WP-08), the Phase 8 units, and the Phase 7 and S1
       `lite-driver`/`driver-stimulus` units. The recommendation is `-S` in every K-11 unit command, or the base
       site-packages digested in the identity records. That is a decision for the unit owners (WP-12, WP-13, #5, the Phase 7
       harness); nothing outside this increment is changed.
     - R-2. Under `-S`, the U4 unit cannot import `xverse_compat.inference` because of the package `__init__`. Either
       make `xverse_compat/__init__.py` lightweight (lazy exports), a compat change, or lock `xverse_xdl` into the U4 venv.
       The recommendation is the former. It is a decision for WP-13.
     - R-3. Export uses the legacy TorchScript exporter (`dynamo=False`), deprecated since PyTorch 2.9. The default
       exporter would need `onnxscript`, which is not locked. The pin to 2.14.1 keeps it available for the campaign.
     - R-4. The export is at IR 7, while V-1 was shown at IR 8. ONNX Runtime 1.31 runs it, and the real model repeats V-1.
     - R-5. Determinism and equivalence are shown for the test network, single-threaded, on this host. The real model's
       tolerance is `TODO: author decision` (WP-09 #4).
     - R-6. Training runs need a run-scoped `TMPDIR`. The local user lookup (`/etc/passwd`, nscd) is benign.
     - R-7. The venv is reproducible at its build path, not relocatable (console scripts), as in WP-08.
     - R-8. The build script is a modified copy of the inference script; a shared builder could be extracted later.
     - R-9. The inference script's bytecode check precedes its `freeze`. That is harmless today (no `.pth` in the U4
       lock), but it should get the same order and `PYTHONDONTWRITEBYTECODE=1` (a WP-08 follow-up).
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.
3. **Independent review of findings 1 and 2 (2026-10-24 15:43:00).**
   - **Reviewer and method.** An independent reviewer who did not write this increment.
     - Read `5ab0dc6` and `4d62ba2` against base `b2ff3e7`, and checked them against thesis
       `design/wp09-training-pipeline.md` §4–§5 and the `decisions.md` rows "WP-09 training pipeline" (288) and
       "WP-09 #3 unit isolation (R-1, R-2, R-9)" (293).
     - The thesis Git freshness check was run read-only: branch `agent/synchronize-thesis-obsidian-notes`, the fetch
       succeeded, and no upstream commit touches the note. The relevant sections of `notes/dynamic_thesis_notes.md` were
       read (DYN-002; evaluation-only ground truth).
     - The wheelhouse and both venvs were only read. Every torch or ORT execution ran inside `unshare -rn` with
       `-S -s -B` and `PYTHONDONTWRITEBYTECODE=1`.
     - No download, no install, no CARLA. The worktree was not changed except for this entry.
   - **Verdict: PASS WITH NOTES. Nothing blocks the merge.** The merge still awaits the author's acceptance.
   - **Evidence.**
     - **Hashes.** `sha256sum` of the 14 wheelhouse files equals the 14 lock hashes exactly.
       - The hash-against-index cross-check of finding 2 could not be repeated offline (no downloads). It is accepted as
         recorded.
       - Dependency confusion is closed structurally: `torch==2.14.1+cpu` is a local version that exists only on the CPU
         index. Installation is `--no-index --require-hashes --no-deps` from the local wheelhouse.
     - **Closure.** From each wheel's `METADATA`, every `Requires-Dist` without an extra marker names a locked
       distribution: no missing hard dependency, and no `nvidia-*` dependency on the CPU `torch`.
     - **Build flags** (make-training-env.sh 38–60).
       - `venv --without-pip`; the base pip with `--python` and `--no-index --find-links --require-hashes --no-deps
         --no-compile`; `PYTHONDONTWRITEBYTECODE=1` on every step.
       - The import check runs with `-S -s -B`, and the bytecode check comes after `freeze`, the last step that runs the
         venv's interpreter, which is where the `distutils-precedence.pth` defect wrote its `.pyc`.
       - After the full suite, the training venv and the U4 venv each hold 0 `__pycache__` directories and 0 `.pyc`
         files.
     - **The `-S` finding, reproduced.**
       - The base pyenv site-packages holds `a1_coverage.pth`, `_editable_impl_xverse_xdl.pth` (which adds
         `/home/jefferson/xverse-t007-t020-queue/src`) and `__editable__.xverse_hwsim-0.1.0.pth`.
       - With `-s -B`, `sys.path` contains the base site-packages **and** `/home/jefferson/xverse-t007-t020-queue/src`.
         With `-S -s -B`, it contains neither.
       - This matches finding 2, and it is now decided in row 293.
     - **Determinism, export and ORT, re-run in scratch under `unshare -rn`.**
       - The `export` probe gives the same weights digest as finding 2 (`7b76c81e…134a`), the operators `{Conv, Flatten,
         Gemm, GlobalAveragePool, Relu}`, opset `[13]` and IR 7.
       - `ort_compare` in the U4 venv gives providers `["CPUExecutionProvider"]` and `maxAbsDiff` `2.98e-08`, which equals
         finding 2.
       - The compat suite with the venvs: 477 passed, 39 subtests (torch and ORT inside `unshare -rn`).
     - **No protocol value is invented.** The 1e-6 bound is labelled test-only in the test (line 109) and the record, and
       the observed 2.98e-08 is recorded as an observation. The seed 1234, 20 steps and batch 8 are labelled test-only in
       the probe. The real model's tolerance stays `TODO: author decision` (R-5).
     - **jinja2 licence, from its wheel.** `METADATA` has no `License` field, but has `Classifier: License :: OSI Approved
       :: BSD License` and `License-File: LICENSE.txt`.
       - The bundled `jinja2-3.1.6.dist-info/licenses/LICENSE.txt` is the 3-clause BSD text: "Copyright 2007 Pallets",
         clauses 1–3, including "Neither the name…".
       - So jinja2 is **BSD-3-Clause**. This closes the `TODO: engineering verification` of finding 2.
   - **Issues (none blocks the merge).**
     - **LOW-1: IR 7 departs from design §5 ("IR 8"), and no test pins the IR.**
       - Where: tests/training/test_training_env.py 98–101.
       - R-4 records the IR honestly, and ORT 1.31 runs it.
       - Either amend design §5 to "the IR emitted for opset 13 (7)", a thesis-side edit, or set `ir_version` explicitly at
         export.
       - In both cases, assert `irVersion` in `test_wp09_export_uses_only_v1_operators_at_opset_13`, so that a change of
         exporter or `onnx` version is detected.
     - **LOW-2: the tests run torch and ORT *without* a network namespace when `unshare -rn` is unavailable.**
       - Where: tests/training/test_training_env.py 28 and 42.
       - The WP-08 earlier-import test skips in that case. These tests fall back to a plain subprocess, which conflicts
         with the rule that every torch or ORT run is network-isolated.
       - Repair: skip, as WP-08 does, when `NETNS` is false.
     - **LOW-3: the build script does not enforce its own network isolation.** Finding 2's build was run inside
       `unshare -rn` by the operator, but `make-training-env.sh` imports torch (line 56) on whatever network it is given.
       Optional: refuse unless run inside a network namespace, or wrap the import check in `unshare -rn`.
     - **LOW-4: the installer process sees the base `.pth` hooks.**
       - The base pip must run with its own site-packages, so `-S` is impossible for it. Its process therefore runs
         `a1_coverage.pth` and puts the editable `xverse_xdl` path on `sys.path`.
       - The lock hashes protect what is installed. The identity record digests the installer's `pip` tree, but not those
         hooks.
       - Record the base site-packages `.pth` files, with their digests, in the identity record, or state the limit
         beside R-1.
   - **Residuals R-1 to R-9.**
     - R-3 to R-8 are accurate.
     - R-1 is now **decided** (`decisions.md` 293):
       - `-S -s -B` with `PYTHONDONTWRITEBYTECODE=1` in every Phase 8 unit command;
       - the Phase 7 and S1 units are left unchanged before the soak, as a declared 1.0 limit.

       R-1 should cite that row.
     - R-2 and R-9 are **decided** as increment WP-08b, before WP-13. They should cite it.
     - Add the jinja2 licence (BSD-3-Clause, from the wheel) to finding 2's licence list when the record is next amended.
   - **Recommendation.**
     - Ready for the author's acceptance.
     - Before increment #4 trains anything, repair LOW-2 (skip without a network namespace) and pin the IR (LOW-1).
     - LOW-3 and LOW-4 are optional or a residual. Cite rows 293 and WP-08b in the residuals.
4. **Disposition of finding 3 (2026-10-24 15:46:18; `decisions.md` row "WP-09 #3 review LOW items", 15:44, under the
   author's delegation, flagged for review). Repair all four before the merge. Recorded before repair.**
   - LOW-1: design §5 now names the IR that the pinned exporter emits for opset 13 (IR 7), a thesis-side amendment already
     made. The export test asserts `irVersion == 7`. V-1 is re-run on the real model's IR (#4).
   - LOW-2: the torch and ONNX Runtime tests skip when `unshare -rn` is unavailable, as the WP-08 test does.
   - LOW-3: the build script refuses to run unless no non-loopback network interface is visible.
   - LOW-4: the identity record lists the base interpreter's `.pth` hooks with their SHA-256. If that changes
     `identity.json`, only `identity.json` is regenerated, read-only from the existing venv; there is no rebuild
     unless one is needed.
   - The residuals cite the rows "WP-09 #3 unit isolation" and WP-08b; `jinja2` BSD-3-Clause is added to the licence
     list.
