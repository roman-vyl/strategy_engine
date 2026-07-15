# EMA Pullback Triggers v1 Specification

## Requirement: Trigger ownership

The independent Strategy Engine SHALL own the semantic implementations of `reclaim_anchor`, `strong_reclaim_anchor`, and `touch_anchor`.

## Requirement: Prior-window reclaim

Reclaim triggers SHALL inspect only the configured number of bars strictly before the evaluated bar. A probe on the current bar SHALL NOT satisfy the prior-probe condition.

## Requirement: Side symmetry

Long and short trigger inequalities SHALL mirror the copied BBB semantics exactly.

## Requirement: Composition

For each enabled side, the engine SHALL calculate `pre_risk_entry_allowed` as the conjunction of upstream `pre_trigger_allowed` and the trigger mask.

## Requirement: Honest capability stage

The range API SHALL expose trigger evidence and report `triggers_ready`, while keeping `entries` empty and `decisions_ready=false` until risk and final entry composition are implemented.

## Requirement: Golden parity

Acceptance SHALL compare every trigger mask and trace field against the copied BBB implementation for all supported trigger components and both trade sides.
