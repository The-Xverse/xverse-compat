"""Controlled, reproducible rebuilds of immutable compatibility sources.

The module deliberately separates a public rebuild envelope from a restricted
target patch. It never runs the rebuilt artifact or writes to the source checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from typing import Any, Mapping, NoReturn


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_ID_RE = re.compile(r"[0-9a-f]{40}\Z")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_TOOL_RE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_META_RE = re.compile(r"[A-Za-z0-9_.:/@ -]{1,160}\Z")
_PRIVATE_IPV4_RE = re.compile(
    r"(?:^|[^0-9])(?:10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.)"
)
_SENSITIVE_NAME_RE = re.compile(r"(?:secret|token|password|credential|private[_-]?key)", re.I)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?:password|token|secret|credential|private[_ -]?key)\s*[:=]", re.I
)
_URI_USERINFO_RE = re.compile(r"[a-z][a-z0-9+.-]*://[^/@:\s]+:[^/@\s]+@", re.I)
_PRIVATE_IPV6_RE = re.compile(r"(?:^|[^0-9a-f])(?:fc|fd|fe8|fe9|fea|feb)[0-9a-f]*:", re.I)
_ALLOWED_PLACEHOLDERS = ("{stage}", "{attempt}")
_MANIFEST_FIELDS = {
    "schemaVersion", "sourceRevision", "sourceTree", "patchSha256",
    "gitSha256", "toolSha256", "allowedPatchPaths", "steps", "outputPath",
    "environment", "metadata",
}
_STEP_FIELDS = {"executable", "arguments", "workingDirectory", "timeoutSeconds"}


class RebuildError(RuntimeError):
    """A fail-closed rebuild error with a stable public-safe code."""

    _MESSAGES = {
        "manifest-invalid": "The rebuild manifest is invalid.",
        "source-identity-mismatch": "The source identity does not match the manifest.",
        "patch-digest-mismatch": "The patch digest does not match the manifest.",
        "patch-invalid": "The controlled patch is invalid.",
        "patch-target-denied": "The controlled patch targets an undeclared path.",
        "stage-failed": "An isolated source stage could not be created.",
        "build-command-denied": "A build command is not explicitly allowed.",
        "tool-identity-mismatch": "A build tool identity does not match the manifest.",
        "build-failed": "An isolated build step failed.",
        "output-invalid": "The declared build output is missing or invalid.",
        "reproducibility-mismatch": "The independent build outputs differ.",
        "result-write-failed": "The rebuild result could not be written safely.",
    }

    def __init__(self, code: str) -> None:
        """Create an error without embedding restricted exception or path text."""
        if code not in self._MESSAGES:
            raise ValueError("unknown rebuild error code")
        self.code = code
        super().__init__(self._MESSAGES[code])


@dataclass(frozen=True, slots=True)
class BuildStep:
    """One bounded, no-shell build command from an explicit tool allowlist."""

    executable: str
    arguments: tuple[str, ...]
    working_directory: str
    timeout_seconds: int

    def canonical(self) -> dict[str, Any]:
        """Return the stable JSON representation used for evidence hashing."""
        return {
            "arguments": list(self.arguments),
            "executable": self.executable,
            "timeoutSeconds": self.timeout_seconds,
            "workingDirectory": self.working_directory,
        }


@dataclass(frozen=True, slots=True)
class RebuildManifest:
    """Validated immutable declaration of one controlled derivative build."""

    source_revision: str
    source_tree: str
    patch_sha256: str
    git_sha256: str
    tool_sha256: tuple[tuple[str, str], ...]
    allowed_patch_paths: tuple[str, ...]
    steps: tuple[BuildStep, ...]
    output_path: str
    environment: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]

    @classmethod
    def from_json_bytes(cls, content: bytes) -> "RebuildManifest":
        """Parse strict UTF-8 JSON and reject duplicate keys or unknown fields."""
        try:
            text = content.decode("utf-8")

            def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in items:
                    if key in result:
                        _fail("manifest-invalid")
                    result[key] = value
                return result

            raw = json.loads(text, object_pairs_hook=pairs)
        except RebuildError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError):
            _fail("manifest-invalid")
        if not isinstance(raw, dict) or set(raw) != _MANIFEST_FIELDS:
            _fail("manifest-invalid")
        if raw["schemaVersion"] != 1:
            _fail("manifest-invalid")
        revision = _require_string(raw["sourceRevision"])
        tree = _require_string(raw["sourceTree"])
        patch_digest = _require_string(raw["patchSha256"])
        if not _GIT_ID_RE.fullmatch(revision) or not _GIT_ID_RE.fullmatch(tree):
            _fail("manifest-invalid")
        if not _DIGEST_RE.fullmatch(patch_digest):
            _fail("manifest-invalid")

        allowed_raw = raw["allowedPatchPaths"]
        if not isinstance(allowed_raw, list) or not allowed_raw:
            _fail("manifest-invalid")
        allowed = tuple(_safe_relative_path(_require_string(value)) for value in allowed_raw)
        if len(set(allowed)) != len(allowed):
            _fail("manifest-invalid")

        steps_raw = raw["steps"]
        if not isinstance(steps_raw, list) or not steps_raw:
            _fail("manifest-invalid")
        steps = tuple(_parse_step(value) for value in steps_raw)
        git_digest = _require_string(raw["gitSha256"])
        if not _DIGEST_RE.fullmatch(git_digest):
            _fail("manifest-invalid")
        tool_digests = _parse_digest_map(raw["toolSha256"])
        if set(dict(tool_digests)) != {step.executable for step in steps}:
            _fail("manifest-invalid")
        output = _safe_relative_path(_require_string(raw["outputPath"]))
        environment = _parse_string_map(raw["environment"], environment=True)
        metadata = _parse_string_map(raw["metadata"], environment=False)
        return cls(
            revision, tree, patch_digest, git_digest, tool_digests,
            allowed, steps, output, environment, metadata,
        )

    def canonical(self) -> dict[str, Any]:
        """Return a deterministic schema-versioned representation."""
        return {
            "allowedPatchPaths": list(self.allowed_patch_paths),
            "environment": dict(self.environment),
            "gitSha256": self.git_sha256,
            "metadata": dict(self.metadata),
            "outputPath": self.output_path,
            "patchSha256": self.patch_sha256,
            "schemaVersion": 1,
            "sourceRevision": self.source_revision,
            "sourceTree": self.source_tree,
            "steps": [step.canonical() for step in self.steps],
            "toolSha256": dict(self.tool_sha256),
        }

    @property
    def digest(self) -> str:
        """Return the SHA-256 identity of the canonical manifest."""
        return _sha256(_canonical_json(self.canonical()))


@dataclass(frozen=True, slots=True)
class RebuildResult:
    """Public-safe evidence from two matching independent builds."""

    manifest_sha256: str
    source_revision: str
    source_tree: str
    patch_sha256: str
    git_sha256: str
    tool_sha256: tuple[tuple[str, str], ...]
    steps_sha256: str
    attempt_digests: tuple[str, str]
    artifact_sha256: str
    metadata: tuple[tuple[str, str], ...]

    def canonical(self) -> dict[str, Any]:
        """Return the result contract without host paths or runtime claims."""
        return {
            "artifactSha256": self.artifact_sha256,
            "attemptDigests": list(self.attempt_digests),
            "gitSha256": self.git_sha256,
            "manifestSha256": self.manifest_sha256,
            "metadata": dict(self.metadata),
            "patchSha256": self.patch_sha256,
            "reproducible": True,
            "schemaVersion": 1,
            "sourceRevision": self.source_revision,
            "sourceTree": self.source_tree,
            "stepsSha256": self.steps_sha256,
            "toolSha256": dict(self.tool_sha256),
        }

    def to_json_bytes(self) -> bytes:
        """Serialize canonical JSON suitable for atomic evidence writing."""
        return _canonical_json(self.canonical()) + b"\n"


class ControlledRebuilder:
    """Verify, stage, patch, and rebuild exact sources without executing output."""

    def __init__(self, git_executable: Path, tools: Mapping[str, Path]) -> None:
        """Bind logical tool names to reviewed absolute host executables."""
        self._git = _validated_executable(git_executable)
        if not tools:
            _fail("build-command-denied")
        checked: dict[str, Path] = {}
        for name, path in tools.items():
            if not _TOOL_RE.fullmatch(name) or name in checked:
                _fail("build-command-denied")
            checked[name] = _validated_executable(path)
        self._tools = checked

    def rebuild(
        self,
        manifest: RebuildManifest,
        source: Path,
        patch: Path,
        work_root: Path,
    ) -> RebuildResult:
        """Perform two clean builds and return evidence only when outputs match."""
        if source.is_symlink() or patch.is_symlink():
            _fail("patch-invalid")
        try:
            source = source.resolve(strict=True)
            patch = patch.resolve(strict=True)
        except OSError:
            _fail("patch-invalid")
        if not source.is_dir() or not patch.is_file():
            _fail("patch-invalid")
        if _sha256_file(patch, error_code="patch-invalid") != manifest.patch_sha256:
            _fail("patch-digest-mismatch")
        if _sha256_file(self._git, error_code="tool-identity-mismatch") != manifest.git_sha256:
            _fail("tool-identity-mismatch")
        declared_tools = dict(manifest.tool_sha256)
        for name in {step.executable for step in manifest.steps}:
            executable = self._tools.get(name)
            if executable is None:
                _fail("build-command-denied")
            if _sha256_file(executable, error_code="tool-identity-mismatch") != declared_tools[name]:
                _fail("tool-identity-mismatch")
        self._verify_source(manifest, source)
        try:
            patch_bytes = patch.read_bytes()
        except OSError:
            _fail("patch-invalid")
        _validate_patch(patch_bytes, set(manifest.allowed_patch_paths))

        work_root = _new_work_root(work_root)
        try:
            digests = tuple(
                self._attempt(manifest, source, patch, work_root / f"attempt-{label}", label)
                for label in ("a", "b")
            )
            if digests[0] != digests[1]:
                _fail("reproducibility-mismatch")
            steps_digest = _sha256(
                _canonical_json([step.canonical() for step in manifest.steps])
            )
            return RebuildResult(
                manifest.digest, manifest.source_revision, manifest.source_tree,
                manifest.patch_sha256, manifest.git_sha256, manifest.tool_sha256,
                steps_digest, (digests[0], digests[1]), digests[0], manifest.metadata,
            )
        except BaseException:
            shutil.rmtree(work_root, ignore_errors=True)
            raise

    def _verify_source(self, manifest: RebuildManifest, source: Path) -> None:
        """Verify the checkout points at the exact declared commit and tree."""
        revision = self._git_text(source, "rev-parse", "HEAD^{commit}")
        tree = self._git_text(source, "rev-parse", "HEAD^{tree}")
        if revision != manifest.source_revision or tree != manifest.source_tree:
            _fail("source-identity-mismatch")

    def _git_text(self, source: Path, *arguments: str) -> str:
        """Run a bounded read-only Git query and return one stripped line."""
        try:
            completed = subprocess.run(
                [str(self._git), "-C", str(source), *arguments],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={}, check=True, timeout=30,
            )
            value = completed.stdout.decode("ascii").strip()
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
            _fail("source-identity-mismatch")
        return value

    def _attempt(
        self, manifest: RebuildManifest, source: Path, patch: Path, stage: Path, label: str
    ) -> str:
        """Create one fresh stage, apply the patch, build, and hash output."""
        stage.mkdir(mode=0o700)
        archive = stage.parent / f"source-{label}.tar"
        try:
            subprocess.run(
                [str(self._git), "-C", str(source), "archive", "--format=tar",
                 f"--output={archive}", manifest.source_revision],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={}, check=True, timeout=60,
            )
            _extract_safe_archive(archive, stage)
        except RebuildError:
            raise
        except (OSError, subprocess.SubprocessError, tarfile.TarError):
            _fail("stage-failed")
        finally:
            archive.unlink(missing_ok=True)

        for relative in manifest.allowed_patch_paths:
            _require_regular_ancestry(
                stage, relative, leaf_may_be_missing=True, error_code="patch-invalid"
            )
        self._apply_patch(stage, patch)
        for relative in manifest.allowed_patch_paths:
            _require_regular_ancestry(
                stage, relative, leaf_may_be_missing=False, error_code="patch-invalid"
            )

        environment = dict(manifest.environment)
        for step in manifest.steps:
            executable = self._tools.get(step.executable)
            if executable is None:
                _fail("build-command-denied")
            cwd = _resolve_directory(stage, step.working_directory)
            arguments = [_expand_argument(value, stage, label) for value in step.arguments]
            try:
                subprocess.run(
                    [str(executable), *arguments], cwd=cwd, env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True, check=True,
                    timeout=step.timeout_seconds,
                )
            except (OSError, subprocess.SubprocessError):
                _fail("build-failed")
        return _sha256_file(_resolve_regular_file(stage, manifest.output_path))

    def _apply_patch(self, stage: Path, patch: Path) -> None:
        """Check the complete patch before applying it to one isolated stage."""
        base = [str(self._git), "-C", str(stage), "apply", "--whitespace=error-all"]
        for extra in (["--check", str(patch)], [str(patch)]):
            try:
                subprocess.run(
                    [*base, *extra], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, env={}, check=True, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                _fail("patch-invalid")


def load_manifest(path: Path) -> RebuildManifest:
    """Load one manifest from a regular, non-symbolic-link file."""
    if path.is_symlink():
        _fail("manifest-invalid")
    try:
        resolved = path.resolve(strict=True)
        content = resolved.read_bytes()
    except OSError:
        _fail("manifest-invalid")
    if not resolved.is_file():
        _fail("manifest-invalid")
    return RebuildManifest.from_json_bytes(content)


def write_result_exclusive(path: Path, result: RebuildResult) -> None:
    """Atomically create a new result file without replacing any existing path."""
    temporary: Path | None = None
    try:
        if path.exists() or path.is_symlink():
            _fail("result-write-failed")
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir():
            _fail("result-write-failed")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".rebuild-", dir=parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(result.to_json_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, parent / path.name, follow_symlinks=False)
        temporary.unlink()
        temporary = None
        directory = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except RebuildError:
        raise
    except OSError:
        _fail("result-write-failed")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _parse_step(value: Any) -> BuildStep:
    """Validate one raw build-step object."""
    if not isinstance(value, dict) or set(value) != _STEP_FIELDS:
        _fail("manifest-invalid")
    executable = _require_string(value["executable"])
    if not _TOOL_RE.fullmatch(executable):
        _fail("manifest-invalid")
    arguments_raw = value["arguments"]
    if not isinstance(arguments_raw, list):
        _fail("manifest-invalid")
    arguments: list[str] = []
    for raw in arguments_raw:
        argument = _require_string(raw)
        if "\x00" in argument or len(argument) > 4096:
            _fail("manifest-invalid")
        remainder = argument
        for placeholder in _ALLOWED_PLACEHOLDERS:
            remainder = remainder.replace(placeholder, "")
        if "{" in remainder or "}" in remainder:
            _fail("manifest-invalid")
        arguments.append(argument)
    working = _safe_relative_path(_require_string(value["workingDirectory"]), allow_dot=True)
    timeout = value["timeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        _fail("manifest-invalid")
    return BuildStep(executable, tuple(arguments), working, timeout)


def _parse_string_map(value: Any, *, environment: bool) -> tuple[tuple[str, str], ...]:
    """Validate and sort a public-safe string map."""
    if not isinstance(value, dict):
        _fail("manifest-invalid")
    result: list[tuple[str, str]] = []
    for key, raw in value.items():
        item = _require_string(raw)
        if not _NAME_RE.fullmatch(key) or _SENSITIVE_NAME_RE.search(key):
            _fail("manifest-invalid")
        if (
            not item
            or len(item) > 4096
            or "\x00" in item
            or _PRIVATE_IPV4_RE.search(item)
            or _PRIVATE_IPV6_RE.search(item)
            or _SENSITIVE_VALUE_RE.search(item)
            or _URI_USERINFO_RE.search(item)
        ):
            _fail("manifest-invalid")
        if not environment and not _META_RE.fullmatch(item):
            _fail("manifest-invalid")
        result.append((key, item))
    return tuple(sorted(result))


def _parse_digest_map(value: Any) -> tuple[tuple[str, str], ...]:
    """Validate logical tool names mapped to exact executable digests."""
    if not isinstance(value, dict) or not value:
        _fail("manifest-invalid")
    result: list[tuple[str, str]] = []
    for key, raw in value.items():
        digest = _require_string(raw)
        if not _TOOL_RE.fullmatch(key) or not _DIGEST_RE.fullmatch(digest):
            _fail("manifest-invalid")
        result.append((key, digest))
    return tuple(sorted(result))


def _validate_patch(content: bytes, allowed: set[str]) -> None:
    """Validate a text-only, in-place Git patch and all target paths."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        _fail("patch-invalid")
    forbidden = (
        "GIT binary patch", "Binary files ", "new file mode ", "deleted file mode ",
        "old mode ", "new mode ", "rename from ", "rename to ", "copy from ",
        "copy to ", "similarity index ",
    )
    if any(line.startswith(forbidden) for line in text.splitlines()):
        _fail("patch-invalid")
    targets: list[str] = []
    old_path: str | None = None
    new_path: str | None = None

    def finish_block() -> None:
        """Require one complete in-place path tuple for the current diff block."""
        if not targets:
            return
        current = targets[-1]
        if old_path != current or new_path != current:
            _fail("patch-invalid")
        if current not in allowed:
            _fail("patch-target-denied")

    for line in text.splitlines():
        if line.startswith("diff --git "):
            finish_block()
            match = re.fullmatch(r"diff --git a/([^\s]+) b/([^\s]+)", line)
            if not match or match.group(1) != match.group(2):
                _fail("patch-invalid")
            targets.append(_safe_relative_path(match.group(2)))
            old_path = None
            new_path = None
        elif line.startswith("--- ") or line.startswith("+++ "):
            if not targets:
                _fail("patch-invalid")
            prefix = "a/" if line.startswith("--- ") else "b/"
            value = line[4:].split("\t", 1)[0]
            if not value.startswith(prefix):
                _fail("patch-invalid")
            header_path = _safe_relative_path(value[2:])
            if header_path not in allowed:
                _fail("patch-target-denied")
            if line.startswith("--- "):
                if old_path is not None:
                    _fail("patch-invalid")
                old_path = header_path
            else:
                if new_path is not None:
                    _fail("patch-invalid")
                new_path = header_path
    if not targets or len(targets) != len(set(targets)):
        _fail("patch-invalid")
    finish_block()


