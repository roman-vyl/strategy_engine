## Context

- `composite_setup` already combines predicate children by AND, N-of-M and OR. It reuses the predicate layer's nodes, identities and
  memo, and it traces child values (`ema-pullback-composite-setup-v1`).
- The predicate layer already provides every operand a voter needs: feature, episode, segment, ratio, candle, leg mean and base-bar
  price. These operands are evaluated per side, are missing where undefined, and read no bar after `t`.
- What is missing is a weighted combination with veto steps and a threshold, entirely configured by the spec.

## Decisions

### D1. A setup component, not a predicate class

`weighted_vote_setup` is a setup component like `composite_setup`.
- It produces a `SetupMask`, may declare `context_consumption`, and is AND-composed with the other setups.
- It is not a predicate class and not a child of `composite_setup`. Its result is not a boolean of the predicate layer but a scored
  decision with its own evidence.
- Rejected: a predicate class `vote`. It would need a score-and-reason trace that the predicate layer does not carry, and nesting it
  in composites adds nothing the spec cannot express by declaring both setups.

### D2. Shape

```json
{
  "component_id": "weighted_vote_setup",
  "instance_id": "vote",
  "params": {
    "threshold": 0.75,
    "voters": [
      {
        "voter_id": "alpha",
        "role": "vote",
        "inputs": [
          {
            "input_id": "alpha_in",
            "operand": { "ratio": { "left": {...}, "right": {...} } },
            "direction": "at_most",
            "steps": [ {"level": 0.8, "weight": 0.1}, {"level": 0.4, "weight": 0.3}, {"level": 0.1, "veto": true} ]
          }
        ]
      },
      {
        "voter_id": "beta",
        "role": "vote",
        "inputs": [
          {
            "input_id": "beta_in",
            "count": { "of": [ {"range": {...}}, {"compare": {...}}, {"range": {...}} ] },
            "steps": [ {"level": 2, "weight": 0.3} ]
          }
        ]
      },
      {
        "voter_id": "gamma",
        "role": "veto",
        "inputs": [
          { "input_id": "gamma_in", "operand": {...}, "direction": "at_least", "steps": [ {"level": 0.55, "veto": true} ] }
        ]
      }
    ]
  }
}
```

The numbers above are placeholders for the shape only.

### D3. Validation

- `threshold`: a finite number > 0.
- `voters`: non-empty. `voter_id` values are unique and contain no `/`.
- `role`: `vote` or `veto`. A `veto` voter SHALL have only veto steps.
- `inputs`: non-empty per voter. `input_id` values are unique within the setup and contain no `/`. Each input has exactly one of
  `operand` or `count`.
- `operand`: any operand the predicate layer accepts as the operand of a `range`, validated by the layer.
  `direction` is required: `at_most` or `at_least`.
- `count.of`: a non-empty list of predicates of the layer, validated by the layer. `direction` is not allowed: count steps are
  always `at_least`.
- `steps`: non-empty. Each step has a finite `level` and exactly one of:
  - `weight`: a finite number ≥ 0;
  - `veto: true`.

  Levels are unique within an input. For `count` the levels are integers in `1 … len(of)`.
- Unknown keys are rejected at every level.
- A `short` override is not supported in this change. Inputs are side-aware through their operands. One table serves both sides.

### D4. Step order and the input weight

The input weight is the **largest** weight among crossed steps. The Engine does not require the steps to be sorted or the weights to be
monotone in the level.
- A spec that lists steps from wide to deep with growing weights gets "the weight of the deepest crossed step".
- Any other table is still evaluated deterministically.

Rejected: "the weight of the deepest step". It would make an unsorted or non-monotone table ambiguous.

### D5. Missing values

A missing or non-finite operand value crosses no step: weight 0, no veto. A `count` input counts only True predicates. A predicate on a
missing operand follows its own `empty` policy.

There is no `empty: block` at the voter level: blocking on missing data is expressed by a separate `range` setup, which already has
that policy.

### D6. Score and block

- `score[t]` = Σ voter weights.
- `blocked[t]` = any voter vetoes, or `score[t] ≥ threshold`.
- local mask = `¬blocked`.
- Floating comparison: `score ≥ threshold` uses the plain IEEE comparison, with no epsilon. Research references are produced the same
  way.

### D7. Evidence

The `SetupMask.trace` contains:
- `input:<input_id>:value`: the operand value, or for `count` the count; null where missing;
- `voter:<voter_id>:weight` and `voter:<voter_id>:veto`;
- `score`;
- `blocked_by`: `veto:<voter_id>` for the first vetoing voter in declared order, else `score` when `score ≥ threshold`, else null.

### D8. Identity, memo and cost

- Operands and predicates inside inputs are nodes of the predicate layer, with their existing identities, so they are shared:
  - with other setups;
  - with `composite_setup` children;
  - between candidates.
- The setup's own identity is the canonical JSON of `threshold` and `voters`: voter order, input order and step order all matter, but
  only for evidence.
- Two candidates that differ only in levels, weights, veto flags or `threshold` compute each operand once.
- Cost: O(bars × total steps) vectorized comparisons on top of the operands. No market read and no feature beyond those the inputs
  reference.

### D9. History and feature plan

- Feature references inside inputs are planned as for `composite_setup` children.
- The history requirement is the maximum of the requirements of the inputs' operands and predicates.
- An episode referenced by an input is required to be declared in `raw_spec.ema_stack_episode`, as in the predicate layer.
