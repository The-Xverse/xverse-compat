"""The U4 unit command template (Phase 8 WP-08b; thesis decisions.md "WP-09 #3 unit isolation", R-1).

Every U4 process runs the real CPython 3.13.13 interpreter with ``-S -s -B``: no ``site`` (so the base interpreter's
site-packages, its ``.pth`` hooks and editable installs never fill a missing module), no user site and no bytecode. The
environment is exactly the one below, with ``PYTHONPATH`` naming the pinned U4 venv and the compat sources. WP-13 and the
blueprint U4 unit use this template; the test harnesses use it too. Standard library only.
"""

from __future__ import annotations

INTERPRETER_FLAGS = ("-S", "-s", "-B")
FIXED_ENVIRONMENT = {"PYTHONDONTWRITEBYTECODE": "1", "ORT_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "1",
                     "OPENBLAS_NUM_THREADS": "1"}


def environment(site_packages, extra_paths=(), home: str = "/nonexistent-inference-home") -> dict:
    """Return the complete U4 environment: ``PATH``, ``HOME``, the fixed settings and ``PYTHONPATH``."""

    paths = [str(site_packages), *(str(p) for p in extra_paths)]
    return {"PATH": "/usr/bin", "HOME": str(home), **FIXED_ENVIRONMENT, "PYTHONPATH": ":".join(paths)}


def command(interpreter, module: str, *args) -> list[str]:
    """Return the argv of one U4 process running ``-m module args``."""

    return [str(interpreter), *INTERPRETER_FLAGS, "-m", module, *(str(a) for a in args)]
