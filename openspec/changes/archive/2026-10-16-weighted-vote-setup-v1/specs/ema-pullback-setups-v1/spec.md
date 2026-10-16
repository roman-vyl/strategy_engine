## ADDED Requirements

### Requirement: Weighted vote setup is a supported setup

The engine SHALL support `weighted_vote_setup` in addition to the existing setups, with the semantics specified by
`ema-pullback-weighted-vote-setup-v1`. It SHALL be dispatched by `component_id` like any other setup.

#### Scenario: Spec without a weighted vote

- **WHEN** a spec declares no `weighted_vote_setup`
- **THEN** its setup masks, evidence and composition SHALL be identical to those before this change.