def _extract_safe_archive(archive: Path, destination: Path) -> None:
    """Extract only regular files and directories with safe relative paths."""
    with tarfile.open(archive, "r:") as stream:
        members = stream.getmembers()
        for member in members:
            _safe_relative_path(member.name)
            if not (member.isfile() or member.isdir()):
                _fail("stage-failed")
        stream.extractall(destination, members=members, filter="data")


def _new_work_root(path: Path) -> Path:
    """Create one new work root below its resolved existing parent."""
    if path.exists() or path.is_symlink():
        _fail("stage-failed")
    try:
        parent = path.parent.resolve(strict=True)
        root = parent / path.name
        root.mkdir(mode=0o700)
    except OSError:
        _fail("stage-failed")
    return root


def _validated_executable(path: Path) -> Path:
    """Return a reviewed absolute regular executable or fail closed."""
    if not path.is_absolute() or path.is_symlink():
        _fail("build-command-denied")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError:
        _fail("build-command-denied")
    if not stat.S_ISREG(mode) or not os.access(resolved, os.X_OK):
        _fail("build-command-denied")
    return resolved


def _resolve_directory(stage: Path, relative: str) -> Path:
    """Resolve a declared working directory without following an escape."""
    target = stage if relative == "." else stage / relative
    try:
        resolved = target.resolve(strict=True)
    except OSError:
        _fail("build-failed")
    if not resolved.is_dir() or not resolved.is_relative_to(stage):
        _fail("build-failed")
    return resolved


