"""Target-neutral compatibility-provider conformance helpers for X-Verse vNext."""

from .provider import (
    CompatibilityProviderError,
    ConformanceProcessProvider,
    ProviderCompositionRoot,
)
from .platform_pin import PlatformPinError, platform_tree_digest, verify_platform_pin
from .rebuild import (
    BuildStep,
    ControlledRebuilder,
    RebuildError,
    RebuildManifest,
    RebuildResult,
    load_manifest,
    write_result_exclusive,
)

__version__ = "0.2.0"

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
