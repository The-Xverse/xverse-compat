"""Contract-verification table for the selected artifacts (thesis V05).

Every statement about an artifact's real interface (port, flag, key expression, encoding, version,
interpreter compatibility) is recorded with the evidence that supports it: a file path with a line
number, or a command whose output hash is in the read-only inventory. A statement without evidence
is NOT_VERIFIED and carries a blocker; nothing is inferred.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

STATUSES: frozenset[str] = frozenset({"verified", "NOT_VERIFIED", "mismatch"})
_LINE_REF = re.compile(r"^/[^\s:]+:[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*$")
_HASH_REF = re.compile(r"^(?:sha256|md5):[0-9a-f]{16,64}$")
_GAP = re.compile(r"^G[0-9]+$")


class ContractError(RuntimeError):
    """Stable, public-safe failure raised while loading the contract table."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure.

        @param code Stable code of the form ``XVERSE-COMPAT-CONTRACT-<REASON>``.
        @param message Public-safe explanation.
        """

        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class ContractStatement:
    """One verifiable statement with its evidence and status."""

    id: str
    artifact: str
    statement: str
    status: str
    evidence: tuple[str, ...]
    blocker: str | None = None
    gap: str | None = None


def _check_evidence(reference: str, inventory_text: str, cited_files: Mapping[str, str], statement_id: str) -> None:
    """Accept a hash present in the inventory, or a ``path:line`` whose path the inventory hashes."""

    if _HASH_REF.match(reference):
        digest = reference.split(":", 1)[1]
        if digest in inventory_text:
            return
        raise ContractError("XVERSE-COMPAT-CONTRACT-EVIDENCE", f"statement {statement_id} cites a hash absent from the inventory")
    if _LINE_REF.match(reference):
        path = reference.rsplit(":", 1)[0]
        if path in cited_files:
            return
        raise ContractError("XVERSE-COMPAT-CONTRACT-EVIDENCE", f"statement {statement_id} cites a file the inventory does not hash")
    raise ContractError("XVERSE-COMPAT-CONTRACT-EVIDENCE", f"statement {statement_id} evidence is neither an absolute path:line nor an inventory hash")


def load_contract_table(path: Path, inventory_path: Path) -> tuple[ContractStatement, ...]:
    """Load and validate the contract table against the inventory, failing closed.

    @param path JSON file with ``statements`` and ``gaps``.
    @param inventory_path The read-only artifact inventory whose hashes evidence may cite.
    @return Validated statements in file order.
    @raises ContractError On a missing evidence reference, an unknown status, or a gap without a row.
    """

    code = "XVERSE-COMPAT-CONTRACT"
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        inventory_text = Path(inventory_path).read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ContractError(f"{code}-READ", "contract table or inventory is unreadable or not JSON") from error
    if not isinstance(raw, Mapping):
        raise ContractError(f"{code}-READ", "contract table is not a JSON object")
    try:
        inventory = json.loads(inventory_text)
    except ValueError as error:
        raise ContractError(f"{code}-READ", "inventory is not JSON") from error
    cited_files = inventory.get("cited_files") if isinstance(inventory, Mapping) else None
    if not isinstance(cited_files, Mapping) or not all(isinstance(v, str) and len(v) == 64 for v in cited_files.values()):
        raise ContractError(f"{code}-READ", "inventory lacks a cited_files map of path to sha256")
    statements: list[ContractStatement] = []
    seen: set[str] = set()
    for item in raw.get("statements") or ():
        if not isinstance(item, Mapping):
            raise ContractError(f"{code}-SHAPE", "statement is not an object")
        statement_id = str(item.get("id", ""))
        if not statement_id or statement_id in seen:
            raise ContractError(f"{code}-ID", "statement id missing or duplicated")
        seen.add(statement_id)
        status = str(item.get("status", ""))
        if status not in STATUSES:
            raise ContractError(f"{code}-STATUS", f"statement {statement_id} status is not one of {sorted(STATUSES)}")
        evidence = tuple(str(value) for value in (item.get("evidence") or ()))
        if status == "verified":
            if not evidence:
                raise ContractError(f"{code}-EVIDENCE", f"verified statement {statement_id} cites no evidence")
            for reference in evidence:
                _check_evidence(reference, inventory_text, cited_files, statement_id)
        blocker = item.get("blocker")
        gap = item.get("gap")
        if status != "verified" and not blocker:
            raise ContractError(f"{code}-BLOCKER", f"statement {statement_id} is {status} without a blocker")
        if gap is not None and not _GAP.match(str(gap)):
            raise ContractError(f"{code}-GAP", f"statement {statement_id} gap is not G<n>")
        statements.append(ContractStatement(
            id=statement_id, artifact=str(item.get("artifact", "")), statement=str(item.get("statement", "")),
            status=status, evidence=evidence, blocker=blocker if isinstance(blocker, str) else None,
            gap=str(gap) if gap is not None else None,
        ))
    declared_gaps = {str(item) for item in (raw.get("gaps") or ())}
    covered = {item.gap for item in statements if item.gap}
    if declared_gaps - covered:
        raise ContractError(f"{code}-GAP-ROW", f"gaps without a blocker row: {sorted(declared_gaps - covered)}")
    return tuple(statements)


def statements_by_artifact(statements: Sequence[ContractStatement]) -> dict[str, tuple[ContractStatement, ...]]:
    """Group statements by artifact id for reporting."""

    grouped: dict[str, list[ContractStatement]] = {}
    for item in statements:
        grouped.setdefault(item.artifact, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def contract_public_data(statements: Sequence[ContractStatement]) -> list[dict[str, Any]]:
    """Return a JSON-ready projection of the statements (no host-private data is added)."""

    return [
        {"id": item.id, "artifact": item.artifact, "statement": item.statement, "status": item.status,
         "evidence": list(item.evidence), "blocker": item.blocker, "gap": item.gap}
        for item in statements
    ]
