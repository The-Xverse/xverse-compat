"""Validation and owned admission checks for the Thesis Lite Phase 4 XDL descriptors.

The platform (`xverse_xdl`) validates the XDL graph against the core schemas and the runtime
compatibility Profile 0.2 and derives the catalog. This module adds only the admission rules the
schema does not express (committed revisions, observable readiness wording, declared dependencies,
stream traceability, digest equality with the pins) and fails closed with stable codes. It never
starts a process, opens a socket, or discovers anything on the host.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from xverse_xdl import (
    CatalogEntry,
    LifecyclePlan,
    NormalizedResource,
    RUNTIME_PROFILE_NAMESPACE,
    ValidationResult,
    build_lifecycle_plan,
    derive_catalog,
    validate_files,
)

from .selection import ArtifactSelectionRecord

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTOR_DIR = ROOT / "xdl" / "descriptors" / "aeb-sim"
PROFILE_SCHEMA_RELATIVE = Path("xdl") / "profiles" / "runtime-compatibility-v0.2.schema.json"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_RELEASE = re.compile(r"^release:[A-Za-z0-9][A-Za-z0-9+._-]*$")
_DURATION = re.compile(
    r"(?i)\b(?:sleep|wait|delay)\b|\b\d+(?:\.\d+)?\s*(?:s|sec|secs|seconds|ms|milliseconds|min|minutes)\b"
)
_GAP_BLOCKER = "XVERSE-PLAN-THESIS-{gap}"


class DescriptorError(RuntimeError):
    """Stable, public-safe failure raised by the owned descriptor admission rules."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure.

        @param code Stable code of the form ``XVERSE-COMPAT-DESCRIPTOR-<REASON>``.
        @param message Public-safe explanation.
        """

        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class DescriptorAdmission:
    """Result of validating the descriptor graph and applying the owned rules."""

    validation: ValidationResult
    entries: tuple[CatalogEntry, ...]
    plans: tuple[LifecyclePlan, ...]


def descriptor_paths(directory: Path = DESCRIPTOR_DIR) -> tuple[Path, ...]:
    """Return the descriptor resource files of ``directory`` in stable order.

    @param directory Folder holding ``*.xdl.yaml`` resources.
    @return Sorted absolute paths; never scans outside ``directory``.
    """

    return tuple(sorted(Path(directory).glob("*.xdl.yaml")))


def default_platform_root() -> Path:
    """Return the sibling platform checkout used for schema validation (``../xverse-platform``)."""

    return ROOT.parent / "xverse-platform"


def validate_descriptors(paths: Sequence[Path], platform_root: Path) -> ValidationResult:
    """Validate descriptor files with the platform core schemas and Profile 0.2.

    @param paths Resource files (System, Components, Deployment, Profile).
    @param platform_root Pinned platform checkout providing the Profile schema.
    @return The platform validation result (diagnostics and normalized resources).
    """

    schema = Path(platform_root) / PROFILE_SCHEMA_RELATIVE
    return validate_files(tuple(Path(item) for item in paths), profile_schema_paths=(schema,))


def _mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` when it is a mapping, else an empty mapping."""

    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    """Return ``value`` when it is a non-string sequence, else an empty tuple."""

    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def check_owned_rules(
    resources: Sequence[NormalizedResource],
    entries: Sequence[CatalogEntry],
    record: ArtifactSelectionRecord,
) -> None:
    """Apply the admission rules the platform schema does not cover; fail closed on the first violation.

    @param resources Normalized resources from a valid platform validation.
    @param entries Catalog entries derived from those resources.
    @param record Validated selection record whose pins and streams the descriptors must match.
    @raises DescriptorError With a stable code naming the violated rule.
    """

    code = "XVERSE-COMPAT-DESCRIPTOR"
    for resource in resources:
        if resource.identity.kind != "Component":
            continue
        revision = str(_mapping(resource.provenance).get("revision", ""))
        if not (_COMMIT.match(revision) or _RELEASE.match(revision)):
            raise DescriptorError(f"{code}-REVISION", f"component {resource.identity.uri} provenance revision is neither a 40-hex commit nor release:<id>")
    pin_digests = {pin.digest for pin in record.pins if pin.digest}
    unavailable_pins = {pin.id for pin in record.pins if pin.availability != "present"}
    streams = {item.stream: item for item in record.streams}
    binding_ids: set[str] = set()
    claimed: dict[str, str] = {}
    deployments = [item for item in resources if item.identity.kind == "Deployment"]
    for deployment in deployments:
        bindings = _sequence(deployment.content.get("bindings"))
        binding_ids |= {str(_mapping(item).get("id")) for item in bindings}
    for deployment in deployments:
        for raw in _sequence(deployment.content.get("bindings")):
            binding = _mapping(raw)
            binding_id = str(binding.get("id"))
            payload = _mapping(_mapping(binding.get("extensions")).get(RUNTIME_PROFILE_NAMESPACE))
            if not payload:
                continue
            observe = next((_mapping(item) for item in _sequence(payload.get("actions")) if _mapping(item).get("phase") == "observe"), {})
            condition = str(observe.get("condition", ""))
            if _DURATION.search(condition):
                raise DescriptorError(f"{code}-READINESS-DURATION", f"binding {binding_id} declares a duration, not observable evidence, as readiness")
            parameters = _mapping(binding.get("parameterValues"))
            for dependency in _sequence(parameters.get("dependsOnBindings")):
                if str(dependency) not in binding_ids:
                    raise DescriptorError(f"{code}-DEPENDENCY", f"binding {binding_id} depends on unknown binding {dependency!r}")
            blockers = {str(item) for item in _sequence(payload.get("planningBlockers"))}
            for stream_name in _sequence(parameters.get("suppliesStreams")):
                stream = streams.get(str(stream_name))
                if stream is None or stream.disposition != "supplied":
                    raise DescriptorError(f"{code}-STREAM-TRACE", f"binding {binding_id} claims stream {stream_name!r} that the selection record does not mark supplied")
                if str(stream_name) in claimed:
                    raise DescriptorError(f"{code}-STREAM-TRACE", f"stream {stream_name!r} is claimed by two bindings")
                claimed[str(stream_name)] = binding_id
                if any(dep in unavailable_pins for dep in stream.depends_on) and _GAP_BLOCKER.format(gap="G1") not in blockers:
                    raise DescriptorError(f"{code}-BLOCKER", f"binding {binding_id} supplies {stream_name!r} through a NOT_AVAILABLE pin without {_GAP_BLOCKER.format(gap='G1')}")
    for stream in record.streams:
        if stream.disposition == "supplied" and stream.stream not in claimed:
            raise DescriptorError(f"{code}-STREAM-UNCLAIMED", f"supplied stream {stream.stream!r} has no descriptor binding")
    for entry in entries:
        if not set(entry.artifact_digests) <= pin_digests:
            raise DescriptorError(f"{code}-ARTIFACT-DIGEST", f"catalog entry {entry.identity} binds a digest absent from the selection pins")


