# xverse-compat

X-Verse vNext is a multi-industry cyber-physical systems experimentation platform under development.

Owns external descriptors, compatibility adapters, and deployment glue for unchanged legacy assets. Keep business/domain logic out.

## Current maturity
This repository is part of X-Verse Lite 1.0 rc.1, an engineering-integration baseline across
`xverse-platform`, `xverse-compat` and `xverse-blueprints`. It is not AEB validation, not M1 and not a
scientific result. See the release record [docs/releases/xverse-lite-1.0.md](docs/releases/xverse-lite-1.0.md).
For X-Verse Lite it contains:
- the compatibility descriptors and the admission record of the selected CARLA 0.9.15 server and
  bridge artifacts (`xdl/descriptors/aeb-sim/`, `xdl/selection/`; Thesis Lite Phase 4). The admission
  record keeps `executionAuthority` absent;
- the bridge route adapter (`src/xverse_compat/adapters/`; Phase 6);
- the owned CARLA client adapters on the pinned `carla` 0.9.15 cp310 client (`src/xverse_compat_carla/`;
  Phases 4b and 7), including the restore guard `xverse_compat_carla.restore`;
- the owned live units of the Lite CARLA closed loop, the driver and the stimulus, and their nonce-marker
  readiness helper (`src/xverse_compat/live/`; Phase 7 and stabilization S1c).

The blueprint that runs them is in `xverse-blueprints`, `automotive/thesis-lite-carla-closed-loop/`. The
engineering logs are under `docs/engineering/thesis-lite-*`. The offline suite runs against the
installed platform wheel:

```sh
env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src <venv>/bin/python -m pytest tests -q -p no:cacheprovider
```

The repository also keeps its earlier engineering setup: the reviewed design and the controlled
target-neutral conformance implementation for the companion side of the M3 compatibility-provider
boundary, and a controlled derivative-rebuild envelope that verifies exact source and external patch
identities, builds in two clean stages, and compares the declared outputs. The target-specific patch
remains a separately controlled, gated input. The SD-0001 gateway provider stays blocked, and rebuild
success does not permit the resulting artifact to run.
Platform results do not certify any legacy component.

## Engineering workflow
Spec Kit **0.14.0** is initialized with its official generic integration, Bash scripts, templates,
and bundled workflow. The generic integration uses `.specify/commands` because this workspace's
`.agents` and `.codex` directories are read-only. No permissions or agent directories were changed.

Read [engineering rules](AGENTS.md) and the [constitution](.specify/memory/constitution.md).
Ask the agent to read and follow `.specify/commands/speckit.<stage>.md`, supplying the feature
request as its input. Stages: constitution, specify, clarify, plan, tasks, analyze, implement.
Follow implementation with a separate architecture review. These Markdown commands are not shell
executables; slash-command discovery is not assumed for the generic integration.

The [M0 feature](../xverse-platform/specs/001-legacy-repository-inventory/spec.md) and its tasks live only in
xverse-platform. Run M0 prerequisite and evidence checks from that repository; companion
repositories intentionally have no active feature pointer until their own first capability.
See the [M0 quickstart](../xverse-platform/specs/001-legacy-repository-inventory/quickstart.md).

## Architecture and review gates
Dependencies flow from blueprints through domain profiles and XDL/platform APIs to runtime
abstractions. Existing production repositories remain read-only. Features must pass architecture,
compatibility, runtime (when applicable), test, reproducibility, and documentation gates.

Platform [ADR-0018](../xverse-platform/docs/adr/ADR-0018-platform-first-delivery-sequence.md) now
requires the main platform capability baselines and stable extension contracts before target-specific
legacy integration resumes. Existing provider and controlled-rebuild evidence remains retained, while
SD-0001 patching, execution, and parity are deferred.
The platform [SADS traceability register](../xverse-platform/docs/architecture/SADS_REQUIREMENTS_TRACEABILITY.md)
allocates all requirements from the supplied architecture reference; compatibility features retain
the applicable IDs without treating target requirements as implementation evidence.

See [architecture guidance](../xverse-platform/docs/architecture/XVERSE_VNEXT_ARCHITECTURE_AND_CODEX_GUIDANCE.md)
and the [legacy inventory](../xverse-platform/docs/legacy/REPOSITORY_INVENTORY.md). Relative cross-repository
links assume sibling checkouts with their repository names, as in this workspace.

M0 documents are intended for public-safe review. Referenced private GitHub evidence requires
existing repository access. Review of inventory boundaries, classifications, interfaces, and
dependencies is required before M1.

## License
See [LICENSE](LICENSE); the existing license is unchanged.

## M0 review status

The user confirmed the cross-repository M0 review on 2026-09-20. See the
[decision record](../xverse-platform/docs/reviews/M0_REVIEW_CHECKLIST.md) and
[supplemental references](../xverse-platform/docs/architecture/REFERENCE_REGISTER.md).
M1 specification/design can begin; no additional runtime capability is implemented by this confirmation.

## M3 compatibility-provider boundary

The [provider-boundary specification](specs/001-compatibility-provider-boundary/spec.md) references
the platform lifecycle API without copying its models. Current M3 compatibility providers are limited
to explicit process actions, and their exact provider ID/kind pair is carried through plans, ownership
handles, evidence, and reconciliation. Provider assembly must be explicit and closed-set.

The [provider contract](specs/001-compatibility-provider-boundary/contracts/provider.md), the blocked
[gateway contract candidate](specs/001-compatibility-provider-boundary/contracts/zenoh-someip-gateway.md),
[static interface projection](specs/001-compatibility-provider-boundary/contracts/zenoh-someip-interface-projection.md),
[design review](docs/reviews/001-compatibility-provider-boundary-design-review.md), and
[implementation review](docs/reviews/002-compatibility-provider-conformance-implementation-review.md),
plus its [target-contract review](docs/reviews/003-zenoh-someip-gateway-contract-review.md),
define the remaining gates. The exact `xverse-xdl==0.4.0` dependency is locked and the complete local
platform package surface is content-pinned by `platform-api.lock.json`.

Run the target-neutral checks:

```sh
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run python scripts/check_doxygen.py --self-test
```

All fixture behavior is in memory. It validates process actions but never invokes their executable.
SD-0001 nominates one exact gateway candidate but keeps its plan blocked. Completed selection,
target-specific implementation, and legacy execution each require their remaining recorded gates.
Use the platform [selection-closure packet](../xverse-platform/specs/005-component-catalog-compat-runtime/evidence/SD-0001-closure-packet.md)
for the required owner, environment, interface, readiness, retention, resource, and vendor decisions.

## Controlled derivative rebuilds

The [controlled-rebuild specification](specs/002-controlled-gateway-rebuild/spec.md),
[manifest contract](specs/002-controlled-gateway-rebuild/contracts/rebuild-manifest.md), and
[ADR-0017](../xverse-platform/docs/adr/ADR-0017-controlled-derivative-rebuilds.md) define the build-only
boundary. The committed mechanism never stores the restricted patch, inherits an ambient executable,
uses a shell, writes to the source checkout, or runs the resulting artifact.

Run its synthetic tests with the complete suite above. A future target invocation must provide an
external patch by exact digest, an absolute reviewed Git executable, an explicit build-tool allowlist,
and a new empty work root. Supplying that SD-0001 patch remains subject to ACC010 and the unresolved
platform decisions.
