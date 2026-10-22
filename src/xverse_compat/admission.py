"""Admission record for the Thesis Lite Phase 4 descriptors (thesis V07) and the platform re-pin.

The record binds, by SHA-256, every input of the phase: the pinned platform source surface and its
``xdl/schemas`` and ``xdl/profiles`` trees, the Phase 1–3 revisions the caller names, the
descriptors with their catalog identities, the selection record and pins (digests recomputed), the
contract table and inventory, the adapter fixtures, and the verification log. It states that
execution authority is absent and lists every open blocker. Building the record also re-pins
``platform-api.lock.json`` to the same platform tree, so the content-lock test and the admission
record cannot disagree. Verification recomputes every hash and fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import load_contract_table
from .descriptors import ROOT, admit_descriptors, descriptor_paths
from .platform_pin import platform_tree_digest
from .selection import load_selection_record, sha256_of, verify_pins

SELECTION = ROOT / "xdl" / "selection" / "aeb-sim-selection.json"
CONTRACTS = ROOT / "xdl" / "selection" / "aeb-sim-contracts.json"
INVENTORY = ROOT / "xdl" / "selection" / "artifact-inventory-20261022.json"
FIXTURES = ROOT / "tests" / "fixtures" / "bridge-samples"
LOCK = ROOT / "platform-api.lock.json"
_TREE_ROOTS = ("xdl/schemas", "xdl/profiles")


class AdmissionError(RuntimeError):
    """Stable, public-safe failure raised when an admission record cannot be built or verified."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure.

        @param code Stable code of the form ``XVERSE-COMPAT-ADMISSION-<REASON>``.
        @param message Public-safe explanation.
        """

        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class PhaseRevisions:
    """Accepted platform revisions of the phases this phase consumes."""

    xdl_lite: str
    argus_lite: str
    maestro_lite: str
    platform_main: str


def tree_digest(root: Path, relative_root: str) -> tuple[int, str]:
    """Return file count and SHA-256 over ``relative_root`` below ``root`` (path + content, sorted)."""

    base = Path(root) / relative_root
    files = sorted(
        (path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return len(files), digest.hexdigest()


def _rel(path: Path) -> str:
    """Return ``path`` relative to the repository root as a POSIX string."""

    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _file_entry(path: Path) -> dict[str, str]:
    """Return a ``{path, sha256}`` entry for a repository file."""

    return {"path": _rel(path), "sha256": sha256_of(path).split(":", 1)[1]}


def build_admission_record(
    *,
    platform_root: Path,
    revisions: PhaseRevisions,
    verification_log: Path,
    verification_summary: Mapping[str, Any],
    output: Path,
    lock_path: Path = LOCK,
    now: datetime | None = None,
    review: Mapping[str, Any] | None = None,
    acceptance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the admission record, write it, and re-pin the platform content lock.

    @param platform_root Pinned platform checkout (read-only).
    @param revisions Full commit ids of the accepted Phase 1–3 deliveries and of platform main.
    @param verification_log Captured output of the owner-side test suite.
    @param verification_summary Mapping with ``command``, ``passed``, ``failed`` and ``suite``.
    @param output Where the record is written (JSON).
    @param lock_path The ``platform-api.lock.json`` to re-pin (a temporary path in tests).
    @param now Timestamp to record; defaults to the current UTC time.
    @param review Separate read-only review verdict to record (``verdict``, ``reference``); ``None`` before review.
    @param acceptance Acceptance decision to record (``decision``, ``basis``, ``date``); ``None`` until accepted.
    @return The record as written.
    @raises AdmissionError When a pin digest does not match the host file, a descriptor is
            rejected, or the platform surface cannot be read.
    """

    code = "XVERSE-COMPAT-ADMISSION"
    record = load_selection_record(SELECTION)
    pin_results = verify_pins(record)
    for pin in record.pins:
        if pin.availability == "present" and pin_results.get(pin.id) != "match":
            raise AdmissionError(f"{code}-PIN", f"pin {pin.id!r} digest does not match the host artifact ({pin_results.get(pin.id)})")
    descriptors = admit_descriptors(record, platform_root=platform_root)
    statements = load_contract_table(CONTRACTS, INVENTORY)
    try:
        file_count, surface = platform_tree_digest(Path(platform_root))
        schemas = tree_digest(Path(platform_root), _TREE_ROOTS[0])
        profiles = tree_digest(Path(platform_root), _TREE_ROOTS[1])
    except OSError as error:
        raise AdmissionError(f"{code}-PLATFORM", "platform source surface is unreadable") from error
    previous_lock = json.loads(Path(lock_path).read_text(encoding="utf-8")) if Path(lock_path).is_file() else None
    if previous_lock is not None and previous_lock.get("treeSha256") == surface and Path(output).is_file():
        # Rebuilding against an already re-pinned lock: keep the superseded pin recorded last time.
        try:
            previous_lock = json.loads(Path(output).read_text(encoding="utf-8")).get("previousPlatformLock")
        except (OSError, ValueError):
            previous_lock = None
    blockers = sorted({item for plan in descriptors.plans for item in plan.blockers} | {f"XVERSE-PLAN-THESIS-{s.gap}" for s in statements if s.gap})
    entries = {entry.binding_id: entry.identity for entry in descriptors.entries}
    data: dict[str, Any] = {
        "schemaVersion": 1,
        "recordedAt": (now or datetime.now(timezone.utc)).isoformat(),
        "platform": {
            "revision": revisions.platform_main,
            "sourceSurfaceFileCount": file_count,
            "sourceSurfaceTreeSha256": surface,
            "schemasTree": {"fileCount": schemas[0], "sha256": schemas[1]},
            "profilesTree": {"fileCount": profiles[0], "sha256": profiles[1]},
            "xdlPackageVersion": "0.4.0",
        },
        "phase1to3": {"xdlLite": revisions.xdl_lite, "argusLite": revisions.argus_lite, "maestroLite": revisions.maestro_lite},
        "selectionRecord": _file_entry(SELECTION),
        "pins": [
            {"id": pin.id, "availability": pin.availability, "digest": pin.digest, "recomputed": pin_results[pin.id]}
            for pin in record.pins
        ],
        "descriptors": [
            {**_file_entry(path), "catalogEntryIds": sorted(entries.values()) if path.name == "deployment.xdl.yaml" else []}
            for path in descriptor_paths()
        ],
        "plans": [
            {"catalogIdentity": plan.catalog_identity, "digest": plan.digest, "blockers": list(plan.blockers),
             "isPlannable": plan.is_plannable, "executionEligible": plan.execution_eligible}
            for plan in descriptors.plans
        ],
        "contracts": {**_file_entry(CONTRACTS), "statements": len(statements),
                      "verified": sum(1 for s in statements if s.status == "verified")},
        "inventory": _file_entry(INVENTORY),
        "fixtures": [_file_entry(path) for path in sorted(FIXTURES.glob("*.jsonl"))],
        "verification": {
            "suite": str(verification_summary.get("suite", "")),
            "command": str(verification_summary.get("command", "")),
            "passed": int(verification_summary.get("passed", 0)),
            "failed": int(verification_summary.get("failed", 0)),
            "logSha256": sha256_of(verification_log).split(":", 1)[1],
            "logPath": _rel(verification_log) if Path(verification_log).resolve().is_relative_to(ROOT.resolve()) else str(verification_log),
        },
        "executionAuthority": "absent",
        "blockers": blockers,
        "previousPlatformLock": previous_lock,
        "review": dict(review) if review is not None else None,
        "acceptance": dict(acceptance) if acceptance is not None else None,
    }
    new_lock = {
        "algorithm": "sha256-path-null-content-null-v1",
        "fileCount": file_count,
        "includedRoots": ["pyproject.toml", "src/xverse_xdl", "xdl/profiles", "xdl/schemas"],
        "package": "xverse-xdl",
        "packageVersion": "0.4.0",
        "sourceKind": "reviewed-sibling-tree",
        "treeSha256": surface,
        "platformRevision": revisions.platform_main,
    }
    Path(lock_path).write_text(json.dumps(new_lock, indent=2) + "\n", encoding="utf-8")
    data["platformLock"] = {"path": _rel(Path(lock_path)) if Path(lock_path).resolve().is_relative_to(ROOT.resolve()) else str(lock_path), **new_lock}
    Path(output).write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return data


