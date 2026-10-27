## ADDED Requirements

### Requirement: Signed and only-if identity and cost

Signed and only-if operands SHALL each have their own node family. The upstream SHALL be the inner operand's node, plus the requirement
operands' nodes for only-if. A spec without them SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over the same signed or only-if operand
- **THEN** that operand and its inputs SHALL each be computed once per batch per side.
