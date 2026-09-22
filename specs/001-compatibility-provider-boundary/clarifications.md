# Clarifications: Compatibility Provider Boundary

**Date**: 2026-09-20

No blocking clarification remains. The platform M3 specification and the user's 2026-09-20 approval
establish the decisions required for the target-neutral conformance increment.

## Recorded decisions

1. This feature may implement an in-memory process-action conformance fixture and explicit composition
   root. It implements no target-specific provider and invokes no process.
2. Platform lifecycle types and contracts are referenced, not copied.
3. Provider selection uses the exact ID/kind from the XDL-derived plan and introduces no authored registry.
4. Target selection and legacy execution remain separate human gates.
5. No M0 candidate is preferred or selected by architectural inference.
6. Current M3 compatibility providers are process-action based. Non-process typed actions require a
   separate platform feature; `None` never means provider-private configuration.
7. Provider identity is the exact ID/kind pair across plan, implementation, handle, evidence, and reconciliation.
8. Authorization covers T008–T011 only. Target selection, target-specific implementation, and legacy
   execution remain separately gated.
