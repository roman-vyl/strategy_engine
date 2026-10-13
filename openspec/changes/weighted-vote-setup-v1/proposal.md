## Why

Pre-entry filters exist today as independent blocks: a `range` over an operand, combined by AND, or by AND / N-of-M / OR inside
`composite_setup`. Each block is binary: it either blocks on its own or it does not.

Research needs a second way of combining the same blocks: a **weighted vote**. Several weak signals that are not strong enough to
block alone should block together, and a few extreme ones should still block alone. The rules of the combination (which inputs vote,
their cut levels, weights, veto steps and the block threshold) change often and are chosen outside the Engine. The Engine must
therefore take all of them from the spec and know nothing about where they came from.

## What Changes

- **New setup component `weighted_vote_setup`.** It produces an ordinary `SetupMask`, composed with the other setups like
  `composite_setup`.
- **Voters.** `params.voters` is a list of voters. Each voter:
  - has a `voter_id`;
  - has a `role`: `vote` (adds a weight; may also hold veto steps) or `veto` (veto steps only);
  - has one or more `inputs`.
- **Inputs.** An input is one of:
  - **`operand`**: any operand the predicate layer accepts as the operand of a `range` (feature, episode, segment, ratio, candle,
    leg mean, base-bar price), with a `direction`:
    - `at_most`: a step is crossed when value ≤ level;
    - `at_least`: a step is crossed when value ≥ level.
  - **`count`**: the number of True predicates in a list of predicates of the layer (`of`). Steps are crossed when count ≥ level.
    This gives "k of n" groups as a single input.
- **Steps.** Each input has a list of `steps`. A step is `{level, weight}` or `{level, veto: true}`.
- **Evaluation on bar t, per side:**
  1. An input's weight is the largest weight among its crossed steps, or 0 if none is crossed. The input vetoes if any crossed step
     is a veto step.
  2. A voter's weight is the largest weight among its inputs. The voter vetoes if any of its inputs vetoes.
  3. `score` is the sum of the voter weights.
  4. The bar is **blocked** if any voter vetoes or `score ≥ threshold`.
  5. The local setup mask is True where the bar is not blocked.
  - A missing or non-finite input value crosses no step.
- **Module parameters:** `threshold` (> 0) and `voters`. No default weights, levels or threshold exist in the Engine.
- **Evidence.** The trace gives, per voter, its weight and veto series, and per input the value series. It also gives the `score`
  series and the block reason: `veto:<voter_id>` for the first vetoing voter in declared order, `score`, or null.
- **Reuse.** Inputs reuse the operand and predicate nodes, identities and memo of the predicate layer. Candidates that differ only in
  levels, weights, veto flags or the threshold share every operand.
- **No regression.** A spec without `weighted_vote_setup` keeps its node set, identities, masks, feature plan and history plan.

Not in this change:
- any concrete set of voters, weights or levels;
- how weights are chosen;
- catalog and Research manifest bindings;
- research surfaces;
- deploy.
