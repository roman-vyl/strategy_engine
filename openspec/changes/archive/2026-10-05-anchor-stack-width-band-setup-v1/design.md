## Context

The EMA-pullback pipeline is: feature plan → indicator columns on the base frame → components (direction, blockers, setups,
trigger, exits) → managed state. Setups are evaluated per side in `setups.py`: each produces a local mask and a trace, an optional
context gate filters the local mask, and the final masks of all setups are AND-composed into `pre_trigger_allowed`.
`composite_setup` evaluates semantic setup children through the same `_semantic_setup_compute` and identifies them through the
same `resolve_setup_local`.

`anchor_stack_width_setup` computes, in a side-free prefix node `setup.anchor_stack_width.prefix`, the per-bar
`width_atr = |fast - slow| / atr` and its trailing maximum over `width_lookback_bars`; its local node applies
`min_current_width_atr` to the first and `min_recent_width_atr` to the second, and also requires the anchor column to be finite.
Its defaults (`2.0`, `4.0`, `80`) make it a two-condition setup in every configuration.

## Goals / Non-Goals

Goals:

- A stateless setup that admits a bar when the current stack width lies in an inclusive band.
- No new indicator, no new wire field, no cost for specs that do not use it.

Non-goals:

- Any change to `anchor_stack_width_setup`.
- A trailing window, a hold window or any other history inside the new component. Temporal conditions stay the business of
  existing mechanisms.
- A predicate class or a new feature kind for the width.

## Decisions

### D1. A new semantic setup, not a mode of the existing one

A mode flag on `anchor_stack_width_setup` would change its parameter surface and, through normalized parameters, its identity.
A separate component keeps the existing one byte-for-byte unchanged, and its name states the difference: a band over the current
bar, with no history.

### D2. Parameters and validation

| Param | Required | Type | Rule | Default |
|---|---|---|---|---|
| `atr_timeframe` | no | string | a supported timeframe | `base` |
| `atr_period` | no | integer | `> 0` | `14` |
| `min_width_atr` | yes | number | finite, `> 0` | none |
| `max_width_atr` | no | number | finite, `>= min_width_atr` | absent = no upper bound |

- Booleans are not numbers. `null` for `max_width_atr` is rejected; the only spelling of "no upper bound" is an absent key, so
  one meaning has one form.
- Unknown keys are rejected.
- Validation is market-data-free and runs in the canonical static validator, so an invalid band is rejected before evaluation,
  in a top-level setup and in a `composite_setup` child alike. The same parsing function is used by compute and resolve, so
  defaults are applied in one place.

### D3. Semantics

On each base bar `i`:

```
width_atr[i] = |fast[i] - slow[i]| / atr[i]
allowed[i]   = ready[i] and min_width_atr <= width_atr[i] and (max_width_atr absent or width_atr[i] <= max_width_atr)
ready[i]     = fast[i], slow[i], atr[i] finite and atr[i] > 0
```

- `fast` and `slow` are the anchor-stack EMA columns; `atr` is the ATR column of (`atr_timeframe`, `atr_period`). A higher-timeframe
  ATR is the existing aligned column (last completed bar, no look-ahead).
- Both bounds are inclusive. With `min_width_atr == max_width_atr` the band is a single value; it is valid.
- Only `fast`, `slow` and `atr` are read. The anchor column is not an input of the width and is not read.
- The width formula is the one `anchor_stack_width_setup` uses, so the two components agree on `width_atr` for the same columns.

### D4. Side

Side-free: the width is an absolute value and neither bound depends on the side. The same mask serves both sides.

### D5. Trace

Per bar: `blocked_reason` (`indicator_not_ready`, `width_below_min`, `width_above_max`, or empty), `width_atr`, `min_width_atr`,
`max_width_atr` (`null` when absent), `fast_ema`, `slow_ema`, `atr_value`.

### D6. Placement in the pipeline

- Top-level setup: evaluated by the same dispatch as the other semantic setups; context consumption order and AND composition are
  unchanged (local mask first, gate second).
- `composite_setup` child: allowed as a `setup` child with the existing child rules (no `instance_id`, no `context_consumption`);
  it contributes its local mask and its local identity, exactly as the other semantic setup children.
- Not a phase atom of `composite_phase_condition`; the managed state machine and the historical projection are not touched.

### D7. Feature plan

`plan_setup_columns` maps the instance to `{fast, slow, atr}`. `fast` and `slow` are the anchor-stack columns that every spec
already plans; `atr` comes from `add_atr(atr_timeframe, atr_period)`, which deduplicates by `output_id`. A spec that uses the band
with the same ATR as another consumer plans one ATR feature. No new indicator kind is introduced. For a composite child the key is
the existing `"{instance_id}/{child_id}"`.

### D8. Identity and memoization

Two node families, both side-free:

- `setup.anchor_stack_width_band.width`: params `{}`, upstream `{fast, slow, atr}` feature nodes; value is the `width_atr` series.
- `setup.anchor_stack_width_band`: params `{min_width_atr}` plus `max_width_atr` only when present, normalized to `float`;
  upstream `{width}`.

Candidates that differ only in the bounds share the `width` node and compute it once per batch. The width node is not shared with
`setup.anchor_stack_width.prefix`: that node also carries the trailing maximum and its identity must stay unchanged; the two
compute the same O(n) vectorized division only when one spec uses both components. Labels never enter identity.

### D9. Live history

The live history planner records an explicit zero-additional-history entry for the component. The EMA and ATR warm-up is already
counted from the plan by the per-feature policy, and the component reads no earlier bar.

### D10. Cost

The width and the band test are vectorized numpy operations over the frame, O(n). Specs without the component do not reach any new
code path: plan, `plan_hash`, node identities, compute counts and outputs are unchanged.

## Risks / Trade-offs

- Inclusive upper bound vs half-open intervals. A partition of the width axis into adjacent bands `[a, b]`, `[b, c]` admits a bar
  with width exactly `b` in both. Width values are continuous, so exact equality is rare, but a caller comparing against half-open
  bands must use the same convention on both sides.
- Two width computations when a spec uses both width components. Accepted to keep the existing identity unchanged (D8).

## Alternatives not taken

- An optional `max_current_width_atr` on `anchor_stack_width_setup`: changes the existing component and its identity (D1).
- A `range` predicate over a width feature: needs a new derived feature kind (ratio of two EMAs and an ATR) and a second width
  computation path; the setup layer already owns the stack and its columns.
- Reusing `setup.anchor_stack_width.prefix` as the width node: it computes the trailing maximum the new component does not need,
  and its identity carries `width_lookback_bars`.
