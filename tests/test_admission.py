"""U-ADM-01 … U-ADM-04: admission record integrity and platform re-pin (thesis V07)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from xverse_compat.admission import (
    AdmissionError,
    PhaseRevisions,
    build_admission_record,
    verify_admission_record,
)
from xverse_compat.descriptors import default_platform_root
from xverse_compat.platform_pin import verify_platform_pin

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = default_platform_root()
REVISIONS = PhaseRevisions(
    xdl_lite="c1fd213cd00259b74f8308d8ca58157ea985aaa0",
    argus_lite="c2997c0f810d117cf45b2e34a4011b3ba7219494",
    maestro_lite="63f5cb8c7d686b3c2bfb8dd8aedb7e7a9245baa8",
    platform_main="744b66f9c3b964f8ec0105a08ddb905a5e24d2b5",
)


@unittest.skipUnless((PLATFORM / "xdl" / "profiles").is_dir(), "sibling xverse-platform checkout required")
class AdmissionTests(unittest.TestCase):
    """Build into a temporary location; the real record is produced by scripts/admit_phase4.py."""

    def setUp(self) -> None:
        """Prepare a temporary output, lock and verification log."""

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.log = self.directory / "pytest.log"
        self.log.write_text("69 passed, 1 failed\n", encoding="utf-8")
        self.lock = self.directory / "platform-api.lock.json"
        self.output = self.directory / "admission.json"

    def _build(self) -> dict:
        """Build a record into the temporary location."""

        return build_admission_record(
            platform_root=PLATFORM, revisions=REVISIONS, verification_log=self.log,
            verification_summary={"suite": "t", "command": "pytest", "passed": 69, "failed": 1},
            output=self.output, lock_path=self.lock, now=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        )

    def test_u_adm_01_every_file_binding_recomputes(self) -> None:
        """U-ADM-01."""

        data = self._build()
        verified = verify_admission_record(self.output, PLATFORM, expected_revision=REVISIONS.platform_main)
        self.assertEqual(verified["selectionRecord"], data["selectionRecord"])
        self.assertTrue(data["descriptors"]) and self.assertTrue(data["fixtures"])
        for pin in data["pins"]:
            self.assertEqual(pin["recomputed"], "match" if pin["availability"] == "present" else "unpinned", pin["id"])

    def test_u_adm_02_platform_identity_and_repin(self) -> None:
        """U-ADM-02."""

        data = self._build()
        self.assertEqual(data["platform"]["revision"], REVISIONS.platform_main)
        self.assertEqual(data["platform"]["xdlPackageVersion"], "0.4.0")
        self.assertTrue(data["platform"]["schemasTree"]["fileCount"] >= 7)
        self.assertTrue(data["platform"]["profilesTree"]["fileCount"] >= 4)
        manifest = verify_platform_pin(self.lock, PLATFORM)
        self.assertEqual(manifest["treeSha256"], data["platform"]["sourceSurfaceTreeSha256"])
        self.assertEqual(manifest["fileCount"], data["platform"]["sourceSurfaceFileCount"])

    def test_u_adm_03_authority_absent_and_blockers_listed(self) -> None:
        """U-ADM-03."""

        data = self._build()
        self.assertEqual(data["executionAuthority"], "absent")
        for gap in ("G2", "G3", "G4", "G5", "G6"):
            self.assertIn(f"XVERSE-PLAN-THESIS-{gap}", data["blockers"])
        self.assertNotIn("XVERSE-PLAN-THESIS-G1", data["blockers"])  # closed for the adapter runtime (Phase 4b)
        self.assertEqual(data["sensorDescriptors"]["path"], "xdl/descriptors/aeb-sim/carla-sensors.json")
        self.assertIn("XVERSE-PLAN-THESIS-UNEXECUTED", data["blockers"])
        self.assertIsNone(data["review"]) and self.assertIsNone(data["acceptance"])
        for plan in data["plans"]:
            self.assertFalse(plan["executionEligible"]) and self.assertFalse(plan["isPlannable"])

    def test_u_adm_05_sensor_descriptors_binding_and_tampering(self) -> None:
        """Phase 4b re-derivation item 5: carla-sensors.json validated at build and hash-bound."""

        import json as _json
        from unittest import mock

        from xverse_compat import admission

        data = self._build()
        self.assertEqual(len(data["sensorDescriptors"]["sha256"]), 64)
        record = _json.loads(self.output.read_text())
        record["sensorDescriptors"]["sha256"] = "0" * 64
        self.output.write_text(_json.dumps(record))
        with self.assertRaises(admission.AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-FILE")
        del record["sensorDescriptors"]
        self.output.write_text(_json.dumps(record))
        with self.assertRaises(admission.AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-FILE")
        bad = self.output.parent / "carla-sensors-bad.json"
        bad.write_text(_json.dumps({"schema": "xverse-compat.carla-sensors/1", "settings": {"synchronous": False}}))
        with mock.patch.object(admission, "SENSORS", bad), self.assertRaises(admission.AdmissionError) as caught:
            self._build()
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-SENSORS")

    def test_u_adm_04_negatives(self) -> None:
        """U-ADM-04."""

        self._build()
        raw = json.loads(self.output.read_text(encoding="utf-8"))
        altered = dict(raw)
        altered["platform"] = dict(raw["platform"], sourceSurfaceTreeSha256="0" * 64)
        self.output.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-PLATFORM")
        altered = dict(raw)
        altered["descriptors"] = [dict(raw["descriptors"][0], sha256="0" * 64)] + list(raw["descriptors"][1:])
        self.output.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-FILE")
        altered = dict(raw, executionAuthority="granted")
        self.output.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-AUTHORITY")
        self.output.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM, expected_revision="0" * 40)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-REVISION")
        lock_data = json.loads(self.lock.read_text(encoding="utf-8"))
        self.lock.write_text(json.dumps(dict(lock_data, extraKey=True)), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-LOCK")
        self.lock.write_text(json.dumps(lock_data), encoding="utf-8")
        self.log.write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-FILE")
        self.log.write_text("69 passed, 1 failed\n", encoding="utf-8")
        altered = dict(raw, plans=[dict(raw["plans"][0], digest="sha256:" + "0" * 64)] + list(raw["plans"][1:]))
        self.output.write_text(json.dumps(altered), encoding="utf-8")
        with self.assertRaises(AdmissionError) as caught:
            verify_admission_record(self.output, PLATFORM)
        self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-PLAN")
        with tempfile.TemporaryDirectory() as other:
            fake = Path(other) / "xverse-platform"
            shutil.copytree(PLATFORM / "xdl", fake / "xdl")
            (fake / "pyproject.toml").write_text('version = "0.4.0"\n', encoding="utf-8")
            (fake / "src" / "xverse_xdl").mkdir(parents=True)
            self.output.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(AdmissionError) as caught:
                verify_admission_record(self.output, fake)
            self.assertEqual(caught.exception.code, "XVERSE-COMPAT-ADMISSION-PLATFORM")


if __name__ == "__main__":
    unittest.main()

