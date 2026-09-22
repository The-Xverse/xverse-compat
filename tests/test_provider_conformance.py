"""C01–C14 conformance tests for the target-neutral compatibility provider boundary."""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

import xverse_xdl
from xverse_xdl import (
    ExecutionPermit,
    FrozenMap,
    InMemoryEvidenceJournal,
    IsolationAttestation,
    LifecycleController,
    LifecycleError,
    LifecyclePlan,
    OwnedResourceHandle,
    PlanAction,
    ProcessAction,
)

from xverse_compat import (
    CompatibilityProviderError,
    ConformanceProcessProvider,
    PlatformPinError,
    ProviderCompositionRoot,
    verify_platform_pin,
)

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_ROOT = "/opt/xverse/conformance"
EXECUTABLE = "/usr/bin/xverse-controlled-fixture"


def process_action(
    *,
    executable: str = EXECUTABLE,
    working_directory: str = f"{EXECUTION_ROOT}/work",
    environment_names: tuple[str, ...] = (),
) -> ProcessAction:
    """Return one explicit process action that the fixture validates but never executes."""

    return ProcessAction(executable, ("--fixture",), working_directory, environment_names)


def lifecycle_plan(
    *,
    provider_id: str = "controlled-provider",
    provider_kind: str = "process",
    action: ProcessAction | None = None,
    observe_timeout: float = 0.1,
) -> LifecyclePlan:
    """Build a minimal platform-owned plan for isolated compatibility tests."""

    selected_action = process_action() if action is None else action
    return LifecyclePlan(
        catalog_identity="compat-conformance-entry",
        environment_identity="isolated-conformance",
        provider_id=provider_id,
        provider_kind=provider_kind,
        selection=FrozenMap({"fixture": True}),
        resource_revisions=FrozenMap({"fixture": "v1"}),
        artifact_digests=("sha256:" + "0" * 64,),
        actions=(
            PlanAction("prepare", "prepare", "validate", 0.1),
            PlanAction("start", "start", "start", 0.1),
            PlanAction("observe", "observe", "observe", observe_timeout, "running"),
            PlanAction("stop", "stop", "stop", 0.1),
            PlanAction("cleanup", "cleanup", "cleanup", 0.1),
        ),
        process_action=selected_action,
        blockers=(),
        digest="sha256:" + "1" * 64,
    )


def permit_for(plan: LifecyclePlan, suffix: str = "one") -> ExecutionPermit:
    """Create an exact short-lived platform permit for one test plan."""

    now = datetime.now(timezone.utc)
    return ExecutionPermit(
        permit_id=f"permit-{suffix}",
        nonce=f"nonce-{suffix}",
        plan_digest=plan.digest,
        catalog_identity=plan.catalog_identity,
        environment_identity=plan.environment_identity,
        permitted_actions=tuple(action.action_id for action in plan.actions),
        approval_evidence_ref="urn:xverse:compat:test-approval",
        issuer_label="controlled-test",
        operation_classes=tuple(sorted({action.operation for action in plan.actions})),
        exclusions=("legacy-execution", "subprocess"),
        public_safety_classification="public-safe",
        not_before=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=1),
    )


def isolation_attestation() -> IsolationAttestation:
    """Return the explicit isolation declaration used by the controlled fixture."""

    return IsolationAttestation(
        attestation_id="compat-conformance-v1",
        execution_root=EXECUTION_ROOT,
        filesystem_boundary="isolated",
        legacy_checkout_immutable=True,
        network_boundary="none",
    )


def provider(*, available_environment_names: tuple[str, ...] = ()) -> ConformanceProcessProvider:
    """Construct the controlled provider from explicit isolation inputs."""

    return ConformanceProcessProvider(
        "controlled-provider",
        isolation_attestation=isolation_attestation(),
        allowed_executables=(EXECUTABLE,),
        available_environment_names=available_environment_names,
    )


