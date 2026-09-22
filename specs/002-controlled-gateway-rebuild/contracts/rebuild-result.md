# Controlled rebuild result contract

A successful result is canonical JSON containing only:

```json
{
  "schemaVersion": 1,
  "manifestSha256": "sha256:...",
  "sourceRevision": "...",
  "sourceTree": "...",
  "patchSha256": "sha256:...",
  "gitSha256": "sha256:...",
  "toolSha256": {"approved-builder": "sha256:..."},
  "stepsSha256": "sha256:...",
  "attemptDigests": ["sha256:...", "sha256:..."],
  "artifactSha256": "sha256:...",
  "reproducible": true,
  "metadata": {"decision": "SD-0001"}
}
```

The result deliberately omits source/patch paths, executable paths, command output, environment values,
timestamps, host identity, and any readiness or compatibility field. Errors expose a stable code and a
fixed public message only.
