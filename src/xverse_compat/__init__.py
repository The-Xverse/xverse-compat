"""Target-neutral compatibility-provider conformance helpers for X-Verse vNext.

The public names are exported lazily (PEP 562): a submodule is imported on first access to one of its names, so importing
the package itself, or a subpackage such as ``xverse_compat.inference``, needs the standard library only. ``provider``
needs ``xverse_xdl``; the U4 inference unit runs under ``-S`` with neither ``xverse_xdl`` nor the base interpreter's
site-packages available (compat review-wp08b-isolation finding 1; thesis decisions.md "WP-09 #3 unit isolation", R-2).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.2.0"

_EXPORTS = {
    "CompatibilityProviderError": "provider",
    "ConformanceProcessProvider": "provider",
    "ProviderCompositionRoot": "provider",
    "PlatformPinError": "platform_pin",
    "platform_tree_digest": "platform_pin",
    "verify_platform_pin": "platform_pin",
    "BuildStep": "rebuild",
    "ControlledRebuilder": "rebuild",
    "RebuildError": "rebuild",
    "RebuildManifest": "rebuild",
    "RebuildResult": "rebuild",
    "load_manifest": "rebuild",
    "write_result_exclusive": "rebuild",
}

__all__ = [
    "CompatibilityProviderError",
    "ConformanceProcessProvider",
    "BuildStep",
    "ControlledRebuilder",
    "ProviderCompositionRoot",
    "PlatformPinError",
    "RebuildError",
    "RebuildManifest",
    "RebuildResult",
    "__version__",
    "platform_tree_digest",
    "load_manifest",
    "write_result_exclusive",
    "verify_platform_pin",
]


def __getattr__(name: str) -> Any:
    """Import the owning submodule on first access to a public name and cache the value."""

    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # eager names for type checkers only; never executed
    from .platform_pin import PlatformPinError, platform_tree_digest, verify_platform_pin
    from .provider import CompatibilityProviderError, ConformanceProcessProvider, ProviderCompositionRoot
    from .rebuild import (BuildStep, ControlledRebuilder, RebuildError, RebuildManifest, RebuildResult, load_manifest,
                          write_result_exclusive)
