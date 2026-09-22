# Acceptance Checklist: Compatibility Provider Boundary

**Status**: Design and target-neutral conformance implementation accepted; selected-target work may begin

- [X] ACC001 Spec Kit resolves this companion feature and all design artifacts exist.
- [X] ACC002 The contract references platform lifecycle semantics without copying their models.
- [X] ACC003 XDL-derived provider ID/kind is the only selection input; no second descriptor exists.
- [X] ACC004 Provider operations require exact typed actions and exact issued ownership handles.
- [X] ACC005 Permit, lifecycle ordering, mutation exclusion, and evidence remain platform-owned.
- [X] ACC006 Secrets, ambient discovery, implicit shell, and broad cleanup are prohibited.
- [X] ACC007 Target selection, target implementation, and target execution remain separate gates.
- [X] ACC008 Fixture/provider lifecycle evidence cannot establish compatibility or parity.
- [X] ACC009 Separate review has no unresolved BLOCKER or MAJOR finding.
- [X] ACC010 Human review accepts this design before provider implementation begins.
- [X] ACC011 Exact platform version, dependency lock, and complete local-source content pin validate.
- [X] ACC012 Explicit composition root resolves exactly one provider ID/kind without discovery.
- [X] ACC013 Controlled fixture implements the imported process-action/handle protocol without execution.
- [X] ACC014 C01–C14 and source-policy tests pass with no subprocess or legacy interaction.
- [X] ACC015 Doxygen covers every Python source and produces warning-clean HTML/XML.
- [X] ACC016 Separate implementation review has no unresolved BLOCKER or MAJOR finding.
- [X] ACC017 Human review accepts T008–T011 before selected-target work begins.

## Decision record

**Reviewer**: User

**Date**: 2026-09-20

**Decision**: Approved the repaired provider-boundary design and authorized T008–T011 using only a
controlled target-neutral compatibility fixture.

**Exclusions**: No legacy target selection, target-specific provider, subprocess execution, legacy
execution permit, compatibility/parity claim, or legacy repository change.

**Implementation acceptance**: On 2026-09-20, the user explicitly approved ACC017 and directed work
to proceed to the selected-target decision. This authorizes decision preparation and review only; it
does not authorize target-specific implementation or legacy execution.
