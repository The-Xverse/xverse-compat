"""Content-lock validation for the mutable local xverse-xdl development source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_INCLUDED_ROOTS = ("src/xverse_xdl", "xdl/schemas", "xdl/profiles")


class PlatformPinError(RuntimeError):
    """Report version, file-set, or content drift from the reviewed platform pin."""


def _source_files(source_root: Path) -> tuple[Path, ...]:
    """Return the complete packaged platform source surface in stable order."""

    files = [source_root / "pyproject.toml"]
    for relative_root in _INCLUDED_ROOTS:
        files.extend(
            path
            for path in (source_root / relative_root).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    return tuple(sorted(set(files), key=lambda path: path.relative_to(source_root).as_posix()))


def platform_tree_digest(source_root: Path) -> tuple[int, str]:
    """Return file count and SHA-256 digest for the complete packaged source surface.

    @param source_root Root of the reviewed xverse-platform checkout.
    @return Stable file count and hexadecimal tree digest.
    """

    digest = hashlib.sha256()
    paths = _source_files(source_root)
    for path in paths:
        relative = path.relative_to(source_root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + path.read_bytes() + b"\0")
    return len(paths), digest.hexdigest()


def verify_platform_pin(manifest_path: Path, source_root: Path) -> dict[str, Any]:
    """Verify exact package version, file set, and content against a reviewed manifest.

    @param manifest_path Public-safe JSON content-lock manifest.
    @param source_root Root of the local platform source used by uv.
    @return Parsed manifest after successful validation.
    @raises PlatformPinError If the version, file count, or digest differs.
    """

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pyproject = (source_root / "pyproject.toml").read_text(encoding="utf-8")
    expected_version = f'version = "{manifest["packageVersion"]}"'
    if expected_version not in pyproject:
        raise PlatformPinError("platform package version differs from the reviewed pin")
    file_count, digest = platform_tree_digest(source_root)
    if file_count != manifest["fileCount"]:
        raise PlatformPinError("platform package file set differs from the reviewed pin")
    if digest != manifest["treeSha256"]:
        raise PlatformPinError("platform package content differs from the reviewed pin")
    return manifest
