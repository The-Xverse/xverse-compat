# Data Model: Controlled Gateway Rebuild

## RebuildManifest

- `schema_version`: exact supported manifest schema version.
- `source_revision`: full Git commit SHA.
- `source_tree`: full Git tree SHA.
- `patch_sha256`: lowercase SHA-256 of the external patch file.
- `git_sha256`: lowercase SHA-256 of the exact Git executable.
- `tool_sha256`: logical build-tool names mapped to exact executable SHA-256 values.
- `allowed_patch_paths`: unique normalized relative regular-file paths.
- `steps`: ordered `BuildStep` values.
- `output_path`: normalized relative regular-file path produced under each stage.
- `environment`: explicit non-secret name/value map.
- `metadata`: public-safe string map for evidence correlation.

## BuildStep

- `executable`: logical allowlist name, not a filesystem path supplied by the manifest.
- `arguments`: ordered literal argument vector; placeholders are limited to declared stage variables.
- `working_directory`: normalized relative directory under the stage.
- `timeout_seconds`: positive bounded wall-clock ceiling for the step.

## RebuildResult

- exact manifest, source revision/tree, patch, Git, build-tool, and step digests;
- digest observed for attempt A and attempt B;
- accepted artifact digest when both match;
- `reproducible`; always true for a returned success result;
- public metadata copied after safety validation.

## Invariants

1. All digest fields use `sha256:` plus 64 lowercase hexadecimal characters.
2. All paths are relative, normalized, traversal-free, and contain no symbolic-link component.
3. Every patched file is declared and every declared output is a regular file under its stage.
4. Patch validation completes before application.
5. No result exists unless two independent attempts match.
6. Result data contains no build output or environment values.
