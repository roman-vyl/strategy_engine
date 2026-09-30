## Context

### Canonical feature layer

The feature layer lives in `strategy_engine/indicators/`:

- `PlannedFeature(output_id, kind, timeframe, source, parameters,
  dependencies)` declares a feature (`contracts.py:17`).
- `RangeIndicatorEvaluator.evaluate_native` is the single source of
  indicator math (`range_evaluator.py`):
  - it resamples each timeframe once per evaluation;
  - it aligns every non-base feature with `align_completed_to_base`
    (`frame_ops.py:56-65`). An HTF value becomes visible on the first
    base bar after that HTF bar closes, so there is no lookahead;
  - it records a `Validity` per column;
  - it memoizes every feature by its `resolve_feature` identity.
- A feature timeframe must be `base` or an integral multiple of base
  (`_validate_feature_timeframe`).
- Warm-up for live history is generated per planned feature
  (`live_calculation/indicator_requirements.py`).

### ema_pullback-specific wiring

`EmaPullbackFeaturePlan` hands columns to components through ad-hoc
maps: `anchor_columns`, `rsi_columns[(tf, period)]`,
`adx_dmi_columns[(tf, period)]`, `setup_columns_by_instance_id`, and
others.

Labels are kind-specific:

- `ema_close_{tf}_{p}`;
- `rsi_close_{tf}_{p}`;
- `atr_close_{tf}_{p}`;
- `{adx|di_plus|di_minus}_close_{tf}_{p}`.

The EMA label is source-blind. This is pinned legacy behavior: EMA
features with different sources but the same timeframe and period share
one label.

### HTF context

HTF regime is a strategy node, not an indicator.

- `build_context_bundle` (`contexts.py:119`) compares a provider's
  fast/anchor/slow EMAs. Those EMAs are computed on the provider
  timeframe and aligned to base.
- It yields `state ∈ {up, down, neutral}` per `context_ref`.
- The node identity is `context.htf_context`.
- `resolve_htf_regime` (`context_consumption.py:18`) maps a state to
  the side-relative `aligned`, `countertrend` or `neutral`.
- `evaluate_setups` receives only the gate records, not the bundle.

### Memoization and parity

Every memoized strategy node has a resolve-twin. The batch pre-pass
counts consumptions, and a successful evaluation must end with
`unforeseen_consumptions == 0` (`batch-computation-reuse`).

### Setups

- `_setup` computes a local mask and then applies the per-`instance_id`
  gate (`setups.py:498-545`).
- `evaluate_setups` ANDs the final masks.
- Semantic setups read their columns from `setup_columns_by_instance_id`,
  which is planned only for top-level `setups`
  (`feature_plan.py:216-229`).

### Cost of reading a column

Today `_float_series` (`setups.py:97`, `direction_blockers.py:103`)
converts a column with a per-element Python loop.

## Goals / Non-Goals

**Goals:**
- Any canonical market feature, at any supported timeframe, can take
  part in a setup condition. This goes through the pipeline "feature →
  predicate → `composite_setup`", without per-indicator setup
  components.
- OR between named paths and N-of-M within a path.
- No second indicator engine, HTF alignment or feature registry.
- Compute cost does not grow. Specs without `composite_setup` are
  bit-identical and compute-count-identical. Composition overhead is
  O(n) vectorized per child and per path.

**Non-Goals:** see `proposal.md`. In particular this change does not
cover NOT, nested composites, an arithmetic DSL, blockers, phase
conditions, trade-state conditions, new indicator kinds, or catalog/UI
exposure.

## Decisions

**D1. Spec shape.**

```yaml
setups:
  - component_id: composite_setup
    instance_id: trend_ready
    # optional, ordinary setup gate on the composite as a whole:
    context_consumption: {context_ref: htf_4h, policy_id: htf_regime_gate, params: {...}}
    params:
      children:
        - child_id: width8
          setup: {component_id: anchor_stack_width_setup, params: {min_current_width_atr: 8, ...}}
        - child_id: htf1h_held
          predicate: {kind: temporal, mode: held_for, bars: 36,
                      of: {kind: state, context_ref: htf_1h, in: [aligned]}}
        - child_id: adx1h_25
          predicate: {kind: compare, left: {feature: {kind: adx, timeframe: 1h, period: 14}},
                      op: ">=", right: {const: 25}}
        - child_id: rsi5m_lt70
          predicate: {kind: compare, left: {feature: {kind: rsi, timeframe: 5m, period: 14}},
                      op: "<", right: {const: 70}, short: {op: ">", right: {const: 30}}}
      paths:
        - path_id: developed
          require: [width8, htf1h_held, adx1h_25, rsi5m_lt70]
        - path_id: alternate
          require: [width10]
          at_least: {k: 2, of: [adx1h_20, adx5m_25, rsi_range]}
```

