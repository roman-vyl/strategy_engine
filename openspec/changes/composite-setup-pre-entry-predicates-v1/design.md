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
          predicate: {kind: compare, left: {feature: {kind: adx, timeframe: 1h, params: {period: 14}}},
                      op: ">=", right: {const: 25}}
        - child_id: rsi5m_lt70
          predicate: {kind: compare, left: {feature: {kind: rsi, timeframe: 5m, params: {period: 14}}},
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
- `{feature: {kind, timeframe?, source?, params}}`:
  - the predicate layer treats this as an opaque canonical feature
    request;
  - it resolves the request through the canonical feature-kind contract
    (D13): which kinds exist, which are requestable as an operand,
    which `source` values and `params` are valid, the default `source`,
    the column label and the identity;
  - `timeframe` defaults to `base`; its validity is the evaluator's
    existing rule.
  - The v1 requestable set is exactly what the contract marks
    requestable today: `ema`, `rsi`, `atr`, `adx`, `di_plus`,
    `di_minus`. `atr_distance` is not requestable because it declares a
    feature dependency. The predicate layer does not restate this list.
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
- If the short side must differ, the only mechanism is an explicit
  `short` override (`compare` and `range` only). It replaces the listed
  fields for the short side:
  - `op`, `left` and `right` for `compare`;
  - `min` and `max` for `range`.

  Example: `EMA100 > EMA500` for long and `EMA100 < EMA500` for short
  is written as `short: {op: "<"}`.
- There is no automatic inversion of any predicate. `side_relative`
  or any similar flag is rejected.
- `state` is side-relative because it reuses the existing
  `resolve_htf_regime` semantics (`aligned`/`countertrend`). It is not
  a new inversion mechanism.
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
  feature operand it asks the canonical contract (D13) for a normalized
  `PlannedFeature`, then passes it to the existing `add()`. A predicate request therefore shares the
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
| `predicate.compare` | `op`; constants; `price` field names | operand identities | set only for predicates with a `short` override |
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

**D13. Canonical feature-kind contract (minimal extension of the indicator layer).**

*Problem.* Today, knowledge about each feature kind is spread over
four places, each with its own `if/elif` per kind:

- `_ALLOWED_KINDS` and the label functions (`_ema_id`, `_rsi_id`,
  `_atr_id`, `_adx_id`) and the source default in `feature_plan.py`;
- the validators and schemas in `service/registries.py`
  (`IndicatorRegistry`);
- the identity params (only `period`) in `resolve_feature`.

A predicate layer built on the current API would need a fifth copy
(kinds, sources, params). That is exactly the second registry the
owner forbids.

*Extension.* A new module `strategy_engine/indicators/feature_kinds.py`
becomes the single canonical source of per-kind knowledge. It lives in
the indicator layer, next to the math.

```
FeatureKindContract:
  kind: str
  schema: the existing public schema dict (moved from service/registries.py)
  default_source: str | None        # applied when a request omits source
  requestable: bool                 # False when the kind needs feature dependencies (atr_distance)
  validate(PlannedFeature) -> None  # the existing per-kind validator
  label(timeframe, source, params) -> str   # reproduces today's labels exactly
  identity_params(PlannedFeature) -> Mapping  # every semantic parameter; for existing kinds == {period}

feature_kind(kind) -> FeatureKindContract           # unknown kind fails closed
feature_kinds() -> tuple[FeatureKindContract, ...]
plan_feature_request(kind, timeframe, source?, params) -> PlannedFeature
    # applies default_source, validates, builds the label; the only entry point predicates use
```

*Rewiring. The observable behaviour of existing specs does not change:*

- `IndicatorRegistry` (`list_definitions`, `get_schema`,
  `validate_feature`) delegates to `feature_kinds()`. Its responses
  stay identical.
- `feature_plan._ALLOWED_KINDS` is derived from `feature_kinds()`. The
  label functions delegate to `label`, and the resulting labels stay
  identical.
- `resolve_feature` builds identity params as
  `{timeframe, source, **identity_params}`. For every existing kind
  this equals today's `{timeframe, source, period}`, so identities stay
  identical. `atr_distance` keeps its explicit dependency identity.
- Unchanged: the math dispatch in `_compute_feature`, `align_completed_to_base`
  and the warm-up policies in `indicator_requirements.py`. They are
  already the canonical math, alignment and warm-up, which the
  predicate layer only consumes. The warm-up planner already fails
  closed on unknown kinds.

*Predicate layer:*

- `predicates.py` calls only `plan_feature_request` and
  `resolve_feature`.
- It contains no kind names, no source rules and no parameter rules.
- An architecture test enforces this: `predicates.py` has no
  indicator-kind string literals and imports nothing from
  `indicators/implementations`.

*Extension invariant.* Adding a new canonical feature kind (for
example Bollinger `bb_upper`, `bb_middle`, `bb_lower` with
`{period, std}`) requires exactly these steps, all in the indicator
layer:

1. The math branch in `evaluate_native`.
2. A `FeatureKindContract` entry.
3. A warm-up policy.

After that the kind is automatically a valid predicate operand at any
supported timeframe, with canonical HTF alignment. It needs:

- no `*_setup` component;
- no change to `predicates.py` or to the `composite_setup` evaluator;
- no second registry, math or alignment layer.

`std` enters the identity through `identity_params`, so BB(20, 2) and
BB(20, 2.5) never share a memo entry.

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
