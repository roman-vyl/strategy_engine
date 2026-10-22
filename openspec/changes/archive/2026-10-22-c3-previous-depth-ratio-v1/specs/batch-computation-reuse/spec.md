## ADDED Requirements

### Requirement: Previous pullback depth identity

A pullback depth operand with `touch: previous` SHALL be a node of the pullback depth family whose params carry the touch; one with
`touch` absent or `current` SHALL keep the identity it had before this change.

#### Scenario: Current depth identity unchanged

- **WHEN** a spec writes `{"pullback_depth": {"episode": "trend", "touch": "current"}}`
- **THEN** it SHALL resolve to the same node as `{"pullback_depth": {"episode": "trend"}}`.
