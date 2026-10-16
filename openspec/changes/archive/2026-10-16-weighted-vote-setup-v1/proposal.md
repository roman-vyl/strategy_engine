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
  - blocked = any veto, or Σ voter weights ≥ threshold;
  - weights and the threshold are exact decimals (≤ 9 digits), so the decision does not depend on the voter order or on binary
    floating point;
  - a `count` counts the True masks of the predicate layer and has no missing state.
- **Trace:** input values, weights and vetoes, voter weights and vetoes, the score and the block reason. Only the block reason
  depends on the declared order.
- **Identity:** one semantic node (kind, version, normalized config, upstream operand identities, side, market/range). The
  operands keep their own identities and are shared.
- **Unchanged:** operands are reused nodes, and specs without the setup are unchanged.

Not in this change:
- concrete voters, weights or levels;
- how they are chosen;
- catalog and manifest bindings;
- deploy.
