## RENAMED Requirements

- FROM: `### Requirement: Legacy setup parity`
- TO: `### Requirement: Supported setup determinism`

## MODIFIED Requirements

### Requirement: Supported setup determinism

The engine SHALL implement `untouched_anchor_setup`, `ema_bounce_counter_setup`, and `anchor_stack_width_setup` with deterministic, bar-aligned outputs for identical market bars, features, parameters, and side.

#### Scenario: Evaluate a supported setup

- **WHEN** any supported setup receives identical inputs
- **THEN** its bar-aligned mask and trace SHALL be deterministic for those inputs.

### Requirement: Stateful bounce semantics

The EMA bounce counter SHALL preserve trend episode transitions, pending bounce windows, completed/effective counts, maximum-bounce admission, and reset behavior exactly. Batch range evaluation SHALL process bars in ascending order.

#### Scenario: Process an EMA bounce episode

- **WHEN** a batch range contains trend starts, touches, pending windows, completed bounces, or breaks
- **THEN** bars SHALL be processed in ascending order
- **AND** state transitions and counters SHALL follow the trend episode, pending-window, completed/effective count, maximum-bounce admission, and reset behavior above.

### Requirement: Evidence

The response SHALL expose local, context-gated, and final masks for each setup plus component-specific trace fields needed for verification and diagnostics.

#### Scenario: Inspect setup evidence

- **WHEN** setup evidence is requested in a strategy result
- **THEN** it SHALL contain local, context-gated, and final masks
- **AND** SHALL include the component-specific diagnostic trace.
