## ADDED Requirements

### Requirement: History policy for weighted vote inputs

The history requirement of a `weighted_vote_setup` SHALL be the maximum of the requirements of the operands and predicates in its
inputs, each derived exactly as for the same operand or predicate in a `composite_setup` child. The weighted vote SHALL add no
history of its own. An input that the planner does not recognise SHALL fail closed, as for composite children.

#### Scenario: Vote over episode operands

- **WHEN** every input reads segment or leg mean operands of a declared episode
- **THEN** the history requirement SHALL equal that of the same operands in a composite child.
