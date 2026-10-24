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
