# Review log: Phase 8 WP-08b, U4 unit isolation (xverse-compat)

Candidate `candidate/phase8-wp08b-isolation-20261024`, base main `34b514d` (WP-09 #2 merged). Specification:
- thesis `specs/002-assured-aeb/decisions.md` row "WP-09 #3 unit isolation (R-1, R-2, R-9)" (15:39, under the author's
  delegation, flagged for review);
- the basis, compat review-wp09-training-venv finding 2 (R-1, R-2, R-9).
WP-08b is R-2 and R-9, plus the U4 part of R-1. The Phase 7 and S1 units are **not** changed (a declared limit of
1.0, repaired after the soak). Findings are recorded before repairs. This is an engineering increment verified
offline.

## Findings

1. **Design record (2026-10-24 15:41:21, before any code).**
   - **What `xverse_compat/__init__.py` does today.** It eagerly imports:
     - `provider` (`CompatibilityProviderError`, `ConformanceProcessProvider`, `ProviderCompositionRoot`);
     - `platform_pin` (`PlatformPinError`, `platform_tree_digest`, `verify_platform_pin`);
     - `rebuild` (`BuildStep`, `ControlledRebuilder`, `RebuildError`, `RebuildManifest`, `RebuildResult`,
       `load_manifest`, `write_result_exclusive`).
     It defines `__version__ = "0.2.0"` and the `__all__` of these 15 names. Only `provider.py` imports `xverse_xdl`
     at module level (line 11); `platform_pin` and `rebuild` use the standard library.
   - **Who imports the package root.** `tests/test_provider_conformance.py` 31 (`from xverse_compat import (...)` by
     name) and `tests/test_admission.py` 97 (`from xverse_compat import admission`, a submodule). There is no
     `import *` and no root import in `src`, `tools` or the blueprints (`automotive/` at their main).
   - **The failure.** Reproduced at `34b514d`: under `-S -s -B`, with `PYTHONPATH` set to the U4 venv plus compat
     `src`, `import xverse_compat.inference.loader` raises `ModuleNotFoundError: No module named 'xverse_xdl'`. The
     package `__init__` runs before any submodule.
   - **Repair (R-2): lazy exports by PEP 562.**
     - `__init__.py` keeps `__version__` and the same `__all__`.
     - It replaces the eager imports with a name-to-submodule table, a module-level `__getattr__` that imports the
       submodule on first access (and caches the value in the module globals), and a `__dir__`.
     - `from xverse_compat import ConformanceProcessProvider`, `xverse_compat.verify_platform_pin` and
       `from xverse_compat import admission` (a submodule, resolved by the import system) keep working unchanged.
     - An unknown name raises `AttributeError` as before.
     - `xverse_compat.inference.*` and `xverse_compat.live.frames` then import with the standard library only.
     - Under `TYPE_CHECKING` the eager imports stay visible to type checkers.
   - **Repair (R-9).** `tools/inference/make-inference-env.sh`:
     - `PYTHONDONTWRITEBYTECODE=1` in `CLEAN` for every step;
     - the bytecode check moved after `pip freeze`, immediately before the record, as in the training script;
     - the import check runs under `-S -s -B` (R-1).
     The existing U4 venv is **not** rebuilt. Its lock has no distribution with a `.pth`, which is checked: the
     site-packages holds no `.pth`, so the old order could not have produced bytecode, and the WP-08 identity test
     re-verifies the trees on disk. The modified script is exercised once by a build into a scratch directory, inside
     `unshare -rn` and from the existing wheelhouse only, and compared file by file with the real venv. Only the two
     `RECORD` files that hash path-bearing console scripts may differ (compat review-wp08 R-8). The scratch build is
     then removed.
   - **The U4 unit command template (R-1, U4 part).**
     - Compat `src` defines no unit command today. The U4 pattern lives in the test harnesses
       (`tests/inference/test_inference_env.py::_u4`, `test_preprocess.py::_probe`) and in the build script's import
       check, all with `-s -B`.
     - A single template is added in `xverse_compat/inference/unit.py` (standard library):
       - `INTERPRETER_FLAGS = ("-S", "-s", "-B")`;
       - `environment(site_packages, extra_paths, home)`, which returns exactly `PATH`, `HOME`,
         `PYTHONDONTWRITEBYTECODE=1`, `ORT_DISABLE_TELEMETRY=1`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` and
         `PYTHONPATH`;
       - `command(interpreter, module, *args)`.
     - The two harnesses use it. WP-13 and the blueprint U4 unit (#5) are to use it.
   - **Tests.**
     - `tests/inference/test_unit_isolation.py`:
       - in the U4 venv under `unshare -rn` with `-S -s -B` (skipped if the venv or `unshare` is absent):
         `xverse_compat.inference.loader` and `.preprocess` import with `xverse_xdl` absent; `sys.path` holds no base
         site-packages, no editable path and no `.pth` effect; the WP-08 probe passes V-1 through the template; the venv
         stays bytecode-free;
       - in the test venv: the lazy exports give the same objects as the submodules, `dir()` lists `__all__`, an
         unknown name raises `AttributeError`, and importing the package root does not import `provider` until a
         provider name is used;
       - the template's flags and environment.
     - The full suite must give an equal or higher count.
2. **Implementation of finding 1 (2026-10-24 15:45:49).**
   - **R-2.** `src/xverse_compat/__init__.py` now uses PEP 562 lazy exports:
     - `__version__` and `__all__` are unchanged;
     - an `_EXPORTS` table maps the 13 names to `provider`, `platform_pin` and `rebuild`;
     - `__getattr__` imports the owning submodule on first use and caches the value; `__dir__` lists `__all__`;
     - the eager imports remain only under `TYPE_CHECKING`.
     - No caller changed: `from xverse_compat import (...)` (`test_provider_conformance.py`) and `from xverse_compat
       import admission` (`test_admission.py`) pass unchanged.
   - **R-1 (U4 part).** `src/xverse_compat/inference/unit.py` (new, standard library):
     - `INTERPRETER_FLAGS = ("-S", "-s", "-B")`;
     - `FIXED_ENVIRONMENT` (`PYTHONDONTWRITEBYTECODE`, `ORT_DISABLE_TELEMETRY`, `OMP_NUM_THREADS` and
       `OPENBLAS_NUM_THREADS`, each `1`);
     - `environment(site_packages, extra_paths, home)` and `command(interpreter, module, *args)`.
     The U4 harnesses `test_inference_env.py::_u4` and `test_preprocess.py::_probe` now use the template, so every
     existing U4-venv test runs under `-S -s -B`. The default-telemetry bypass test removes only
     `ORT_DISABLE_TELEMETRY`, inside `unshare -rn`. No other unit command exists in compat `src`.
   - **R-9.** `tools/inference/make-inference-env.sh`:
     - `PYTHONDONTWRITEBYTECODE=1` in `CLEAN` for every step;
     - the import check under `-S -s -B`;
     - the bytecode check moved after `pip freeze`, immediately before the record.
     **The real U4 venv was not rebuilt.** Its site-packages has no `.pth` (tested), so the old order could not have
     written bytecode, and the WP-08 identity test still recomputes its trees on disk and passes.
     **Exercise of the modified script:** a build into a scratch directory, inside `unshare -rn` from the existing
     wheelhouse only. It gave import 0, no bytecode, `installed`, `wheels` and lock hash equal to the real record,
     and 1 252 site-packages files. The file-by-file comparison with the real venv differs **only** in
     `numpy-2.5.4.dist-info/RECORD` and `onnxruntime-1.31.0.dist-info/RECORD`, which hash the path-bearing console
     scripts (compat review-wp08 R-8). The scratch build was then removed.
   - **Requirement (a), the U4 venv under `-S`.** At base `34b514d`, `import xverse_compat.inference.loader` failed
     with `ModuleNotFoundError: xverse_xdl`. Now, under `unshare -rn` with `-S -s -B`:
     - `loader`, `preprocess` and `live.frames` import;
     - `xverse_xdl` is **not importable** and `provider` is not loaded;
     - `sys.path` has no base site-packages and no editable path, `site` is not imported, and the flags are
       `no_site`, `no_user_site` and `dont_write_bytecode`;
     - the WP-08 probe passes V-1 through the template with no telemetry message;
     - the venv stays bytecode-free.
   - **Tests.** `tests/inference/test_unit_isolation.py`: 6 tests.
     - The template's argv and exact environment.
     - The lazy exports are the same objects as the submodules', with `dir()`, an `AttributeError` for an unknown name,
       and both public import forms.
     - Importing the root and `inference.loader` does not load `provider` until a provider name is used.
     - Requirement (a) in the U4 venv, and the V-1 probe through the template (both skip without the venv or
       `unshare`).
     - The build-script order and flags.
     - Probe: with the eager base `__init__` restored, 4 of the 6 tests fail.
   - **Suite (requirement (b)).** Base `34b514d`, measured in a temporary detached worktree that was then removed: 535
     passed, 39 subtests. Candidate with the U4 venv: **541 passed, 39 subtests** (+6). Without it
     (`XVERSE_COMPAT_INFERENCE_ENV=/nonexistent`): 529 passed, 12 skipped. The U4 venv has no bytecode after the runs.
     - A first attempt at the base count from a `git archive` export gave 1 failure and 24 subtests, because the export
       is not a git checkout. It is not used as the baseline.
   - **Residuals.**
     - R-1. The Phase 7 and S1 `lite-driver` and `driver-stimulus` units keep `-s` only until after the soak: a
       declared limit of 1.0, repaired in a later 1.0.x increment ("WP-09 #3 unit isolation").
     - R-2. The blueprint U4 unit (#5) and WP-13 must use `xverse_compat.inference.unit`. The other Phase 8 units (U2,
       U3, U5, U6) need the same flags in their own command templates (WP-12, #5).
     - R-3. Lazy exports defer an `xverse_xdl` failure from package import to first use of a provider name. That is
       intended: a deployment without `xverse_xdl` fails exactly where it is needed.
   - **Status.** Candidate for independent review. Not accepted, not merged, not pushed.

3. **Independent read-only review by Codex (2026-10-24; candidate `840091a2c28866fa3fa5c8e4d5f2b276708d6dce`). PASS.**
   - Reviewed the complete change from `34b514d`: lazy public exports, the U4 command/environment template,
     both inference harnesses, the build-script ordering and the six isolation controls. No product repair was made.
   - Existing public names and lazy submodule imports are preserved. U4 imports no provider or `xverse_xdl`;
     `-S -s -B` and the explicit venv-first path remove base/user-site discovery. This is interpreter dependency
     isolation, not a sandbox or hardware-independence claim.
   - Re-ran the full candidate suite with network disabled and the host UID preserved:
     `unshare -cn env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src
     /dev/shm/compat-p6-venv/bin/python -B -m pytest tests -q -p no:cacheprovider --tb=short`.
     Result: **541 passed, 39 subtests passed**, 30.60 s; no skipped test. `bash -n` and `git diff --check` pass.
   - An earlier whole-suite `unshare -rn` invocation changed the effective UID to 0 and failed socket-path checks
     under `/run/user/0`; 66 failed, 475 passed. This was a review invocation error, retained here, not a product
     defect or a waived regression. `unshare -cn` preserves UID 1000 and the complete suite passes.
   - Suite-log SHA-256: `7d9b6a59b7dd7f444cf656c00a10df0c27f04bc7ad4655a6b882b61e299937d2`.
   - Finding 2 residuals R-1 to R-3 remain carried. Phase 7/S1 commands and rc.1 soak inputs are untouched.

4. **Acceptance under the author's delegation of 2026-10-24 (Codex, 2026-10-24; flagged for author review).**
   - Accepted WP-08b on independent finding 3 and the full 541-test/39-subtest result, with finding 2 residuals
     R-1 to R-3 carried. Basis: thesis `specs/002-assured-aeb/decisions.md` §G and the WP-09 #3 unit-isolation row;
     the author's instruction to continue Claude's X-Verse work preserves that delegated engineering scope.
   - This accepts the offline isolation increment only. It grants no Phase 8 live execution, protocol freeze,
     principal-campaign admission, M1 or scientific claim. Integration and push are the next delivery steps.