def _resolve_regular_file(stage: Path, relative: str) -> Path:
    """Resolve a declared output as a regular non-symbolic file within a stage."""
    _require_regular_ancestry(
        stage, relative, leaf_may_be_missing=False, error_code="output-invalid"
    )
    path = stage / relative
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        _fail("output-invalid")
    if path.is_symlink() or not resolved.is_relative_to(stage) or not resolved.is_file():
        _fail("output-invalid")
    return resolved


def _require_regular_ancestry(
    stage: Path,
    relative: str,
    *,
    leaf_may_be_missing: bool,
    error_code: str,
) -> None:
    """Reject symbolic-link components for a path rooted in a stage."""
    current = stage
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current /= part
        is_leaf = index == len(parts) - 1
        if not current.exists():
            if is_leaf and leaf_may_be_missing:
                return
            _fail(error_code)
        if current.is_symlink():
            _fail(error_code)


def _expand_argument(value: str, stage: Path, attempt: str) -> str:
    """Expand only the two declared non-shell placeholders."""
    return value.replace("{stage}", str(stage)).replace("{attempt}", attempt)


def _safe_relative_path(value: str, *, allow_dot: bool = False) -> str:
    """Normalize a portable relative path and reject traversal or ambiguity."""
    if not value or "\x00" in value or "\\" in value:
        _fail("manifest-invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        if allow_dot and value == ".":
            return value
        _fail("manifest-invalid")
    if str(path) != value:
        _fail("manifest-invalid")
    return value


def _require_string(value: Any) -> str:
    """Return a non-empty string or reject the manifest."""
    if not isinstance(value, str) or not value:
        _fail("manifest-invalid")
    return value


def _canonical_json(value: Any) -> bytes:
    """Encode deterministic compact UTF-8 JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(content: bytes) -> str:
    """Return a prefixed lowercase SHA-256 digest."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path, *, error_code: str = "output-invalid") -> str:
    """Hash a file without loading the complete output into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        _fail(error_code)
    return "sha256:" + digest.hexdigest()


def _fail(code: str) -> NoReturn:
    """Raise one stable public-safe rebuild failure."""
    raise RebuildError(code)
