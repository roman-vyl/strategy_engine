## REMOVED Requirements

### Requirement: Complete explicit semantic coverage
**Reason**: Strategy Engine's migration from BBB is complete. The explicit parity manifest is a migration-era acceptance artifact, not a permanent canonical requirement; native Engine tests already cover the same semantic stages independently.
**Migration**: Native Engine tests under `tests/` remain the verification layer for the covered stages. No replacement manifest or parity gate is introduced.

### Requirement: Immutable source provenance
**Reason**: The copied BBB source under `legacy_source/` is being removed; provenance verification against it is no longer meaningful.
**Migration**: None — production code never depended on `legacy_source`, and that architectural boundary is preserved by other canonical requirements.

### Requirement: Reproducible acceptance command
**Reason**: The documented parity command (`scripts/run_semantic_parity_gate.py`) exists only to run the retired parity oracle.
**Migration**: The project's existing native test suite (`pytest`) remains the reproducible acceptance command for production semantics.

### Requirement: Machine-readable report
**Reason**: The JSON parity report exists only to report the retired parity oracle's results.
**Migration**: None — standard test-runner output covers verification reporting needs going forward.

### Requirement: Honest parity boundary
**Reason**: This requirement documents exclusions for a parity claim mechanism that is being retired in its entirety.
**Migration**: None — no replacement parity claim is made.

### Requirement: Consumer acceptance gate
**Reason**: New consumers no longer accept Strategy Engine semantics via a BBB parity report; the copied BBB snapshot the gate referenced is being removed.
**Migration**: None — no replacement consumer acceptance gate is introduced by this change.
