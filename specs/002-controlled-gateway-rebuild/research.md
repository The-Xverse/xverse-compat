# Research: Controlled Gateway Rebuild

## Decision 1: External digest-pinned patch bundle

**Decision**: Accept a unified-diff patch as an external controlled input, verify its SHA-256, parse
its paths against an exact allowlist, then use Git's patch validation and application in the isolated
staged tree.

**Rationale**: A committed patch could disclose removed private values and source context. A generic
text replacement is too weak for review. Digest identity preserves a public binding without publishing
restricted contents.

**Alternatives considered**: Committing the target patch was rejected for public-safety reasons.
Writing replacement source files was rejected because it would duplicate legacy implementation.

## Decision 2: Export committed tree rather than copy checkout

**Decision**: Verify `HEAD` and its tree, then export the exact commit with Git archive into a new
exclusive directory.

**Rationale**: This excludes untracked, modified, ignored, and repository metadata from the build input
and leaves the checkout unchanged.

**Alternatives considered**: Recursive filesystem copy includes ambient state. A worktree writes Git
administrative state and offers no benefit for this one-way disposable stage.

## Decision 3: Explicit command vectors and minimal environment

**Decision**: Each step is an argument vector with a relative working directory. The runner resolves
the executable from an externally supplied allowlist and creates an environment only from manifest
entries plus the selected executable path.

**Rationale**: This prevents shell interpretation, source-provided executable selection, and ambient
environment inheritance.

**Alternatives considered**: Shell command strings and inherited `PATH` were rejected because they make
the effective build depend on unreviewed host state.

The manifest also pins the SHA-256 of Git and every allowlisted build executable. These executable
digests do not pin their dynamic libraries or create process/network containment; a real target build
still requires an immutable environment and isolation attestation.

## Decision 4: Two independent stages

**Decision**: Export, patch, and build twice from scratch, then compare the exact declared output bytes.

**Rationale**: Reusing one stage can hide untracked state and cannot establish a repeated result.

**Alternatives considered**: Two builds in one directory and clean/rebuild were rejected because cleanup
quality would become part of the trust boundary.

## Decision 5: Synthetic validation before target use

**Decision**: Unit and integration tests create a temporary Git repository and use a tiny interpreter
script as an allowlisted builder. No repository-supplied binary or network process runs.

**Rationale**: It validates the envelope independently of unresolved SD-0001 runtime gates.

**Alternatives considered**: Building the current gateway immediately was rejected because the target
patch, peer ABI, environment, and vendor disposition are not approved inputs.
