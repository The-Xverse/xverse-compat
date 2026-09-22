"""Explicit provider assembly and an in-memory process-action conformance fixture."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePath
import re
import threading

from xverse_xdl import (
    IsolationAttestation,
    LifecyclePlan,
    LifecycleProvider,
    OwnedResourceHandle,
    ProcessAction,
)

_SENSITIVE_ENVIRONMENT = re.compile(
    r"(?i)(?:password|passwd|secret|token|credential|api_?key)"
)


class CompatibilityProviderError(RuntimeError):
    """Stable public-safe failure raised by compatibility boundary code."""

    def __init__(self, code: str, message: str) -> None:
        """Create a classified failure containing no target output.

        @param code Stable compatibility failure code.
        @param message Public-safe explanation.
        """

        super().__init__(message)
        self.code = code


@dataclass
class _Activation:
    """Provider-private state for one exact in-memory fixture resource."""

    handle: OwnedResourceHandle
    action: ProcessAction
    status: str


class ProviderCompositionRoot:
    """Resolve one exact provider from an explicitly supplied finite sequence."""

    def __init__(self, providers: Sequence[LifecycleProvider]) -> None:
        """Copy constructed providers without performing discovery.

        @param providers Finite provider instances supplied by the caller.
        """

        self._providers = tuple(providers)

    def resolve(self, plan: LifecyclePlan) -> LifecycleProvider:
        """Return the unique provider matching the plan ID and kind.

        @param plan Platform-owned lifecycle plan containing the selected pair.
        @return The single exact provider implementation.
        @raises CompatibilityProviderError If no provider or multiple providers match.
        """

        matches = tuple(
            provider
            for provider in self._providers
            if (provider.provider_id, provider.provider_kind)
            == (plan.provider_id, plan.provider_kind)
        )
        if not matches:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-PROVIDER-UNKNOWN",
                "no explicitly supplied provider matches the lifecycle plan",
            )
        if len(matches) != 1:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-PROVIDER-AMBIGUOUS",
                "multiple explicitly supplied providers match the lifecycle plan",
            )
        return matches[0]


class ConformanceProcessProvider:
    """Model the process-provider contract entirely in memory for conformance tests.

    The fixture validates an explicit :class:`~xverse_xdl.ProcessAction`, isolation
    declaration, allowlist, environment-name set, and exact ownership handle. It
    never opens a process, filesystem resource, network connection, or legacy asset.
    """

    provider_kind = "process"

    def __init__(
        self,
        provider_id: str,
        *,
        isolation_attestation: IsolationAttestation,
        allowed_executables: Iterable[str],
        available_environment_names: Iterable[str] = (),
    ) -> None:
        """Bind the fixture to explicit non-secret process-action constraints.

        @param provider_id Exact identity selected by the lifecycle plan.
        @param isolation_attestation Caller-reviewed isolation declaration.
        @param allowed_executables Absolute executable names accepted by the fixture.
        @param available_environment_names Explicit non-secret names available to actions.
        @raises ValueError If construction inputs are empty, relative, or secret-like.
        """

        if not provider_id.strip():
            raise ValueError("provider ID is required")
        execution_root = PurePath(isolation_attestation.execution_root)
        if not execution_root.is_absolute() or ".." in execution_root.parts:
            raise ValueError("execution root must be absolute and contain no parent traversal")
        executables = frozenset(str(PurePath(value)) for value in allowed_executables)
        if not executables or any(
            not PurePath(value).is_absolute() or ".." in PurePath(value).parts
            for value in executables
        ):
            raise ValueError("absolute traversal-free executable paths are required")
        environment_names = frozenset(available_environment_names)
        if any(_SENSITIVE_ENVIRONMENT.search(name) for name in environment_names):
            raise ValueError("secret-like environment names are prohibited")

        self.provider_id = provider_id
        self._execution_root = execution_root
        self._allowed_executables = executables
        self._available_environment_names = environment_names
        self._activations: dict[str, _Activation] = {}
        self._activation_keys: dict[tuple[str, str], str] = {}
        self._counter = 0
        self._start_count = 0
        self._stop_count = 0
        self._lock = threading.Lock()

    @property
    def start_count(self) -> int:
        """Return the number of distinct in-memory resources created."""

        with self._lock:
            return self._start_count

    @property
    def stop_count(self) -> int:
        """Return the number of resources transitioned from running to stopped."""

        with self._lock:
            return self._stop_count

    def _validate_action(self, action: ProcessAction | None, timeout_seconds: float) -> ProcessAction:
        """Validate one explicit action against construction-time constraints."""

        if not isinstance(action, ProcessAction):
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-ACTION-REQUIRED",
                "the compatibility provider requires an explicit process action",
            )
        if timeout_seconds <= 0:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-TIMEOUT",
                "the provider timeout must be positive",
            )
        if ".." in PurePath(action.executable).parts:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-EXECUTABLE",
                "the process action executable contains parent traversal",
            )
        if action.executable not in self._allowed_executables:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-EXECUTABLE",
                "the process action executable is outside the explicit allowlist",
            )
        if ".." in PurePath(action.working_directory).parts:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-EXECUTION-ROOT",
                "the process action working directory contains parent traversal",
            )
        try:
            PurePath(action.working_directory).relative_to(self._execution_root)
        except ValueError as error:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-EXECUTION-ROOT",
                "the process action working directory is outside the execution root",
            ) from error
        missing = tuple(
            name for name in action.environment_names
            if name not in self._available_environment_names
        )
        if missing:
            raise CompatibilityProviderError(
                "XVERSE-COMPAT-ENVIRONMENT",
                "the process action requests an unavailable explicit environment name",
            )
        return action

    def start(
        self,
        action: ProcessAction | None,
        execution_id: str,
        action_id: str,
        timeout_seconds: float,
    ) -> OwnedResourceHandle:
        """Create or return one idempotent in-memory fixture resource.

        @param action Exact platform process action; ``None`` is rejected.
        @param execution_id Controller-selected execution identity.
        @param action_id Controller-selected start-action identity.
        @param timeout_seconds Positive operation timeout.
        @return Exact provider-issued ownership handle.
        @raises CompatibilityProviderError If action or repeat bindings are invalid.
        """

        validated = self._validate_action(action, timeout_seconds)
        key = (execution_id, action_id)
        with self._lock:
            existing_id = self._activation_keys.get(key)
            if existing_id is not None:
                existing = self._activations[existing_id]
                if existing.action != validated:
                    raise CompatibilityProviderError(
                        "XVERSE-COMPAT-IDEMPOTENCY",
                        "the repeated activation uses a different process action",
                    )
                return existing.handle
            self._counter += 1
            opaque_id = f"compat-fixture-{self._counter:04d}"
            handle = OwnedResourceHandle(
                opaque_id=opaque_id,
                execution_id=execution_id,
                action_id=action_id,
                provider_id=self.provider_id,
                provider_kind=self.provider_kind,
                resource_identity=f"in-memory:{opaque_id}",
            )
            self._activations[opaque_id] = _Activation(handle, validated, "running")
            self._activation_keys[key] = opaque_id
            self._start_count += 1
            return handle

    def _owned_status(self, handle: OwnedResourceHandle) -> str:
        """Validate *handle* and copy its status while holding the state lock."""

        with self._lock:
            activation = self._activations.get(handle.opaque_id)
            if activation is None or activation.handle != handle:
                raise CompatibilityProviderError(
                    "XVERSE-COMPAT-HANDLE",
                    "the provider does not own the supplied resource handle",
                )
            return activation.status

    def observe(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Return the status of one exactly owned in-memory resource."""

        if timeout_seconds <= 0:
            raise CompatibilityProviderError("XVERSE-COMPAT-TIMEOUT", "the provider timeout must be positive")
        return self._owned_status(handle)

    def stop(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Idempotently stop one exactly owned in-memory resource."""

        if timeout_seconds <= 0:
            raise CompatibilityProviderError("XVERSE-COMPAT-TIMEOUT", "the provider timeout must be positive")
        with self._lock:
            activation = self._activations.get(handle.opaque_id)
            if activation is None or activation.handle != handle:
                raise CompatibilityProviderError(
                    "XVERSE-COMPAT-HANDLE", "the provider does not own the supplied resource handle",
                )
            if activation.status == "running":
                activation.status = "stopped"
                self._stop_count += 1
            return activation.status

    def cleanup(self, handle: OwnedResourceHandle, timeout_seconds: float) -> str:
        """Mark one exactly owned stopped fixture resource as cleaned."""

        if timeout_seconds <= 0:
            raise CompatibilityProviderError("XVERSE-COMPAT-TIMEOUT", "the provider timeout must be positive")
        with self._lock:
            activation = self._activations.get(handle.opaque_id)
            if activation is None or activation.handle != handle:
                raise CompatibilityProviderError(
                    "XVERSE-COMPAT-HANDLE", "the provider does not own the supplied resource handle",
                )
            if activation.status == "running":
                raise CompatibilityProviderError(
                    "XVERSE-COMPAT-CLEANUP-RUNNING",
                    "an owned resource must be stopped before cleanup",
                )
            activation.status = "cleaned"
            return "cleaned"

    def revalidate(self, handle: OwnedResourceHandle) -> bool:
        """Return whether the complete handle still identifies provider-owned state."""

        with self._lock:
            activation = self._activations.get(handle.opaque_id)
            return activation is not None and activation.handle == handle