_LOCK_KEYS = frozenset({"algorithm", "fileCount", "includedRoots", "package", "packageVersion", "sourceKind", "treeSha256", "platformRevision"})


def verify_admission_record(record_path: Path, platform_root: Path, *, expected_revision: str | None = None) -> dict[str, Any]:
    """Recompute the record's bindings against the current files and fail closed on any difference.

    Checked: the platform source surface and the ``xdl/schemas``/``xdl/profiles`` trees; every listed
    file hash (selection record, contracts, inventory, descriptors, fixtures, verification log);
    the on-disk ``platform-api.lock.json`` against the record's lock (exact key set and values);
    the re-derived descriptor plans (digests and blockers); execution authority; and, when
    ``expected_revision`` is given, the platform revision string. Not checked here: that the
    platform checkout's HEAD is that revision (the admission script checks it with ``git``).

    @param record_path The admission record.
    @param platform_root The platform checkout the record claims to be bound to.
    @param expected_revision Full commit id the record must name as platform main, if known.
    @return The parsed record when every binding holds.
    @raises AdmissionError ``-READ``, ``-PLATFORM``, ``-REVISION``, ``-FILE``, ``-LOCK``, ``-PLAN`` or ``-AUTHORITY``.
    """

    code = "XVERSE-COMPAT-ADMISSION"
    try:
        data = json.loads(Path(record_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AdmissionError(f"{code}-READ", "admission record unreadable or not JSON") from error
    if data.get("executionAuthority") != "absent":
        raise AdmissionError(f"{code}-AUTHORITY", "admission record must state executionAuthority absent")
    file_count, surface = platform_tree_digest(Path(platform_root))
    platform = data.get("platform", {})
    if (file_count, surface) != (platform.get("sourceSurfaceFileCount"), platform.get("sourceSurfaceTreeSha256")):
        raise AdmissionError(f"{code}-PLATFORM", "platform source surface differs from the admitted one")
    for root_key, relative in (("schemasTree", _TREE_ROOTS[0]), ("profilesTree", _TREE_ROOTS[1])):
        count, digest = tree_digest(Path(platform_root), relative)
        if (count, digest) != (platform.get(root_key, {}).get("fileCount"), platform.get(root_key, {}).get("sha256")):
            raise AdmissionError(f"{code}-PLATFORM", f"{relative} tree differs from the admitted one")
    if expected_revision is not None and platform.get("revision") != expected_revision:
        raise AdmissionError(f"{code}-REVISION", "admitted platform revision differs from the expected one")
    entries: list[Mapping[str, Any]] = [data.get("selectionRecord", {}), data.get("contracts", {}), data.get("inventory", {})]
    entries += list(data.get("descriptors", ())) + list(data.get("fixtures", ()))
    verification = data.get("verification", {})
    entries.append({"path": verification.get("logPath", ""), "sha256": verification.get("logSha256")})
    for item in entries:
        raw_path = str(item.get("path", ""))
        path = Path(raw_path) if raw_path.startswith("/") else ROOT / raw_path
        try:
            actual = sha256_of(path).split(":", 1)[1]
        except OSError as error:
            raise AdmissionError(f"{code}-FILE", f"admitted file missing: {raw_path}") from error
        if actual != item.get("sha256"):
            raise AdmissionError(f"{code}-FILE", f"admitted file changed: {raw_path}")
    lock = dict(data.get("platformLock", {}))
    lock_path_value = str(lock.pop("path", ""))
    lock_file = Path(lock_path_value) if lock_path_value.startswith("/") else ROOT / lock_path_value
    try:
        on_disk = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AdmissionError(f"{code}-LOCK", "platform lock file unreadable") from error
    if set(on_disk) != _LOCK_KEYS or on_disk != lock:
        raise AdmissionError(f"{code}-LOCK", "on-disk platform lock differs from the admitted lock")
    if lock.get("treeSha256") != surface or lock.get("fileCount") != file_count or lock.get("platformRevision") != platform.get("revision"):
        raise AdmissionError(f"{code}-PLATFORM", "platform lock in the record does not match the platform surface or revision")
    record = load_selection_record(SELECTION)
    plans = {plan.catalog_identity: plan for plan in admit_descriptors(record, platform_root=platform_root).plans}
    recorded = {str(item.get("catalogIdentity")): item for item in data.get("plans", ())}
    if set(plans) != set(recorded):
        raise AdmissionError(f"{code}-PLAN", "set of descriptor plans differs from the admitted one")
    for identity, plan in plans.items():
        item = recorded[identity]
        if item.get("digest") != plan.digest or list(item.get("blockers", ())) != list(plan.blockers):
            raise AdmissionError(f"{code}-PLAN", f"plan {identity} digest or blockers differ from the admitted ones")
    return data
