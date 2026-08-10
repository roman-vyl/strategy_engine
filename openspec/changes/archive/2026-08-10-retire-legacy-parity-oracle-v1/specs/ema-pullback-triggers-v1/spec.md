## MODIFIED Requirements

### Requirement: Side symmetry

Long and short trigger inequalities SHALL mirror each other exactly.

#### Scenario: Mirror trigger evaluation by side

- **WHEN** equivalent long and short market configurations are evaluated
- **THEN** their probe, reclaim, touch, and close inequalities SHALL mirror between sides exactly.

## REMOVED Requirements

### Requirement: Golden parity
**Reason**: This requirement mandated comparing every trigger mask and trace field against the copied BBB implementation. The copied BBB source is being removed; native trigger tests already cover every supported trigger component for both trade sides independently.
**Migration**: Native tests under `tests/test_ema_pullback_triggers.py` remain the verification layer. No replacement parity gate is introduced.
