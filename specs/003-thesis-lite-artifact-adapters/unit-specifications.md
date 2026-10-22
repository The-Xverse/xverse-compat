# Unit specifications: Phase 4 compatibility descriptors

Each row is one test. IDs map to the thesis verification cases V01–V07.

## `xverse_compat.selection` (V01, V02)

| ID | Test | Given | Expect |
| --- | --- | --- | --- |
| U-SEL-01 | record loads and covers every required stream once | `xdl/selection/aeb-sim-selection.json` | `REQUIRED_STREAMS` == set of streams; no duplicates |
| U-SEL-02 | dispositions are consistent | the record | `supplied`/`adapter` have a supplier that resolves to a pin or adapter id; `blocked` cite a gap id `G<n>` |
| U-SEL-03 | no unneeded technology selected | the record | every pin is referenced by at least one stream; `notSelected` non-empty and names the excluded items |
| U-SEL-04 | pins are committed and digested | the record | each pin: `sourceRef` with 40-hex commit or release artifact; `present` ⇒ `digest` `sha256:[0-9a-f]{64}` and `digestCommand`; `NOT_AVAILABLE` ⇒ `reason` |
| U-SEL-05 | negative: missing stream | record without `radar` | `SelectionError` code `XVERSE-COMPAT-SELECTION-STREAM-MISSING` |
| U-SEL-06 | negative: duplicate stream | two `camera` rows | code `…-STREAM-DUPLICATE` |
| U-SEL-07 | negative: supplied without supplier | `supplied` row, no supplier | code `…-SUPPLIER-MISSING` |
| U-SEL-08 | negative: blocked without gap | `blocked` row, no blocker | code `…-BLOCKER-MISSING` |
| U-SEL-09 | negative: floating sourceRef | `sourceRef` ending in `@main` | code `…-PIN-FLOATING` |
| U-SEL-10 | negative: bad digest | `digest: sha256:zz` | code `…-PIN-DIGEST` |
| U-SEL-11 | digest recomputation (owned files) | temp dir with two files of known content, pins with `localPath` | `verify_pins` returns `match` for both; altered content → `mismatch`; missing file → `absent`; never raises |
| U-SEL-12 | digest recomputation (host artifacts) | the real record; skipped with reason if a local path is absent | every `present` pin reports `match` |

## `xverse_compat.descriptors` (V03, V04)

| ID | Test | Expect |
| --- | --- | --- |
| U-DSC-01 | graph validates with Profile 0.2 at the pinned platform | `validation.is_valid`; two catalog entries (`carla-server`, `bridge-auto`) |
| U-DSC-02 | plans derive with blockers, never execution-eligible | each plan has blockers, `not plan.is_plannable` (the platform defines plannable as blocker-free), `not plan.execution_eligible`, a process action and a digest; the bridge binding's blockers include `XVERSE-PLAN-THESIS-G1` |
| U-DSC-03 | artifact digests equal the pins | catalog `artifact_digests` ⊆ pin digests |
| U-DSC-04 | negatives, layer stated | floating revision → owned `…-REVISION`; missing digest → platform binding gate `XDL-BINDING-ARTIFACT-INTEGRITY` (wrapped as `…-VALIDATION`; catalog derivation would also reject it); relative executable / `inheritedHandles` not `"closed"` / `implicitShell: true` / undeclared env name → platform schema (`…-VALIDATION`); `condition: "wait 10 s"` → owned `…-READINESS-DURATION`; unknown dependency → owned `…-DEPENDENCY`; missing G1 blocker or no blocker at all → owned `…-BLOCKER`; claiming a non-supplied stream → owned `…-STREAM-TRACE` |
| U-DSC-05 | no discovery | AST of `descriptors.py` imports none of `subprocess`, `socket`, `psutil`, `glob`, `os.scandir` use |

## `xverse_compat.contracts` (V05)

| ID | Test | Expect |
| --- | --- | --- |
| U-CON-01 | every statement has evidence | each row cites a file path with line or a command output hash present in the inventory |
| U-CON-02 | every gap is a blocker row | G1–G5 appear with status `NOT_VERIFIED` or `mismatch` and a blocker text |

## `xverse_compat.adapters.bridge_samples` (V06)

| ID | Test | Expect |
| --- | --- | --- |
| U-ADP-01 | decode `ego_vehicle/speed` | `"37"` → `speed_kmh == 37`, source key, both timestamps labelled |
| U-ADP-02 | malformed | `"nan"`, `"37.5"`, `""` → diagnostic `…-SAMPLE-MALFORMED`, no value |
| U-ADP-03 | out of range | `"-1"`, `"1000"` → `…-SAMPLE-RANGE` (declared 0–400 km/h) |
| U-ADP-04 | stale | received older than declared freshness → `…-SAMPLE-STALE` |
| U-ADP-05 | duplicate | same sequence twice → `…-SAMPLE-DUPLICATE` |
| U-ADP-06 | undeclared key | `foo/bar` → `…-SAMPLE-KEY` |
| U-ADP-07 | status decoders (attended case) | `vehicle/status/braking_status` `"0.5"` → 0.5; `"1.5"` → `…-SAMPLE-RANGE` |
| U-ADP-08 | no session | AST: no `zenoh` import in the adapter |

## `xverse_compat.admission` (V07)

| ID | Test | Expect |
| --- | --- | --- |
| U-ADM-01 | record binds every file | each listed path's sha256 recomputes |
| U-ADM-02 | platform identity | `platform.revision` equals the accepted main given by the caller; `xdl/schemas` and `xdl/profiles` tree digests recorded; lock re-pinned to the same tree |
| U-ADM-03 | authority absent, blockers listed | `executionAuthority == "absent"`; blockers ⊇ open gaps |
| U-ADM-04 | negative | wrong platform revision or altered descriptor → `AdmissionError` |
