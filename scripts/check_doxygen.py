#!/usr/bin/env python3
"""Validate Python docstrings and generate warning-clean Doxygen reference output."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "src", ROOT / "scripts", ROOT / "tests")
DOXYFILE = ROOT / "Doxyfile"
OUTPUT_ROOT = ROOT / "build" / "doxygen"
WARNING_LOG = ROOT / "build" / "doxygen-warnings.log"


def python_sources(root: Path) -> tuple[Path, ...]:
    """Return Python files below *root* in deterministic order."""

    return tuple(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))


def _missing_symbols(
    body: Iterable[ast.stmt], path: Path, parents: tuple[str, ...] = (),
) -> list[str]:
    """Return undocumented class and callable definitions recursively."""

    missing: list[str] = []
    for node in body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = ".".join((*parents, node.name))
            if ast.get_docstring(node, clean=False) is None:
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno}: {qualified}")
            missing.extend(_missing_symbols(node.body, path, (*parents, node.name)))
    return missing


def find_missing_docstrings(paths: Iterable[Path]) -> tuple[str, ...]:
    """Return missing module and symbol docstrings for supplied paths."""

    missing: list[str] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if ast.get_docstring(tree, clean=False) is None:
            missing.append(f"{path.relative_to(ROOT)}:1: <module>")
        missing.extend(_missing_symbols(tree.body, path))
    return tuple(missing)


def _indexed_files(index_path: Path) -> set[str]:
    """Read exact Python source paths from Doxygen XML file compounds."""

    root = ET.parse(index_path).getroot()
    indexed: set[str] = set()
    for compound in root.findall("compound[@kind='file']"):
        if not (compound.findtext("name") or "").endswith(".py"):
            continue
        detail = ET.parse(index_path.parent / f"{compound.attrib['refid']}.xml")
        location = detail.find(".//compounddef/location")
        if location is not None and location.get("file"):
            indexed.add(Path(location.get("file", "")).as_posix())
    return indexed


def _run_doxygen() -> tuple[str, ...]:
    """Generate documentation and return build or source-index errors."""

    executable = shutil.which("doxygen")
    if executable is None:
        return ("doxygen executable was not found on PATH",)
    WARNING_LOG.parent.mkdir(parents=True, exist_ok=True)
    WARNING_LOG.unlink(missing_ok=True)
    result = subprocess.run(
        (executable, str(DOXYFILE)), cwd=ROOT, text=True, capture_output=True, check=False,
    )
    errors: list[str] = []
    if result.returncode:
        errors.append(f"doxygen exited with {result.returncode}: {(result.stderr or result.stdout).strip()}")
    warnings = WARNING_LOG.read_text(encoding="utf-8").strip() if WARNING_LOG.exists() else ""
    if warnings:
        errors.append(f"Doxygen reported warnings:\n{warnings}")
    html_index = OUTPUT_ROOT / "html" / "index.html"
    xml_index = OUTPUT_ROOT / "xml" / "index.xml"
    if not html_index.is_file():
        errors.append("Doxygen HTML index is missing")
    if not xml_index.is_file():
        errors.append("Doxygen XML index is missing")
    elif not errors:
        expected = {
            path.relative_to(ROOT).as_posix()
            for source_root in SOURCE_ROOTS
            for path in python_sources(source_root)
        }
        absent = sorted(expected - _indexed_files(xml_index))
        if absent:
            errors.append("Doxygen omitted Python sources: " + ", ".join(absent))
    return tuple(errors)


def _self_test() -> tuple[str, ...]:
    """Prove the docstring gate rejects an undocumented synthetic function."""

    (ROOT / "build").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="doxygen-self-test-", dir=ROOT / "build") as temporary:
        fixture = Path(temporary) / "undocumented.py"
        fixture.write_text("def missing(value):\n    return value\n", encoding="utf-8")
        failures = find_missing_docstrings((fixture,))
    return () if len(failures) == 2 else ("coverage self-test did not reject module and function",)


def main(arguments: list[str] | None = None) -> int:
    """Run documentation coverage, optional self-test, and Doxygen generation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(arguments)
    production = (*python_sources(ROOT / "src"), *python_sources(ROOT / "scripts"))
    errors = list(find_missing_docstrings(production))
    if args.self_test:
        errors.extend(_self_test())
    if not args.coverage_only and not errors:
        errors.extend(_run_doxygen())
    if errors:
        print("documentation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    count = sum(len(python_sources(root)) for root in SOURCE_ROOTS)
    print(f"documentation validation passed: {len(production)} covered files")
    if args.self_test:
        print("coverage self-test passed")
    if not args.coverage_only:
        print(f"Doxygen indexed {count} Python source files")
        print("HTML index: build/doxygen/html/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
