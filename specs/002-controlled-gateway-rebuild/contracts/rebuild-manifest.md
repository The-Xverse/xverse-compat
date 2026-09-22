# Controlled rebuild manifest contract

The manifest is UTF-8 JSON with no duplicate keys. Schema version `1` has this shape:

```json
{
  "schemaVersion": 1,
  "sourceRevision": "<40 lowercase hexadecimal characters>",
  "sourceTree": "<40 lowercase hexadecimal characters>",
  "patchSha256": "sha256:<64 lowercase hexadecimal characters>",
  "gitSha256": "sha256:<64 lowercase hexadecimal characters>",
  "toolSha256": {"approved-builder": "sha256:<64 lowercase hexadecimal characters>"},
  "allowedPatchPaths": ["relative/source.cpp"],
  "steps": [
    {
      "executable": "approved-builder",
      "arguments": ["literal", "{stage}"],
      "workingDirectory": ".",
      "timeoutSeconds": 60
    }
  ],
  "outputPath": "build/gateway",
  "environment": {"NON_SECRET_MODE": "reviewed"},
  "metadata": {"decision": "SD-0001"}
}
```

Only `{stage}` and `{attempt}` placeholders are supported. Unknown fields, duplicate values, invalid
names, empty required collections, absolute/traversing paths, NUL bytes, unsupported placeholders,
and values resembling credentials or private endpoints are rejected.

The caller supplies an executable allowlist separately as a mapping from each logical step name to one
absolute regular executable. Host paths are excluded from the portable manifest and public result;
the manifest and result retain the logical names and verified executable digests.

## Stable failure codes

`manifest-invalid`, `source-identity-mismatch`, `patch-digest-mismatch`, `patch-invalid`,
`patch-target-denied`, `stage-failed`, `build-command-denied`, `tool-identity-mismatch`, `build-failed`,
`output-invalid`, `reproducibility-mismatch`, and `result-write-failed` are the complete public failure
categories for schema version 1.
