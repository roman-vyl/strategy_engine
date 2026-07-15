# Specification: EMA Pullback Setups v1

## Requirement: Legacy setup parity

The engine SHALL implement `untouched_anchor_setup`, `ema_bounce_counter_setup`, and `anchor_stack_width_setup` with bar-aligned outputs equivalent to the copied BBB implementation for identical market bars, features, parameters, and side.

## Requirement: Stateful bounce semantics

The EMA bounce counter SHALL preserve trend episode transitions, pending bounce windows, completed/effective counts, maximum-bounce admission, and reset behavior exactly. Batch range evaluation SHALL process bars in ascending order.

## Requirement: Context consumption order

When a setup has `context_consumption`, the engine SHALL calculate the local setup mask first and apply the context gate second. It SHALL NOT let context policy alter the intrinsic setup state machine.

## Requirement: Setup composition

Multiple setup rules SHALL be composed using logical AND in declared order. The composed mask SHALL then be ANDed with the side's `pre_setup_allowed` mask to produce `pre_trigger_allowed`.

## Requirement: Honest readiness

The Strategy API SHALL report `stage=setups_ready`, `setups_ready=true`, and `decisions_ready=false`. It SHALL NOT expose `pre_trigger_allowed` as a final entry decision.

## Requirement: Evidence

The response SHALL expose local, context-gated, and final masks for each setup plus component-specific trace fields needed for BBB diagnostics and parity.