class UnavailableProvider(ConformanceProcessProvider):
    """Controlled test double reporting an unavailable observation."""

    def observe(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Validate ownership, then report an unavailable observation."""

        super().observe(handle, timeout_seconds)
        return "unavailable"


class NotReadyProvider(ConformanceProcessProvider):
    """Controlled test double reporting a nonmatching ordinary status."""

    def observe(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Validate ownership, then report a status that does not meet readiness."""

        super().observe(handle, timeout_seconds)
        return "stopped"


class SlowObservationProvider(ConformanceProcessProvider):
    """Controlled test double exceeding an observation timeout."""

    def observe(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Delay beyond the declared timeout without external interaction."""

        time.sleep(timeout_seconds + 0.01)
        return super().observe(handle, timeout_seconds)


class RestrictedFailureProvider(ConformanceProcessProvider):
    """Controlled test double raising restricted-looking private detail."""

    def start(
        self,
        action: ProcessAction | None,
        execution_id: str,
        action_id: str,
        timeout_seconds: float,
    ) -> OwnedResourceHandle:
        """Raise a failure whose message must not cross the platform boundary."""

        raise RuntimeError("password=restricted 10.1.2.3 /private/legacy/path")


class BlockingStartProvider(ConformanceProcessProvider):
    """Controlled provider that holds the controller mutation lock during start."""

    def __init__(self, *args, **kwargs) -> None:
        """Create synchronization events before accepting a start."""

        super().__init__(*args, **kwargs)
        self.entered = threading.Event()
        self.release = threading.Event()

    def start(
        self,
        action: ProcessAction | None,
        execution_id: str,
        action_id: str,
        timeout_seconds: float,
    ) -> OwnedResourceHandle:
        """Block in memory until the test permits the first start to finish."""

        self.entered.set()
        if not self.release.wait(timeout=1):
            raise RuntimeError("controlled start was not released")
        return super().start(action, execution_id, action_id, timeout_seconds)


class ProviderConformanceTests(unittest.TestCase):
    """Prove every negative case in the accepted provider contract."""

    def test_platform_dependency_is_exact_version(self) -> None:
        """Prove runtime metadata and the imported module match the exact pin."""

        self.assertEqual(version("xverse-xdl"), "0.4.0")
        self.assertEqual(xverse_xdl.__version__, "0.4.0")

    def test_platform_dependency_source_matches_content_lock(self) -> None:
        """Prove the mutable local source exactly matches the reviewed content pin."""

        manifest_path = ROOT / "platform-api.lock.json"
        source_root = ROOT.parent / "xverse-platform"
        manifest = verify_platform_pin(manifest_path, source_root)
        self.assertEqual(manifest["packageVersion"], "0.4.0")
        with tempfile.TemporaryDirectory() as temporary:
            altered = dict(manifest)
            altered["treeSha256"] = "0" * 64
            altered_path = Path(temporary) / "altered-platform-pin.json"
            altered_path.write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(PlatformPinError):
                verify_platform_pin(altered_path, source_root)

    def test_fixture_source_cannot_execute_or_discover_targets(self) -> None:
        """Prove production code imports no process, network, or discovery mechanism."""

        source = (ROOT / "src/xverse_compat/provider.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".", 1)[0])
        self.assertTrue({"subprocess", "socket", "pkg_resources"}.isdisjoint(imports))
        self.assertNotIn("os.environ", source)

    def test_c01_unknown_provider_fails_before_start(self) -> None:
        """C01: reject an unknown provider ID without mutation."""

        fixture = provider()
        with self.assertRaisesRegex(CompatibilityProviderError, "no explicitly supplied") as raised:
            ProviderCompositionRoot((fixture,)).resolve(lifecycle_plan(provider_id="unknown"))
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-PROVIDER-UNKNOWN")
        self.assertEqual(fixture.start_count, 0)

    def test_c02_wrong_provider_kind_fails_before_start(self) -> None:
        """C02: reject a correct ID with the wrong kind without mutation."""

        fixture = provider()
        with self.assertRaises(CompatibilityProviderError) as raised:
            ProviderCompositionRoot((fixture,)).resolve(lifecycle_plan(provider_kind="service"))
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-PROVIDER-UNKNOWN")
        self.assertEqual(fixture.start_count, 0)

    def test_c03_duplicate_exact_providers_are_ambiguous(self) -> None:
        """C03: reject duplicate exact ID/kind implementations."""

        first = provider()
        second = provider()
        with self.assertRaises(CompatibilityProviderError) as raised:
            ProviderCompositionRoot((first, second)).resolve(lifecycle_plan())
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-PROVIDER-AMBIGUOUS")
        self.assertEqual(first.start_count + second.start_count, 0)

    def test_c04_missing_process_action_has_no_hidden_lookup(self) -> None:
        """C04: reject a missing process action without consulting ambient state."""

        fixture = provider()
        with self.assertRaises(CompatibilityProviderError) as raised:
            fixture.start(None, "execution", "start", 0.1)
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-ACTION-REQUIRED")
        self.assertEqual(fixture.start_count, 0)

    def test_c05_relative_process_paths_are_rejected(self) -> None:
        """C05: reject relative executable and working-directory paths."""

        for arguments in (
            {"executable": "relative-command"},
            {"working_directory": "relative-directory"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                process_action(**arguments)

    def test_c06_action_outside_allowlist_or_root_is_rejected(self) -> None:
        """C06: reject executables and working directories outside explicit bounds."""

        fixture = provider()
        for action in (
            process_action(executable="/usr/bin/not-allowed"),
            process_action(working_directory="/outside/conformance"),
            process_action(working_directory=f"{EXECUTION_ROOT}/../outside"),
        ):
            with self.subTest(action=action), self.assertRaises(CompatibilityProviderError):
                fixture.start(action, "execution", "start", 0.1)
        self.assertEqual(fixture.start_count, 0)
        with self.assertRaises(ValueError):
            ConformanceProcessProvider(
                "controlled-provider",
                isolation_attestation=isolation_attestation(),
                allowed_executables=("/usr/bin/../bin/xverse-controlled-fixture",),
            )
        with self.assertRaises(ValueError):
            ConformanceProcessProvider(
                "controlled-provider",
                isolation_attestation=IsolationAttestation(
                    "traversal", f"{EXECUTION_ROOT}/../outside", "isolated", True, "none"
                ),
                allowed_executables=(EXECUTABLE,),
            )

    def test_c07_secret_like_or_absent_environment_fails_closed(self) -> None:
        """C07: reject secret-like and unavailable environment names."""

        with self.assertRaises(ValueError):
            process_action(environment_names=("API_TOKEN",))
        fixture = provider()
        with self.assertRaises(CompatibilityProviderError) as raised:
            fixture.start(process_action(environment_names=("LANG",)), "execution", "start", 0.1)
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-ENVIRONMENT")
        self.assertEqual(fixture.start_count, 0)

    def test_c08_every_handle_field_is_part_of_ownership(self) -> None:
        """C08: reject each forged handle field and preserve the resource."""

        fixture = provider()
        handle = fixture.start(process_action(), "execution", "start", 0.1)
        for field, value in (
            ("opaque_id", "forged"),
            ("execution_id", "other-execution"),
            ("action_id", "other-action"),
            ("provider_id", "other-provider"),
            ("provider_kind", "other-kind"),
            ("resource_identity", "other-resource"),
        ):
            forged = replace(handle, **{field: value})
            with self.subTest(field=field), self.assertRaises(CompatibilityProviderError):
                fixture.observe(forged, 0.1)
            with self.assertRaises(CompatibilityProviderError):
                fixture.stop(forged, 0.1)
            with self.assertRaises(CompatibilityProviderError):
                fixture.cleanup(forged, 0.1)
        self.assertEqual(fixture.observe(handle, 0.1), "running")

    def test_c09_matching_start_and_stop_are_idempotent(self) -> None:
        """C09: return one resource and one stop transition for repeated calls."""

        fixture = provider()
        first = fixture.start(process_action(), "execution", "start", 0.1)
        second = fixture.start(process_action(), "execution", "start", 0.1)
        self.assertEqual(first, second)
        self.assertEqual(fixture.start_count, 1)
        self.assertEqual(fixture.stop(first, 0.1), "stopped")
        self.assertEqual(fixture.stop(first, 0.1), "stopped")
        self.assertEqual(fixture.stop_count, 1)

    def test_c10_catalog_environment_mutation_is_exclusive(self) -> None:
        """C10: reject a second execution while the selected identity is mutating."""

        fixture = BlockingStartProvider(
            "controlled-provider",
            isolation_attestation=isolation_attestation(),
            allowed_executables=(EXECUTABLE,),
        )
        plan = lifecycle_plan()
        first = LifecycleController(InMemoryEvidenceJournal())
        second = LifecycleController(InMemoryEvidenceJournal())
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(
                first.start, plan, permit_for(plan, "first"), fixture, execution_id="execution-first"
            )
            self.assertTrue(fixture.entered.wait(timeout=1))
            try:
                with self.assertRaises(LifecycleError) as raised:
                    second.start(
                        plan, permit_for(plan, "second"), fixture,
                        execution_id="execution-second",
                    )
                self.assertEqual(
                    raised.exception.diagnostic.code,
                    "XVERSE-RUNTIME-CONCURRENT-MUTATION",
                )
                self.assertEqual(fixture.start_count, 0)
            finally:
                fixture.release.set()
            self.assertEqual(running.result().status, "running")
        self.assertEqual(fixture.start_count, 1)

    def test_c11_readiness_unavailable_and_timeout_never_succeed(self) -> None:
        """C11: classify unavailable and timed-out observations without success."""

        cases = (
            (UnavailableProvider("controlled-provider", isolation_attestation=isolation_attestation(), allowed_executables=(EXECUTABLE,)), "unavailable", 0.1),
            (NotReadyProvider("controlled-provider", isolation_attestation=isolation_attestation(), allowed_executables=(EXECUTABLE,)), "not-ready", 0.1),
            (SlowObservationProvider("controlled-provider", isolation_attestation=isolation_attestation(), allowed_executables=(EXECUTABLE,)), "timeout", 0.001),
        )
        for index, (fixture, expected, timeout) in enumerate(cases, 1):
            with self.subTest(expected=expected):
                plan = lifecycle_plan(observe_timeout=timeout)
                controller = LifecycleController(InMemoryEvidenceJournal())
                controller.start(plan, permit_for(plan, str(index)), fixture, execution_id=f"execution-{index}")
                self.assertEqual(controller.observe(f"execution-{index}", fixture).status, expected)

    def test_c12_restart_with_unverifiable_handle_remains_unowned(self) -> None:
        """C12: refuse reconciliation when a fresh provider cannot verify the handle."""

        plan = lifecycle_plan()
        journal = InMemoryEvidenceJournal()
        first_provider = provider()
        first = LifecycleController(journal)
        first.start(plan, permit_for(plan), first_provider, execution_id="execution")
        restarted = LifecycleController(journal)
        self.assertFalse(restarted.reconcile(plan, "execution", provider()))

    def test_c13_restricted_provider_detail_is_not_exposed(self) -> None:
        """C13: retain only a stable exception type in platform evidence."""

        plan = lifecycle_plan()
        journal = InMemoryEvidenceJournal()
        fixture = RestrictedFailureProvider(
            "controlled-provider",
            isolation_attestation=isolation_attestation(),
            allowed_executables=(EXECUTABLE,),
        )
        controller = LifecycleController(journal)
        with self.assertRaises(LifecycleError) as raised:
            controller.start(plan, permit_for(plan), fixture, execution_id="execution")
        public = json.dumps(journal.public_records(), sort_keys=True)
        for restricted in ("password=restricted", "10.1.2.3", "/private/legacy/path"):
            self.assertNotIn(restricted, str(raised.exception))
            self.assertNotIn(restricted, public)

    def test_c14_cleanup_cannot_use_discovered_identity(self) -> None:
        """C14: reject cleanup constructed from a name, PID, port, or path."""

        fixture = provider()
        fabricated = OwnedResourceHandle(
            opaque_id="pid-1234",
            execution_id="execution",
            action_id="cleanup",
            provider_id=fixture.provider_id,
            provider_kind=fixture.provider_kind,
            resource_identity="port:8080:/tmp/discovered",
        )
        with self.assertRaises(CompatibilityProviderError) as raised:
            fixture.cleanup(fabricated, 0.1)
        self.assertEqual(raised.exception.code, "XVERSE-COMPAT-HANDLE")
        self.assertEqual(fixture.start_count, 0)


if __name__ == "__main__":
    unittest.main()