Rules:

- **Children.** Each child has a `child_id` that is unique within the
  composite. It carries exactly one of `setup` or `predicate`.
- **Setup children.**
  - Only `untouched_anchor_setup`, `ema_bounce_counter_setup` and
    `anchor_stack_width_setup` are allowed. `composite_setup` is not
    allowed, so there is no nesting.
  - They carry neither `instance_id` nor `context_consumption`.
    Gate records are collected only from top-level items
    (`context_consumption.py:150-170`), so a nested gate would be
    silently ignored. It is therefore rejected.
- **Paths.**
  - Each path has a unique `path_id`.
  - It needs at least one of `require` (non-empty) or `at_least`.
  - For `at_least`, `1 <= k <= len(of)`, and `of` has no duplicates.
- **References.**
  - Every referenced `child_id` must exist.
  - Every child must be referenced by at least one path. An
    unreferenced child would be wasted compute, so it is rejected.
- **Semantics.** A path is AND(`require`) AND (count(`of`) >= k). The
  composite local mask is the OR over paths in declared order.

**D2. Predicate model.**

Operands:
- `{feature: {kind, timeframe?, source?, period}}`:
  - `kind ∈ {ema, rsi, atr, adx, di_plus, di_minus}`, the planner's
    existing kinds except `atr_distance`;
  - `timeframe` defaults to `base`;
  - `source` is allowed only for `ema` and defaults to `close`;
  - `period` is a positive integer.
- `{price: open|high|low|close}`: the current base bar, read from
  `market_arrays`.
- `{const: number}`.

Classes:
- `compare {left, op, right}`:
  - `op ∈ {>, >=, <, <=}`;
  - at least one operand is not a constant;
  - this one class covers both "feature vs constant" and "feature vs
    feature".
- `range {operand, min, max}`:
  - bounds are inclusive and `min <= max`;
  - the operand is a feature or a price.
- `state {context_ref, in}`:
  - `context_ref` must be declared in `contexts`;
  - `in` is a non-empty subset of `{aligned, countertrend, neutral}`,
    resolved per side through `resolve_htf_regime`.
- `temporal {mode, bars, of}`:
  - `mode ∈ {held_for, within}` and `bars >= 1`;
  - `of` is a non-temporal predicate. Temporal-of-temporal is
    rejected, because it adds nothing the examples need.

Not supported: NOT, `==` on floats, arithmetic, nested boolean
expressions inside a predicate. Logic lives only in paths.

**D3. Side semantics.**

- A predicate is side-free by default: the same condition for long and
  short.
- A `short` override (`compare` and `range` only) replaces the listed
  fields for the short side:
  - `op`, `left` and `right` for `compare`;
  - `min` and `max` for `range`.
- `side_relative: true` applies to `compare` only, when both operands
  are non-constant. For short it swaps `left` and `right`, so
  `EMA100 > EMA500` on long becomes `EMA500 > EMA100` on short.
  `side_relative` and `short` are mutually exclusive.
- `state` is side-relative by construction.
- A side-free predicate's identity has no side, so it is computed once
  for both sides. This follows the precedent of the width prefix.

**D4. Temporal semantics.**

- `N` counts base bars, the same axis as every existing
  strategy-semantic lookback (`live_calculation_requirements.py`
  header).
- `held_for N` is True at bar i iff the inner predicate is True on each
  of bars i−N+1..i. If fewer than N bars exist (i < N−1), the result is
  False: "held" is not proven.
- `within N` is True at bar i iff the inner predicate is True on at
  least one of bars max(0, i−N+1)..i. The window is shortened at the
  start, matching the `rsi_lookback_extreme_blocker` rolling
  `min_periods=1` precedent.
- `bars: 1` equals the current value.
- Both modes are O(n) regardless of N, through a cumulative sum and a
  shifted difference. There is no per-window loop.

**D5. Non-finite values.**

If any operand of a `compare` or `range` is None or non-finite on a
bar, the result is False on that bar. This is the existing convention:
every component treats not-ready values as not satisfied. It is also
the only warm-up rule the predicate layer needs, because column
validity already reflects indicator warm-up.

**D6. Planning through the canonical plan.**

- `build_feature_plan_from_canonical_spec` walks
  `setups[*].params.children` of `composite_setup` items. For each
  feature operand it calls the existing `add()` with the existing label
  function for the kind. A predicate request therefore shares the
  column, plan entry and identity with any existing consumer of the
  same feature.
