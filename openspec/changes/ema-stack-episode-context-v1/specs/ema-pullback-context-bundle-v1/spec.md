## MODIFIED Requirements

### Requirement: Strategy-owned context construction

Strategy Engine SHALL construct declared `ema_pullback` context providers internally after Indicator Engine feature evaluation. External callers SHALL NOT provide precomputed context masks or state series.

The supported providers SHALL be `htf_context` and `ema_stack_episode`. Any other `component_id` SHALL be rejected.

#### Scenario: Construct contexts from evaluated features

- **WHEN** a strategy range has an evaluated FeatureFrame
- **THEN** Strategy Engine SHALL construct its declared context providers internally
- **AND** SHALL NOT require precomputed context masks or states from the caller.

#### Scenario: Episode provider beside an HTF provider

- **WHEN** a spec declares one `htf_context` and one `ema_stack_episode` context
- **THEN** both SHALL be built once in the same ContextBundle
- **AND** the `htf_context` output SHALL be identical to its output without the episode context.

## ADDED Requirements

### Requirement: Episode context in the API result

For an `ema_stack_episode` context, the strategy range result SHALL carry:

- the provider metadata;
- per side, the per-bar fields on the context time axis;
- per side, a table with one row per zone: episode id, touch number, start bar, last-contact bar, false-break start and comeback bars when present, `S` and `P` points, and the up and down legs.

The `htf_context` output shape SHALL be unchanged.

#### Scenario: Zone table matches the per-bar fields

- **WHEN** the result carries an episode context
- **THEN** each zone row's touch number and start bar SHALL match a bar where `touch_start` is 1 with that `touch_number`.

### Requirement: Episode contexts are not gates

A context-consumption policy, an exit consumption or a `state` predicate that references an `ema_stack_episode` context SHALL be rejected statically.

#### Scenario: Gate on an episode context

- **WHEN** a setup's `context_consumption` names an `ema_stack_episode` context
- **THEN** static validation SHALL reject the spec.