def admit_descriptors(
    record: ArtifactSelectionRecord,
    *,
    paths: Sequence[Path] | None = None,
    platform_root: Path | None = None,
) -> DescriptorAdmission:
    """Validate the descriptor graph, derive its catalog and plans, and apply the owned rules.

    @param record Validated selection record.
    @param paths Descriptor files; defaults to ``xdl/descriptors/aeb-sim/*.xdl.yaml``.
    @param platform_root Pinned platform checkout; defaults to the sibling ``xverse-platform``.
    @return Validation result, catalog entries and lifecycle plans. Plans are never execution-eligible
            and, while any planning blocker is declared, not plannable (``is_plannable`` is false).
    @raises DescriptorError On a platform validation failure, a catalog diagnostic, or an owned rule.
    """

    files = tuple(paths) if paths is not None else descriptor_paths()
    root = Path(platform_root) if platform_root is not None else default_platform_root()
    validation = validate_descriptors(files, root)
    if not validation.is_valid:
        codes = sorted({item.code for item in validation.diagnostics})
        raise DescriptorError("XVERSE-COMPAT-DESCRIPTOR-VALIDATION", f"platform validation failed at its schema or binding gates: {codes}")
    catalog = derive_catalog(validation.resources)
    if not catalog.is_valid:
        codes = sorted({item.code for item in catalog.diagnostics})
        raise DescriptorError("XVERSE-COMPAT-DESCRIPTOR-CATALOG", f"catalog derivation failed: {codes}")
    check_owned_rules(validation.resources, catalog.entries, record)
    plans = tuple(build_lifecycle_plan(entry) for entry in catalog.entries)
    if any(plan.execution_eligible for plan in plans):
        raise DescriptorError("XVERSE-COMPAT-DESCRIPTOR-ELIGIBLE", "a descriptor plan is execution-eligible without a permit")
    if any(not plan.blockers for plan in plans):
        raise DescriptorError("XVERSE-COMPAT-DESCRIPTOR-BLOCKER", "a descriptor plan declares no planning blocker although no selected artifact has been executed")
    return DescriptorAdmission(validation=validation, entries=catalog.entries, plans=plans)
