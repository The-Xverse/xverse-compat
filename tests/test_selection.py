"""U-SEL-01 … U-SEL-12: artifact-selection record and pin verification (thesis V01, V02)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from xverse_compat.selection import (
    REQUIRED_STREAMS,
    SelectionError,
    load_selection_record,
    verify_pins,
)

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "xdl" / "selection" / "aeb-sim-selection.json"


def _write(raw: dict, directory: Path) -> Path:
    """Write ``raw`` as the selection record inside ``directory`` and return its path."""

    path = directory / "record.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


class SelectionRecordTests(unittest.TestCase):
    """Positive and negative checks of the committed selection record."""

    def setUp(self) -> None:
        """Load the raw record once per test for mutation-based negatives."""

        self.raw = json.loads(RECORD.read_text(encoding="utf-8"))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def _load_mutated(self, mutate) -> None:
        """Apply ``mutate`` to a copy of the record and load it."""

        raw = copy.deepcopy(self.raw)
        mutate(raw)
        load_selection_record(_write(raw, self.directory))

    def test_u_sel_01_every_required_stream_once(self) -> None:
        """U-SEL-01."""

        record = load_selection_record(RECORD)
        streams = [item.stream for item in record.streams]
        self.assertEqual(set(streams), set(REQUIRED_STREAMS))
        self.assertEqual(len(streams), len(set(streams)))

    def test_u_sel_02_dispositions_consistent(self) -> None:
        """U-SEL-02."""

        record = load_selection_record(RECORD)
        pin_ids = {pin.id for pin in record.pins}
        for item in record.streams:
            if item.disposition == "supplied":
                self.assertIn(item.supplier, pin_ids)
            elif item.disposition == "adapter":
                self.assertIn(item.supplier, record.adapters)
            else:
                self.assertRegex(item.blocker or "", r"^G[0-9]+$")

    def test_u_sel_03_no_unneeded_technology(self) -> None:
        """U-SEL-03."""

        record = load_selection_record(RECORD)
        referenced = {item.supplier for item in record.streams} | {dep for item in record.streams for dep in item.depends_on}
        for pin in record.pins:
            self.assertIn(pin.id, referenced)
        self.assertTrue(record.not_selected)
        self.assertTrue(any("zenoh_vehicle.py" in item for item in record.not_selected))

    def test_u_sel_04_pins_committed_and_digested(self) -> None:
        """U-SEL-04."""

        record = load_selection_record(RECORD)
        for pin in record.pins:
            if pin.availability == "present":
                self.assertRegex(pin.digest or "", r"^sha256:[0-9a-f]{64}$")
                self.assertTrue(pin.digest_command)
            else:
                self.assertIsNone(pin.digest)
                self.assertTrue(pin.reason)

    def test_u_sel_05_missing_stream(self) -> None:
        """U-SEL-05."""

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(lambda raw: raw["streams"].pop(next(i for i, s in enumerate(raw["streams"]) if s["stream"] == "radar")))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-STREAM-MISSING")

    def test_u_sel_06_duplicate_stream(self) -> None:
        """U-SEL-06."""

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(lambda raw: raw["streams"].append(copy.deepcopy(raw["streams"][0])))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-STREAM-DUPLICATE")

    def test_u_sel_07_supplied_without_supplier(self) -> None:
        """U-SEL-07."""

        def mutate(raw: dict) -> None:
            row = next(s for s in raw["streams"] if s["disposition"] == "supplied")
            del row["supplier"]

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(mutate)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-SUPPLIER-MISSING")

    def test_u_sel_08_blocked_without_gap(self) -> None:
        """U-SEL-08."""

        def mutate(raw: dict) -> None:
            row = next(s for s in raw["streams"] if s["disposition"] == "blocked")
            del row["blocker"]

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(mutate)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-BLOCKER-MISSING")

    def test_u_sel_09_floating_source_ref(self) -> None:
        """U-SEL-09."""

        def mutate(raw: dict) -> None:
            pin = next(p for p in raw["pins"] if p["id"] == "bridge-auto")
            pin["sourceRef"] = pin["sourceRef"].rsplit("@", 1)[0] + "@main"

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(mutate)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-PIN-FLOATING")

    def test_u_sel_10_bad_digest(self) -> None:
        """U-SEL-10."""

        def mutate(raw: dict) -> None:
            raw["pins"][0]["digest"] = "sha256:zz"

        with self.assertRaises(SelectionError) as caught:
            self._load_mutated(mutate)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SELECTION-PIN-DIGEST")

    def test_u_sel_10b_release_flag_uri_and_local_path(self) -> None:
        """LOW repairs: releaseArtifact must be boolean; sourceRef needs a scheme; localPath absolute."""

        def release_string(raw: dict) -> None:
            raw["pins"][0]["releaseArtifact"] = "no"

        def no_scheme(raw: dict) -> None:
            raw["pins"][0]["sourceRef"] = "tiny.carla.org/carla-0-9-15-linux"

        def relative_path(raw: dict) -> None:
            raw["pins"][0]["localPath"] = "carla-simulator/CarlaUE4.sh"

        for mutate, expected in ((release_string, "XVERSE-COMPAT-SELECTION-PIN-RELEASE"), (no_scheme, "XVERSE-COMPAT-SELECTION-PIN-SOURCE"), (relative_path, "XVERSE-COMPAT-SELECTION-PIN-LOCAL-PATH")):
            with self.subTest(expected=expected), self.assertRaises(SelectionError) as caught:
                self._load_mutated(mutate)
            self.assertEqual(caught.exception.code, expected)

    def test_u_sel_11_digest_recomputation_on_owned_files(self) -> None:
        """U-SEL-11."""

        root = self.directory / "root"
        (root / "a").mkdir(parents=True)
        (root / "a" / "one.bin").write_bytes(b"one")
        (root / "a" / "two.bin").write_bytes(b"two")
        raw = copy.deepcopy(self.raw)
        raw["pins"] = [
            {
                "id": pin_id, "artifactKind": "file", "version": "1", "sourceRef": "urn:x@" + "0" * 40,
                "availability": "present", "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "digestCommand": "sha256sum", "localPath": f"/a/{pin_id}.bin", "license": "n/a",
                "classification": "public-safe", "toolchain": "n/a",
            }
            for pin_id, content in (("one", b"one"), ("two", b"two"))
        ]
        raw["streams"] = [
            {"stream": stream, "disposition": "blocked", "blocker": "G1"} for stream in sorted(REQUIRED_STREAMS)
        ]
        raw["streams"][0]["dependsOn"] = ["one", "two"]
        record = load_selection_record(_write(raw, self.directory))
        self.assertEqual(verify_pins(record, root), {"one": "match", "two": "match"})
        (root / "a" / "two.bin").write_bytes(b"TWO")
        (root / "a" / "one.bin").unlink()
        self.assertEqual(verify_pins(record, root), {"one": "absent", "two": "mismatch"})

    def test_u_sel_12_digest_recomputation_on_host_artifacts(self) -> None:
        """U-SEL-12 (skipped when the host lacks a pinned local path)."""

        record = load_selection_record(RECORD)
        for pin in record.pins:
            if pin.availability == "present" and pin.local_path and not Path(pin.local_path).is_file():
                self.skipTest(f"pinned local path absent on this host: {pin.id}")
        results = verify_pins(record)
        for pin in record.pins:
            if pin.availability == "present":
                self.assertEqual(results[pin.id], "match", pin.id)
            else:
                self.assertEqual(results[pin.id], "unpinned", pin.id)


if __name__ == "__main__":
    unittest.main()
