"""Artifact-selection record and artifact pins for the Thesis Lite Phase 4 descriptors.

The record names, for every stream the declared AEB needs, which selected artifact supplies it, which
owned adapter derives it, or why it is blocked. Pins identify each selected artifact by committed
revision and runnable digest. Loading fails closed with a stable code; digest verification is a pure
read of local files and never raises on an absent file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

REQUIRED_STREAMS: frozenset[str] = frozenset({
    "camera", "radar", "vehicleSpeed", "wheelSpeedEscStatus", "brakeStatus",
    "brakeActuation", "groundTruth", "scenarioControl",
})
DISPOSITIONS: frozenset[str] = frozenset({"supplied", "adapter", "blocked"})
AVAILABILITY: frozenset[str] = frozenset({"present", "NOT_AVAILABLE"})
_COMMIT_REF = re.compile(r"@[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GAP = re.compile(r"^G[0-9]+$")


class SelectionError(RuntimeError):
    """Stable, public-safe failure raised while loading a selection record."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure.

        @param code Stable code of the form ``XVERSE-COMPAT-SELECTION-<REASON>``.
        @param message Public-safe explanation without host-private data.
        """

        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ArtifactPin:
    """Identity of one selected artifact: committed source and runnable digest."""

    id: str
    artifact_kind: str
    version: str
    source_ref: str
    availability: str
    license: str
    classification: str
    toolchain: str
    digest: str | None = None
    digest_command: str | None = None
    local_path: str | None = None
    reason: str | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class StreamDisposition:
    """How one required AEB stream is served by the selection."""

    stream: str
    disposition: str
    supplier: str | None = None
    interface: str | None = None
    blocker: str | None = None
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactSelectionRecord:
    """The validated selection record."""

    record_version: str
    aeb_source: str
    platform_revision: str
    streams: tuple[StreamDisposition, ...]
    pins: tuple[ArtifactPin, ...]
    adapters: tuple[str, ...]
    not_selected: tuple[str, ...]
    decisions: tuple[str, ...] = field(default_factory=tuple)

    def pin(self, pin_id: str) -> ArtifactPin:
        """Return the pin with ``pin_id``.

        @param pin_id Pin identifier referenced by a stream disposition.
        @return The matching pin.
        @raises KeyError If no pin has that identifier.
        """

        for pin in self.pins:
            if pin.id == pin_id:
                return pin
        raise KeyError(pin_id)


def _string(value: Any, code: str, what: str) -> str:
    """Return ``value`` as a non-empty string or fail with ``code``."""

    if not isinstance(value, str) or not value:
        raise SelectionError(code, f"{what} must be a non-empty string")
    return value


def _strings(value: Any, code: str, what: str) -> tuple[str, ...]:
    """Return ``value`` as a tuple of non-empty strings or fail with ``code``."""

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise SelectionError(code, f"{what} must be a list of strings")
    return tuple(_string(item, code, what) for item in value)


def _pin(raw: Mapping[str, Any]) -> ArtifactPin:
    """Validate one raw pin mapping."""

    code = "XVERSE-COMPAT-SELECTION-PIN"
    pin_id = _string(raw.get("id"), code, "pin id")
    source_ref = _string(raw.get("sourceRef"), f"{code}-SOURCE", f"pin {pin_id!r} sourceRef")
    availability = _string(raw.get("availability"), f"{code}-AVAILABILITY", f"pin {pin_id!r} availability")
    if availability not in AVAILABILITY:
        raise SelectionError(f"{code}-AVAILABILITY", f"pin {pin_id!r} availability is not one of {sorted(AVAILABILITY)}")
    digest = raw.get("digest")
    if availability == "present":
        if not isinstance(digest, str) or not _DIGEST.match(digest):
            raise SelectionError(f"{code}-DIGEST", f"pin {pin_id!r} needs a sha256:<64 hex> digest")
        _string(raw.get("digestCommand"), f"{code}-DIGEST-COMMAND", f"pin {pin_id!r} digestCommand")
        if not _COMMIT_REF.search(source_ref) and not raw.get("releaseArtifact"):
            raise SelectionError(f"{code}-FLOATING", f"pin {pin_id!r} sourceRef names no 40-hex commit and no release artifact")
    else:
        if digest is not None:
            raise SelectionError(f"{code}-DIGEST", f"pin {pin_id!r} is NOT_AVAILABLE and must not carry a digest")
        _string(raw.get("reason"), f"{code}-REASON", f"pin {pin_id!r} reason")
    if _COMMIT_REF.search(source_ref) is None and "@" in source_ref:
        raise SelectionError(f"{code}-FLOATING", f"pin {pin_id!r} sourceRef revision is not a 40-hex commit")
    return ArtifactPin(
        id=pin_id,
        artifact_kind=_string(raw.get("artifactKind"), code, f"pin {pin_id!r} artifactKind"),
        version=_string(raw.get("version"), code, f"pin {pin_id!r} version"),
        source_ref=source_ref,
        availability=availability,
        license=_string(raw.get("license"), code, f"pin {pin_id!r} license"),
        classification=_string(raw.get("classification"), code, f"pin {pin_id!r} classification"),
        toolchain=_string(raw.get("toolchain"), code, f"pin {pin_id!r} toolchain"),
        digest=digest if isinstance(digest, str) else None,
        digest_command=raw.get("digestCommand"),
        local_path=raw.get("localPath"),
        reason=raw.get("reason"),
        limitations=_strings(raw.get("limitations"), code, f"pin {pin_id!r} limitations"),
    )


def _stream(raw: Mapping[str, Any], pin_ids: frozenset[str], adapter_ids: frozenset[str]) -> StreamDisposition:
    """Validate one raw stream disposition against the known suppliers."""

    code = "XVERSE-COMPAT-SELECTION"
    stream = _string(raw.get("stream"), f"{code}-STREAM", "stream")
    if stream not in REQUIRED_STREAMS:
        raise SelectionError(f"{code}-STREAM-UNKNOWN", f"stream {stream!r} is not a required AEB stream")
    disposition = _string(raw.get("disposition"), f"{code}-DISPOSITION", f"stream {stream!r} disposition")
    if disposition not in DISPOSITIONS:
        raise SelectionError(f"{code}-DISPOSITION", f"stream {stream!r} disposition is not one of {sorted(DISPOSITIONS)}")
    supplier = raw.get("supplier")
    blocker = raw.get("blocker")
    if disposition == "supplied":
        if supplier not in pin_ids:
            raise SelectionError(f"{code}-SUPPLIER-MISSING", f"supplied stream {stream!r} names no selected pin")
        _string(raw.get("interface"), f"{code}-INTERFACE", f"stream {stream!r} interface")
    elif disposition == "adapter":
        if supplier not in adapter_ids:
            raise SelectionError(f"{code}-SUPPLIER-MISSING", f"adapter stream {stream!r} names no declared adapter")
    if disposition == "blocked" or (disposition == "adapter" and blocker is not None):
        if not isinstance(blocker, str) or not _GAP.match(blocker):
            raise SelectionError(f"{code}-BLOCKER-MISSING", f"stream {stream!r} needs a gap id G<n> as blocker")
    elif blocker is not None:
        raise SelectionError(f"{code}-BLOCKER-UNEXPECTED", f"supplied stream {stream!r} must not carry a blocker")
    return StreamDisposition(
        stream=stream,
        disposition=disposition,
        supplier=supplier if isinstance(supplier, str) else None,
        interface=raw.get("interface"),
        blocker=blocker if isinstance(blocker, str) else None,
        depends_on=_strings(raw.get("dependsOn"), f"{code}-DEPENDS", f"stream {stream!r} dependsOn"),
    )


def load_selection_record(path: Path) -> ArtifactSelectionRecord:
    """Load and validate a selection record, failing closed on the first violation.

    @param path JSON file with the record.
    @return The validated record.
    @raises SelectionError On any structural or consistency violation.
    """

    code = "XVERSE-COMPAT-SELECTION"
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SelectionError(f"{code}-READ", "selection record is unreadable or not JSON") from error
    if not isinstance(raw, Mapping):
        raise SelectionError(f"{code}-READ", "selection record is not a JSON object")
    pins = tuple(_pin(item) for item in raw.get("pins") or ())
    pin_ids = frozenset(pin.id for pin in pins)
    if len(pin_ids) != len(pins):
        raise SelectionError(f"{code}-PIN-DUPLICATE", "pin identifiers are not unique")
    adapters = _strings(raw.get("adapters"), f"{code}-ADAPTERS", "adapters")
    adapter_ids = frozenset(adapters)
    if adapter_ids & pin_ids:
        raise SelectionError(f"{code}-ADAPTERS", "an adapter id collides with a pin id")
    streams = tuple(_stream(item, pin_ids, adapter_ids) for item in raw.get("streams") or ())
    seen = [item.stream for item in streams]
    if len(set(seen)) != len(seen):
        raise SelectionError(f"{code}-STREAM-DUPLICATE", "a stream is listed more than once")
    missing = REQUIRED_STREAMS - set(seen)
    if missing:
        raise SelectionError(f"{code}-STREAM-MISSING", f"required streams without disposition: {sorted(missing)}")
    referenced = {item.supplier for item in streams if item.disposition == "supplied"}
    referenced |= {dep for item in streams for dep in item.depends_on}
    unused = pin_ids - referenced
    if unused:
        raise SelectionError(f"{code}-PIN-UNUSED", f"selected pins no stream needs: {sorted(unused)}")
    for item in streams:
        for dep in item.depends_on:
            if dep not in pin_ids and dep not in seen:
                raise SelectionError(f"{code}-DEPENDS", f"stream {item.stream!r} depends on unknown {dep!r}")
    not_selected = _strings(raw.get("notSelected"), f"{code}-NOT-SELECTED", "notSelected")
    if not not_selected:
        raise SelectionError(f"{code}-NOT-SELECTED", "notSelected must name the inspected technologies that were excluded")
    return ArtifactSelectionRecord(
        record_version=_string(raw.get("recordVersion"), f"{code}-VERSION", "recordVersion"),
        aeb_source=_string(raw.get("aebSource"), f"{code}-AEB-SOURCE", "aebSource"),
        platform_revision=_string(raw.get("platformRevision"), f"{code}-PLATFORM", "platformRevision"),
        streams=streams,
        pins=pins,
        adapters=adapters,
        not_selected=not_selected,
        decisions=_strings(raw.get("decisions"), f"{code}-DECISIONS", "decisions"),
    )


def sha256_of(path: Path) -> str:
    """Return the ``sha256:`` digest of a local file, streaming its content."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def verify_pins(record: ArtifactSelectionRecord, root: Path = Path("/")) -> dict[str, str]:
    """Recompute every ``present`` pin's digest from its ``localPath`` below ``root``.

    @param record Validated selection record.
    @param root Directory that absolute ``localPath`` values are resolved under (``/`` on the host).
    @return Mapping pin id to ``match``, ``mismatch``, ``absent`` (file missing), or ``unpinned``
            (NOT_AVAILABLE or no localPath). Never raises for a missing or unreadable file.
    """

    results: dict[str, str] = {}
    for pin in record.pins:
        if pin.availability != "present" or not pin.local_path or not pin.digest:
            results[pin.id] = "unpinned"
            continue
        target = Path(root) / Path(pin.local_path).relative_to("/") if Path(pin.local_path).is_absolute() else Path(root) / pin.local_path
        try:
            results[pin.id] = "match" if sha256_of(target) == pin.digest else "mismatch"
        except OSError:
            results[pin.id] = "absent"
    return results
