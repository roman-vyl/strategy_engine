## Context

- Atomic operands (`pre-entry-predicates-v1`): `feature`, `episode`, `segment`, `candle`, `leg_mean`, `anchor_follow`,
  `ratio`, `price`, `const`. Each yields one float per bar per side, NaN where missing. New operands added later are usable
  by the vote without any change to it.
- `composite_setup` (`ema-pullback-composite-setup-v1`) already evaluates predicate children once per identity, combines them
  with `require` and `at_least`, and exposes `child:<id>:value` in its trace. `composite_vote` reuses its evaluation helpers
  (operand values, predicate masks, node sharing) and its place in setup composition.

## Goals / Non-Goals

- Goal: a data-driven executor for "veto or weighted sum" over arbitrary operands and predicates.
- Goal: bit-identical results in batch and live for the same spec and bars; no state beyond the evaluated arrays.
- Non-goal: calibration, statistics over outcomes, quantiles, default numbers, component-specific code.

## Decisions

### D1. A separate setup component, not an extension of `composite_setup`

`composite_setup` paths are boolean; adding weights would change its identity and semantics for existing specs. A new
component keeps every existing identity and result unchanged. Both can appear in one spec and are AND-composed.

### D2. Spec shape

```json
{
  "component_id": "composite_vote",
  "instance_id": "<id>",
  "params": {
    "block_at": "<number>",
    "members": [
      {
        "member_id": "m1",
        "inputs": [
          {
            "operand": { "<any operand>": {} },
            "side": "high",
            "levels": [
              { "at": "<number>", "weight": "<number>" },
              { "at": "<number>", "veto": true }
            ]
          }
        ]
      },
      {
        "member_id": "m2",
        "inputs": [
          {
            "group": { "at_least": "<k>", "of": [ { "<predicate>": {} }, { "<predicate>": {} }, { "<predicate>": {} } ] },
            "weight": "<number>"
          }
        ]
      }
    ]
  }
}
```

All values come from the spec; the Engine defines none.

- `block_at`: finite number > 0, or `null` (only vetoes block).
- `member_id`: unique within the vote, no `/`.
- `inputs`: non-empty. An input is exactly one of `operand` or `group`.
- Operand input: `side` is `low` or `high`; `levels` non-empty; each level has a finite `at` and exactly one of `weight`
  (finite, ≥ 0) or `veto: true`; the `at` values of one input are distinct.
- Group input: `at_least` integer `1 ≤ k ≤ len(of)`; `of` a non-empty list of predicates in the predicate grammar; exactly one
  of `weight` or `veto: true`.
- Unknown keys are rejected everywhere. `composite_vote` is not a `composite_setup` child and does not nest.

### D3. Evaluation (per side, per bar, vectorized)

1. Operand input with value `v`:
   - missing (non-finite) `v` → fires nothing;
   - level fired iff `v ≤ at` (`low`) or `v ≥ at` (`high`), inclusive;
   - taken level = the fired level with the most extreme `at` (smallest for `low`, largest for `high`), so the result does not
     depend on the order of the list.
2. Group input: fired iff the number of True predicates ≥ `at_least`; a predicate on a missing value is False, as in the
   predicate layer.
3. Input result: `(weight, veto)` of the taken level or of the fired group; `(0, False)` when nothing fired.
4. Member: `weight = max` over inputs, `veto = any` over inputs.
5. Vote: `sum = Σ member weights`; `blocked = any(member veto) or (block_at is not null and sum ≥ block_at)`.
6. Local setup mask = `not blocked`.

The deepest-level rule means one member gives one vote whatever its ladder length; levels are never summed.

### D4. Trace

- `member:<member_id>:weight` (float per bar), `member:<member_id>:veto` (bool per bar);
- `member:<member_id>/<input_index>:value` for operand inputs (float or null), `member:<member_id>/<input_index>:level` (the
  taken `at` or null), `member:<member_id>/<input_index>:count` for group inputs;
- `vote:sum` (float), `vote:reason` (`veto:<member_id>` of the first vetoing member in declared order, `sum`, or null).

### D5. Identity and sharing

- Each operand input resolves to the existing operand node; each group predicate to the existing predicate node. Nodes shared
  with other setups or members are computed once per evaluation context.
- The vote node (`setup.composite_vote`) carries the canonicalised params (members, inputs, levels, `block_at`) and the
  upstream operand and predicate identities. Labels (`member_id`) do not change operand identities.
- Candidates that differ only in numbers of the vote share every operand and predicate node.

### D6. Live

No new history requirement: the vote reads only operand and predicate arrays that already declare their own windows. The
value on bar `t` depends only on values on `t`.

## Risks / Trade-offs

- Large ladders cost O(bars × levels); typical ladders are tens of levels, negligible next to operand cost.
- Non-monotone weights in a ladder are allowed; the deepest fired level wins by definition, not the largest weight. Tests pin
  this.