- Semantic setup children are planned by the existing per-component
  code, keyed by the internal instance key `"{instance_id}/{child_id}"`
  in `setup_columns_by_instance_id`.
  - A `/` is rejected in user-supplied `instance_id` and `child_id`,
    so the key cannot collide with a top-level `instance_id`.
- For specs without `composite_setup`, the plan is unchanged: same
  features, same order, same `plan_hash`.

**D7. Label collision fails closed.**

A predicate feature operand resolves to a `resolve_feature` identity.
If the plan column under its label carries a different identity, the
request is rejected with `InvalidRequestError`, and the predicate never
reads a different series than it asked for. The case: a predicate asks
for `ema(open, 1h, 100)` while `ema(close, 1h, 100)` already owns
`ema_close_1h_100`, or the reverse.

**D8. Column arrays are converted once.**

- Predicates read a column through a memoized node
  `predicate.column(feature identity)`. The node returns a read-only
  float64 numpy array, with non-finite and None mapped to NaN.
- The column is converted once per evaluation context and shared by
  all predicates, both sides and all batch candidates.
- Existing components keep `_float_series` unchanged.
- Base-bar prices come from `frame.market_arrays`, which is already a
  shared float64 view.

**D9. Context bundle to setups.**

- `evaluate_ema_pullback_frame` passes the `ContextBundle` it already
  builds (`evaluation.py:92`) into `evaluate_setups`.
- The identity path passes `resolve_context_bundle`'s map into
  `resolve_setups`.
- The `state` predicate reads `bundle.outputs[context_ref].state` and
  maps it per side. It computes no EMA and no alignment.

**D10. Identity.**

Identity nodes:

| Node | Params | Upstream | side |
|---|---|---|---|
| `predicate.column` | — | feature identity | none |
| `predicate.compare` | `op`; constants; `price` field names | operand identities | set only for `short` or `side_relative` predicates |
| `predicate.range` | `min`, `max` | operand identity | set only for `short` predicates |
| `predicate.state` | sorted `in` | context node | the side |
| `predicate.temporal` | `mode`, `bars` | inner predicate | inherited |
| `composite.path` | `k` | `require` = frozenset of child identities; `of` = frozenset | — |
| `setup.composite_setup` (local) | — | paths as ordered roles `path_0..path_{m-1}` | — |

- **`composite.path`.** AND and N-of-M are commutative.
- **Composite local.** Order matters for the `winning_path` trace.
- **Semantic children** reuse `resolve_setup_local` unchanged.
- **Labels.** `instance_id`, `child_id` and `path_id` are labels and
  never enter an identity.
- **Identical children** in different paths or candidates share one
  identity, so they are computed once.

**D11. Evidence.**

`SetupMask.trace` for `composite_setup` contains:

- `child:<child_id>`: the child mask. For a setup child this is its
  local mask;
- `path:<path_id>`: the path mask;
- `path:<path_id>:at_least_count` for paths with `at_least`;
- `winning_path`: the first true path in declared order, or None.

The trace holds references to already computed masks and no copies.
Each mask is converted to a tuple once, as `SetupMask` does today.

**D12. Static validation.**

`static_semantics` validates the whole D1–D3 structure without market
data:

- ids, references and bounds;
- kinds, ops, operand shapes and period positivity;
- timeframe string syntax;
- that `context_ref` is declared;
- no `/` in ids, no nested gate, no nested composite.

Timeframe-vs-base divisibility remains a plan-time check, as today.

## Risks / Trade-offs

- **Resolve-twin drift.** Every compute path needs a mirrored resolve
  path. A mismatch shows up as `unforeseen_consumptions > 0` or a
  parity diff, and the memo parity tests
  (`tests/parity/test_all_families_memo.py` style) gate it.
- **Trace volume.** A composite with many children adds one boolean
  tuple per child and path to the response, the same order as the
  existing per-setup masks. This is accepted, because it is the
  evidence the user asked for.
- **`held_for` at the start of history is False.** A strategy that
  starts evaluating mid-history loses the first N−1 bars of that
  condition. This matches the "not proven" semantics, and the live
  window accounts for N.
- **Catalog.** `composite_setup` is not in the composer catalog yet,
  so authoring is raw-spec only until a follow-up change.

## Migration Plan

This change is additive. `SETUP_SUPPORTED` gains `composite_setup`,
and every existing spec path is unchanged. There is no rollback
complexity: removing the component id rejects specs that use it and
changes nothing else.
