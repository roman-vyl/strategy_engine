# EMA Pullback Setups v1 Specification

## ADDED Requirements

### Requirement: Legacy setup parity

The engine SHALL implement `untouched_anchor_setup`, `ema_bounce_counter_setup`, and `anchor_stack_width_setup` with bar-aligned outputs equivalent to the copied BBB implementation for identical market bars, features, parameters, and side.

#### Scenario: Evaluate a supported setup

- **WHEN** any supported setup receives identical inputs to BBB
- **THEN** its bar-aligned mask and trace SHALL match the copied BBB implementation.

### Requirement: Stateful bounce semantics

The EMA bounce counter SHALL preserve trend episode transitions, pending bounce windows, completed/effective counts, maximum-bounce admission, and reset behavior exactly. Batch range evaluation SHALL process bars in ascending order.

#### Scenario: Process an EMA bounce episode

- **WHEN** a batch range contains trend starts, touches, pending windows, completed bounces, or breaks
- **THEN** bars SHALL be processed in ascending order
- **AND** all state transitions and counters SHALL match BBB.

### Requirement: Context consumption order

When a setup has `context_consumption`, the engine SHALL calculate the local setup mask first and apply the context gate second. It SHALL NOT let context policy alter the intrinsic setup state machine.

#### Scenario: Gate a stateful setup with context

- **WHEN** a setup declares context consumption
- **THEN** the local setup and trace SHALL be calculated before the context gate
- **AND** the gate SHALL only filter the resulting local mask.

### Requirement: Setup composition

Multiple setup rules SHALL be composed using logical AND in declared order. The composed mask SHALL then be ANDed with the side's `pre_setup_allowed` mask to produce `pre_trigger_allowed`.

#### Scenario: Compose multiple setup rules

- **WHEN** more than one setup is declared for a side
- **THEN** their final masks SHALL be AND-composed in declaration order
- **AND** `pre_trigger_allowed` SHALL equal `pre_setup_allowed` AND the composed setup mask.

### Requirement: Honest readiness and pipeline boundary

The Strategy API SHALL advertise setup readiness together with the exact accumulated production stage. `pre_trigger_allowed` SHALL remain the setup layer's intermediate artifact for downstream trigger and entry evaluation rather than an independent final entry decision.

#### Scenario: Return setup-stage evidence

- **WHEN** a strategy range response contains setup evidence
- **THEN** readiness metadata SHALL accurately describe the accumulated production stage
- **AND** downstream layers SHALL consume `pre_trigger_allowed` before a final entry is concluded.

### Requirement: Evidence

The response SHALL expose local, context-gated, and final masks for each setup plus component-specific trace fields needed for BBB diagnostics and parity.

#### Scenario: Inspect setup evidence

- **WHEN** setup evidence is requested in a strategy result
- **THEN** it SHALL contain local, context-gated, and final masks
- **AND** SHALL include the component-specific diagnostic trace.
