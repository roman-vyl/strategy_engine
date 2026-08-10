## REMOVED Requirements

### Requirement: No semantic overclaim
**Reason**: This requirement documented the scope boundary and forward-looking commitment of the original foundation/migration-stage change (no semantic parity claimed yet, "golden parity against BBB" promised as the next step). It is a historical migration-stage guard, not durable production semantics, and its forward reference to a future BBB golden-parity follow-up no longer applies now that the parity oracle is retired.
**Migration**: None — the durable architectural guarantee that production code does not depend on BBB/legacy runtime is preserved by other canonical requirements (e.g. "No legacy production imports", "No legacy runtime").
