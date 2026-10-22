"""U-DSC-01 … U-DSC-05: XDL descriptors validated at the pinned platform (thesis V03, V04)."""

from __future__ import annotations

import ast
from pathlib import Path
import shutil
import tempfile
import unittest

from xverse_xdl import derive_catalog

from xverse_compat.descriptors import (
    DESCRIPTOR_DIR,
    DescriptorError,
    admit_descriptors,
    default_platform_root,
    descriptor_paths,
    validate_descriptors,
)
from xverse_compat.selection import load_selection_record

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "xdl" / "selection" / "aeb-sim-selection.json"
PLATFORM = default_platform_root()


@unittest.skipUnless((PLATFORM / "xdl" / "profiles").is_dir(), "sibling xverse-platform checkout required")
class DescriptorTests(unittest.TestCase):
    """Positive admission and layered negatives on mutated copies of the descriptor graph."""

    def setUp(self) -> None:
        """Load the record and prepare a temp copy of the descriptor folder for mutations."""

        self.record = load_selection_record(RECORD)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.copy = Path(self.temp.name) / "aeb-sim"
        shutil.copytree(DESCRIPTOR_DIR, self.copy)

    def _mutate(self, filename: str, old: str, new: str) -> tuple[Path, ...]:
        """Replace ``old`` by ``new`` exactly once in the copied ``filename`` and return the copy's paths."""

        path = self.copy / filename
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        path.write_text(text.replace(old, new), encoding="utf-8")
        return descriptor_paths(self.copy)

    def test_u_dsc_01_graph_validates_and_derives_two_entries(self) -> None:
        """U-DSC-01."""

        admission = admit_descriptors(self.record)
        self.assertTrue(admission.validation.is_valid, admission.validation.diagnostics)
        self.assertEqual(
            sorted(entry.binding_id for entry in admission.entries),
            ["bridge-auto-binding", "carla-server-binding"],
        )
        self.assertEqual({entry.provider_kind for entry in admission.entries}, {"process"})

    def test_u_dsc_02_blocked_plans_never_eligible(self) -> None:
        """U-DSC-02: plans derive with their blockers; not plannable while blocked; never eligible."""

        admission = admit_descriptors(self.record)
        for plan in admission.plans:
            self.assertTrue(plan.blockers, plan.catalog_identity)
            self.assertFalse(plan.is_plannable, plan.catalog_identity)
            self.assertFalse(plan.execution_eligible, plan.catalog_identity)
            self.assertIsNotNone(plan.process_action)
            self.assertTrue(plan.digest.startswith("sha256:"))
        bridge = next(plan for plan in admission.plans if plan.catalog_identity.endswith("bridge-auto-binding"))
        self.assertIn("XVERSE-PLAN-THESIS-G1", bridge.blockers)
        self.assertIn("XVERSE-PLAN-THESIS-UNEXECUTED", bridge.blockers)

    def test_u_dsc_03_artifact_digests_equal_pins(self) -> None:
        """U-DSC-03."""

        admission = admit_descriptors(self.record)
        pins = {pin.digest for pin in self.record.pins if pin.digest}
        for entry in admission.entries:
            self.assertTrue(set(entry.artifact_digests) <= pins, entry.identity)
            self.assertTrue(entry.artifact_digests, entry.identity)

    def test_u_dsc_04_negatives_with_rejecting_layer(self) -> None:
        """U-DSC-04."""

        cases = (
            ("owned revision", "component-bridge-auto.xdl.yaml", "revision: eef3f71747220d150c0b99c30194ca197fe339f9", "revision: main", "XVERSE-COMPAT-DESCRIPTOR-REVISION"),
            ("owned readiness duration", "deployment.xdl.yaml", "condition: a sample is published on the zenoh key ego_vehicle/speed", "condition: wait 10 s", "XVERSE-COMPAT-DESCRIPTOR-READINESS-DURATION"),
            ("owned readiness duration words", "deployment.xdl.yaml", "condition: a sample is published on the zenoh key ego_vehicle/speed", "condition: ready after one second", "XVERSE-COMPAT-DESCRIPTOR-READINESS-DURATION"),
            ("owned readiness timer", "deployment.xdl.yaml", "condition: CARLA RPC server answers a version query on tcp port 2000", "condition: the startup timer expires", "XVERSE-COMPAT-DESCRIPTOR-READINESS-DURATION"),
            ("owned missing UNEXECUTED", "deployment.xdl.yaml", "            - XVERSE-PLAN-THESIS-G3\n            - XVERSE-PLAN-THESIS-UNEXECUTED\n", "            - XVERSE-PLAN-THESIS-G3\n", "XVERSE-COMPAT-DESCRIPTOR-BLOCKER"),
            ("owned artifact sourceRef differs from pin", "deployment.xdl.yaml", "      sourceRef: https://github.com/The-Xverse/carla-simulator-bridge.git@eef3f71747220d150c0b99c30194ca197fe339f9\n      maturity: observed", "      sourceRef: https://github.com/The-Xverse/carla-simulator-bridge.git@main\n      maturity: observed", "XVERSE-COMPAT-DESCRIPTOR-ARTIFACT-SOURCE"),
            ("owned release:latest revision", "component-carla-server.xdl.yaml", "revision: release:0.9.15", "revision: release:latest", "XVERSE-COMPAT-DESCRIPTOR-REVISION"),
            ("owned dependency", "deployment.xdl.yaml", "          - carla-server-binding\n", "          - zenoh-router-binding\n", "XVERSE-COMPAT-DESCRIPTOR-DEPENDENCY"),
            ("owned blocker", "deployment.xdl.yaml", "            - XVERSE-PLAN-THESIS-G1\n", "", "XVERSE-COMPAT-DESCRIPTOR-BLOCKER"),
            ("owned stream trace", "deployment.xdl.yaml", "          - vehicleSpeed\n", "          - camera\n", "XVERSE-COMPAT-DESCRIPTOR-STREAM-TRACE"),
            ("platform binding gate missing digest", "deployment.xdl.yaml", "      digest: sha256:37b6b6be6ac843475bcddd9f2139d6f265e42aaa30d7f295f8d586022bce62ed\n", "", "XVERSE-COMPAT-DESCRIPTOR-VALIDATION"),
            ("platform schema relative executable", "deployment.xdl.yaml", "executable: /home/jefferson/carla-simulator/CarlaUE4.sh", "executable: CarlaUE4.sh", "XVERSE-COMPAT-DESCRIPTOR-VALIDATION"),
            ("platform schema inherited handles", "deployment.xdl.yaml", "            environmentNames: []\n            inheritedHandles: closed", "            environmentNames: []\n            inheritedHandles: false", "XVERSE-COMPAT-DESCRIPTOR-VALIDATION"),
            ("platform schema undeclared env name", "deployment.xdl.yaml", "              - SDL_VIDEODRIVER\n", "              - sdl-video-driver\n", "XVERSE-COMPAT-DESCRIPTOR-VALIDATION"),
            ("platform schema implicit shell", "deployment.xdl.yaml", "            inheritedHandles: closed\n            implicitShell: false\n          planningBlockers:\n            - XVERSE-PLAN-THESIS-G1", "            inheritedHandles: closed\n            implicitShell: true\n          planningBlockers:\n            - XVERSE-PLAN-THESIS-G1", "XVERSE-COMPAT-DESCRIPTOR-VALIDATION"),
            ("owned no blocker", "deployment.xdl.yaml", "          planningBlockers:\n            - XVERSE-PLAN-RESOURCE-LIMITS-UNAPPROVED\n            - XVERSE-PLAN-THESIS-UNEXECUTED\n", "", "XVERSE-COMPAT-DESCRIPTOR-BLOCKER"),
        )
        for name, filename, old, new, expected in cases:
            with self.subTest(case=name):
                shutil.rmtree(self.copy)
                shutil.copytree(DESCRIPTOR_DIR, self.copy)
                paths = self._mutate(filename, old, new)
                with self.assertRaises(DescriptorError) as caught:
                    admit_descriptors(self.record, paths=paths)
                self.assertEqual(caught.exception.code, expected)

    def test_u_dsc_04b_missing_digest_is_rejected_by_the_platform_binding_gate(self) -> None:
        """U-DSC-04: a digest-less bound artifact fails the platform binding gate before catalog derivation."""

        paths = self._mutate("deployment.xdl.yaml", "      digest: sha256:37b6b6be6ac843475bcddd9f2139d6f265e42aaa30d7f295f8d586022bce62ed\n", "")
        validation = validate_descriptors(paths, PLATFORM)
        self.assertFalse(validation.is_valid)
        self.assertIn("XDL-BINDING-ARTIFACT-INTEGRITY", {item.code for item in validation.diagnostics})
        catalog = derive_catalog(validation.resources)
        self.assertNotIn("bridge-auto-binding", {entry.binding_id for entry in catalog.entries})
        self.assertIn("XVERSE-CATALOG-ARTIFACT-PIN", {item.code for item in catalog.diagnostics})

    def test_u_dsc_05_no_discovery_or_execution_imports(self) -> None:
        """U-DSC-05."""

        source = (ROOT / "src" / "xverse_compat" / "descriptors.py").read_text(encoding="utf-8")
        imports: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        self.assertFalse(imports & {"subprocess", "socket", "psutil", "glob", "os", "shutil", "zenoh"}, imports)


if __name__ == "__main__":
    unittest.main()
