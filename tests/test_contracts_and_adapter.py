"""U-CON-01/02 and U-ADP-01 … U-ADP-08: contract table and bridge-sample adapter (thesis V05, V06)."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest

from xverse_compat.adapters.bridge_samples import (
    BridgeSampleDecoder,
    DecoderPolicy,
    SampleDiagnostic,
    read_fixture,
)
from xverse_compat.contracts import ContractError, load_contract_table

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "xdl" / "selection" / "aeb-sim-contracts.json"
INVENTORY = ROOT / "xdl" / "selection" / "artifact-inventory-20261022.json"
FIXTURE = ROOT / "tests" / "fixtures" / "bridge-samples" / "ego-speed-hand-authored.jsonl"


class ContractTableTests(unittest.TestCase):
    """The contract table cites evidence for every verified statement and a row for every gap."""

    def test_u_con_01_every_verified_statement_has_evidence(self) -> None:
        """U-CON-01."""

        statements = load_contract_table(TABLE, INVENTORY)
        self.assertGreaterEqual(len(statements), 10)
        for item in statements:
            if item.status == "verified":
                self.assertTrue(item.evidence, item.id)
            else:
                self.assertTrue(item.blocker, item.id)

    def test_u_con_02_every_gap_is_a_blocker_row(self) -> None:
        """U-CON-02."""

        statements = load_contract_table(TABLE, INVENTORY)
        gaps = {item.gap for item in statements if item.gap}
        self.assertEqual(gaps, {"G1", "G2", "G3", "G4", "G5"})
        for item in statements:
            if item.gap:
                self.assertTrue(item.blocker, item.id)

    def test_negative_unknown_hash_and_missing_blocker(self) -> None:
        """A hash absent from the inventory, or NOT_VERIFIED without a blocker, fails closed."""

        raw = json.loads(TABLE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "table.json"
            altered = copy.deepcopy(raw)
            altered["statements"][1]["evidence"] = ["sha256:" + "0" * 64]
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ContractError) as caught:
                load_contract_table(path, INVENTORY)
            self.assertEqual(caught.exception.code, "XVERSE-COMPAT-CONTRACT-EVIDENCE")
            altered = copy.deepcopy(raw)
            del altered["statements"][2]["blocker"]
            path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ContractError) as caught:
                load_contract_table(path, INVENTORY)
            self.assertEqual(caught.exception.code, "XVERSE-COMPAT-CONTRACT-BLOCKER")


class BridgeSampleAdapterTests(unittest.TestCase):
    """Fail-closed decoding of hand-authored bridge samples; no Zenoh session."""

    def _sample(self, **overrides: object) -> dict:
        """Return a valid speed sample with ``overrides`` applied."""

        sample = {"key": "ego_vehicle/speed", "payload": "37", "sequence": 7, "receivedMonotonicS": 100.0, "receivedUtc": "2026-10-22T10:00:00Z"}
        sample.update(overrides)
        return sample

    def test_u_adp_01_decode_speed_fixture(self) -> None:
        """U-ADP-01."""

        decoder = BridgeSampleDecoder()
        speeds = [decoder.decode(item) for item in read_fixture(FIXTURE) if item["key"] == "ego_vehicle/speed"]
        self.assertEqual([item.value for item in speeds], [0.0, 37.0, 38.0])
        self.assertEqual(speeds[1].key, "ego_vehicle/speed")
        self.assertEqual(speeds[1].received_monotonic_s, 100.05)
        self.assertEqual(speeds[1].received_utc, "2026-10-22T10:00:00.050Z")

    def test_u_adp_02_malformed(self) -> None:
        """U-ADP-02."""

        for payload in ("nan", "37.5", "", "inf", "0x10"):
            with self.subTest(payload=payload), self.assertRaises(SampleDiagnostic) as caught:
                BridgeSampleDecoder().decode(self._sample(payload=payload))
            self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-MALFORMED")

    def test_u_adp_03_out_of_range(self) -> None:
        """U-ADP-03."""

        for payload in ("-1", "1000"):
            with self.subTest(payload=payload), self.assertRaises(SampleDiagnostic) as caught:
                BridgeSampleDecoder().decode(self._sample(payload=payload))
            self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-RANGE")

    def test_u_adp_04_stale(self) -> None:
        """U-ADP-04."""

        decoder = BridgeSampleDecoder(DecoderPolicy(freshness_s=0.5, now_monotonic_s=101.0))
        with self.assertRaises(SampleDiagnostic) as caught:
            decoder.decode(self._sample(receivedMonotonicS=100.0))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-STALE")
        self.assertEqual(decoder.decode(self._sample(receivedMonotonicS=100.8)).value, 37.0)

    def test_u_adp_05_duplicate(self) -> None:
        """U-ADP-05."""

        decoder = BridgeSampleDecoder()
        decoder.decode(self._sample())
        with self.assertRaises(SampleDiagnostic) as caught:
            decoder.decode(self._sample())
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-DUPLICATE")

    def test_u_adp_06_undeclared_key_and_shape(self) -> None:
        """U-ADP-06."""

        with self.assertRaises(SampleDiagnostic) as caught:
            BridgeSampleDecoder().decode(self._sample(key="foo/bar"))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-KEY")
        with self.assertRaises(SampleDiagnostic) as caught:
            BridgeSampleDecoder().decode(self._sample(sequence="7"))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-SHAPE")

    def test_u_adp_07_status_decoders_for_the_attended_case(self) -> None:
        """U-ADP-07."""

        decoder = BridgeSampleDecoder()
        self.assertEqual(decoder.decode(self._sample(key="vehicle/status/braking_status", payload="0.5")).value, 0.5)
        with self.assertRaises(SampleDiagnostic) as caught:
            decoder.decode(self._sample(key="vehicle/status/braking_status", payload="1.5", sequence=8))
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-SAMPLE-RANGE")

    def test_u_adp_08_no_session_import(self) -> None:
        """U-ADP-08."""

        source = (ROOT / "src" / "xverse_compat" / "adapters" / "bridge_samples.py").read_text(encoding="utf-8")
        imports: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        self.assertFalse(imports & {"zenoh", "socket", "subprocess", "asyncio"}, imports)


if __name__ == "__main__":
    unittest.main()
