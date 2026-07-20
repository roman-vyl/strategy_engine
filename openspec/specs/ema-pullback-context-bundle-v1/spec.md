# EMA Pullback Context Bundle v1 Specification

## Purpose

Define Strategy Engine-owned context construction, BBB-compatible context semantics, bundle reuse, stable API output, module boundaries, and golden parity for EMA Pullback.

## Requirements

### Requirement: Strategy-owned context construction

Strategy Engine SHALL construct declared `ema_pullback` context providers internally after Indicator Engine feature evaluation. External callers SHALL NOT provide precomputed context masks or state series.

#### Scenario: Construct contexts from evaluated features

- **WHEN** a strategy range has an evaluated FeatureFrame
- **THEN** Strategy Engine SHALL construct its declared context providers internally
- **AND** SHALL NOT require precomputed context masks or states from the caller.

### Requirement: BBB-compatible HTF context semantics

For an `htf_context` provider, the engine SHALL classify each base-grid position as `up` when fast EMA is greater than anchor EMA and anchor EMA is greater than slow EMA; `down` when fast EMA is less than anchor EMA and anchor EMA is less than slow EMA; and `neutral` otherwise. Null, missing, or non-ready values SHALL resolve to neutral. Required feature columns absent from the FeatureFrame SHALL produce an all-neutral provider output.

#### Scenario: Classify an HTF EMA stack

- **WHEN** fast, anchor, and slow EMA values are evaluated on the base grid
- **THEN** strict ascending or descending stack order SHALL produce `up` or `down`
- **AND** all other, missing, null, or non-ready values SHALL produce `neutral`.

### Requirement: One bundle per evaluation

The engine SHALL construct one ContextBundle per strategy range evaluation and SHALL reuse that bundle for downstream signal and exit consumers. Context providers SHALL NOT trigger additional Market Data Service reads or indicator calculations.

#### Scenario: Reuse contexts downstream

- **WHEN** downstream consumers need strategy context during one evaluation
- **THEN** they SHALL reuse the ContextBundle built for that evaluation
- **AND** context construction SHALL NOT trigger another market read or indicator calculation.

### Requirement: Stable API result

The strategy range response SHALL expose an aligned context time axis and, for each context reference, provider metadata, state values, and boolean up/down/neutral masks. The strategy catalog and evaluation result SHALL advertise `contexts_ready=true`; their overall stage and decision readiness SHALL match the currently wired production evaluator.

#### Scenario: Return context output in a range result

- **WHEN** context output is included in a successful strategy range response
- **THEN** it SHALL contain the aligned time axis, provider metadata, states, and masks
- **AND** readiness metadata SHALL accurately describe the accumulated production stage.

### Requirement: Context module boundary

Context construction SHALL remain transport-neutral and SHALL NOT itself evaluate context-consumption policies, blockers, setups, triggers, entries, exits, managed execution, or runtime incremental processing. Those behaviors MAY be implemented by separate downstream layers.

#### Scenario: Evaluate a context provider

- **WHEN** the context module builds a ContextBundle
- **THEN** it SHALL only derive provider outputs from the FeatureFrame
- **AND** SHALL leave downstream policy and decision evaluation to separate layers.

### Requirement: Golden parity

Acceptance SHALL include direct execution of copied BBB context code and exact comparison of state and mask outputs, including warmup and neutral fallback cases.

#### Scenario: Run context golden parity

- **WHEN** representative context fixtures are evaluated by both implementations
- **THEN** state and mask outputs SHALL match exactly, including warmup and neutral fallback positions.
