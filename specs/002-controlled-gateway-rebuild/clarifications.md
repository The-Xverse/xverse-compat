# Clarifications: Controlled Gateway Rebuild

**Date**: 2026-09-21

## Decisions

### C01 — Meaning of the user's authorization

The user accepted the configurable-rebuild recommendation. This authorizes implementation and
synthetic build validation of a controlled rebuild mechanism in `xverse-compat`. It does not supply
missing host/containment ownership, peer ABI, private deployment values, retention policy, resource
limits, readiness evidence, or an execution permit.

### C02 — Location of the target transformation

The public repository stores the mechanism and public digest metadata. A target patch that necessarily
touches restricted source/configuration remains in an approved external evidence store and is supplied
by exact digest. This avoids publishing removed private values or proprietary source context.

### C03 — Legacy immutability

The exact committed Git tree is exported into disposable staging. The mechanism never applies a patch,
generates build files, or writes outputs inside the legacy checkout.

### C04 — Reproducibility claim

Reproducible means two clean build attempts using the same exact inputs produced byte-identical declared
outputs. It does not mean portable across undeclared environments or functionally compatible.

### C05 — Target behavior

This increment does not select an endpoint, serialization, byte order, readiness probe, signal policy,
or logging retention rule. Those remain explicit restricted patch and selected-component decisions.
