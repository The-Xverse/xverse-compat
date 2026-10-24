"""Phase 8 WP-08b: U4 unit isolation (review-wp08b-isolation finding 1; decisions.md "WP-09 #3 unit isolation").

The venv tests run the real CPython 3.13.13 interpreter through the U4 unit template (``-S -s -B``), inside ``unshare -rn``
(no network), read-only, and skip cleanly when the U4 venv or ``unshare`` is absent.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys

import pytest

import xverse_compat
from xverse_compat.inference import unit

from .test_inference_env import ENV, NETNS, PY313, ROOT, SITE, needs_env

CHECK = """
import json, sys
import xverse_compat.inference.loader, xverse_compat.inference.preprocess, xverse_compat.live.frames
try:
    import xverse_xdl
    xdl = True
except ImportError:
    xdl = False
base = [p for p in sys.path if p.endswith('3.13.13/lib/python3.13/site-packages')]
print(json.dumps({"xverseXdlImportable": xdl, "providerLoaded": 'xverse_compat.provider' in sys.modules, "baseSite": base,
                  "editable": [p for p in sys.path if 'editable' in p or 'xverse-t007' in p], "siteImported": 'site' in sys.modules,
                  "flags": [sys.flags.no_site, sys.flags.no_user_site, sys.flags.dont_write_bytecode]}))
"""


# ---- the template and the lazy package (test venv) ---------------------------------------------------


def test_wp08b_the_u4_template_runs_without_site_user_site_or_bytecode():
    argv = unit.command("/py", "m", "a", 1)
    assert argv == ["/py", "-S", "-s", "-B", "-m", "m", "a", "1"]
    env = unit.environment("/venv/site-packages", ("/compat/src",), home="/h")
    assert env == {"PATH": "/usr/bin", "HOME": "/h", "PYTHONDONTWRITEBYTECODE": "1", "ORT_DISABLE_TELEMETRY": "1",
                   "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "PYTHONPATH": "/venv/site-packages:/compat/src"}


def test_wp08b_lazy_exports_keep_every_public_name_and_import_on_first_use():
    names = [n for n in xverse_compat.__all__ if n != "__version__"]
    for name in names:
        owner = importlib.import_module(f"xverse_compat.{xverse_compat._EXPORTS[name]}")
        assert getattr(xverse_compat, name) is getattr(owner, name)
    assert set(xverse_compat.__all__) <= set(dir(xverse_compat)) and xverse_compat.__version__ == "0.2.0"
    with pytest.raises(AttributeError):
        xverse_compat.no_such_name  # noqa: B018
    from xverse_compat import ConformanceProcessProvider, admission  # noqa: F401 - names and a submodule, as the suite does


def test_wp08b_importing_the_package_root_does_not_import_provider():
    code = ("import sys, xverse_compat, xverse_compat.inference.loader; a = 'xverse_compat.provider' in sys.modules; "
            "xverse_compat.ConformanceProcessProvider; print(a, 'xverse_compat.provider' in sys.modules)")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                          env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["False", "True"]  # loaded only once a provider name is used


# ---- the U4 venv under the template, without network --------------------------------------------------


needs_netns = pytest.mark.skipif(not NETNS, reason="unprivileged network namespaces (unshare -rn) unavailable")


def _u4(*argv):
    proc = subprocess.run(["unshare", "-rn", *argv], env=unit.environment(SITE, (ROOT / "src", ROOT)), cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc


@needs_env
@needs_netns
def test_wp08b_under_the_template_the_u4_modules_import_with_no_xverse_xdl_and_no_base_site():
    out = json.loads(_u4(str(PY313), *unit.INTERPRETER_FLAGS, "-c", CHECK).stdout.strip().splitlines()[-1])
    assert out == {"xverseXdlImportable": False, "providerLoaded": False, "baseSite": [], "editable": [], "siteImported": False,
                   "flags": [1, 1, 1]}


@needs_env
@needs_netns
def test_wp08b_the_wp08_probe_passes_v1_through_the_template_and_the_venv_stays_clean():
    from .test_inference_env import FIXTURE, FIXTURE_DIGEST  # noqa: PLC0415

    proc = _u4(*unit.command(PY313, "tests.inference.probe", FIXTURE, FIXTURE_DIGEST, 3))
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["record"]["providers"] == ["CPUExecutionProvider"] and len(out["hashes"]) == 1
    assert "telemetry" not in proc.stderr
    assert not [p for p in (ENV / "venv").rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
    assert not list(SITE.glob("*.pth"))  # no .pth in the U4 venv: the R-9 order never produced bytecode here


def test_wp08b_the_wp08_build_script_checks_bytecode_after_every_interpreter_run():
    text = (ROOT / "tools/inference/make-inference-env.sh").read_text()
    assert "PYTHONDONTWRITEBYTECODE=1" in text.split("CLEAN=(", 1)[1].split(")", 1)[0]
    assert text.index("freeze --all") < text.index("refused: bytecode present") and '"$PY313" -S -s -B -c "$check"' in text
