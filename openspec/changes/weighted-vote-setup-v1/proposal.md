## Why

Today a pre-entry filter can only block on its own, alone or combined by AND / N-of-M / OR in `composite_setup`. We also need a
**weighted vote**: weak signals block only together, strong ones still block alone. The combination (which inputs vote, their
levels, weights, vetoes, the threshold) is chosen outside the Engine and changes often. So the Engine takes all of it from the spec
and knows nothing about how it was chosen.

## What Changes

- New setup component **`weighted_vote_setup`** with `threshold` and `voters`. No defaults.
- A **voter** has a role, `vote` or `veto`, and inputs.
  - An **input** is an existing predicate-layer operand with a direction, or a `count` of True predicates.
  - Each input has a ladder of **steps** `{level, weight}` or `{level, veto: true}`.
- **On each bar, per side:**
  - voter weight = largest weight among the crossed steps of its inputs;
  - blocked = any veto, or Σ voter weights ≥ threshold.
- **Trace:** input values, voter weights and vetoes, the score and the block reason.
- **Unchanged:** operands are reused nodes, and specs without the setup are unchanged.

Not in this change:
- concrete voters, weights or levels;
- how they are chosen;
- catalog and manifest bindings;
- deploy.
