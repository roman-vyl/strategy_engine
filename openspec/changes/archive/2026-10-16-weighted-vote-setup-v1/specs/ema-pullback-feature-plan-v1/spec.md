## ADDED Requirements

### Requirement: Feature plan of weighted vote inputs

Feature references inside the operands and predicates of `weighted_vote_setup` inputs SHALL be planned exactly as feature references
inside `composite_setup` children. For a spec without `weighted_vote_setup` the plan (features, order and labels) SHALL be unchanged.

#### Scenario: Feature used only by a vote input

- **WHEN** a feature is referenced only inside a weighted vote input
- **THEN** it SHALL be in the feature plan once, with the same label as in a composite child.
