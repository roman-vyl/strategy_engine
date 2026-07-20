# Proposal: EMA Pullback Setups v1

## Why

The independent Strategy Engine already owns feature planning, indicator calculation, contexts, context consumption, direction, and blockers. The next legacy seam is the setup stack that converts `pre_setup_allowed` into a side-specific `pre_trigger_allowed` mask.

## What changes

- Port `untouched_anchor_setup` semantics.
- Port stateful `ema_bounce_counter_setup` semantics.
- Port `anchor_stack_width_setup` semantics.
- Apply setup context gates after local setup semantics.
- Compose multiple setup rules through logical AND in declared order.
- Expose setup evidence in the existing coarse-grained strategy range response.
- Advance the strategy evaluation stage to `setups_ready`.

## Out of scope

- trigger components;
- risk components;
- final entry signals;
- exit policy and managed exits;
- incremental/bar-to-bar checkpoints;
- BBB cutover.
