## Why

Research wants to describe an entry setup as alternative combinations of
market conditions: "wide stack AND 1h trend aligned AND ADX(1h) >= 25
AND ADX(5m) >= 20 AND RSI(5m) < 70, OR wider stack AND at least 2 of
[ADX(1h) >= 20, ADX(5m) >= 25, RSI(5m) in 40..65]". Today this is not
expressible:

- `evaluate_setups` only ANDs the declared setups (`setups.py:554-610`);
  there is no OR between alternative paths and no N-of-M.
- Market conditions such as "ADX(tf) >= X" or "RSI(tf) < X" exist only
  inside role-specific packaging (`trend_strength_episode_blocker`,
  `rsi_lookback_extreme_blocker`, the managed `adx_di_threshold`
  phase condition). Using them in a setup would mean either borrowing a
  blocker's `allowed` output or adding one `*_threshold_setup` per
  indicator. Both carry legacy role taxonomy into a new capability, and
  the second grows a component per indicator forever.

The canonical feature layer below the roles already provides everything
a condition needs. `strategy_engine/indicators/` provides:

- declaration (`PlannedFeature`);
- one source of indicator math (`RangeIndicatorEvaluator.evaluate_native`);
- completed-bar HTF alignment for every kind (`align_completed_to_base`);
- validity and warm-up;
- semantic identity (`resolve_feature`);
- memoization (`EvaluationContext`).

What is missing is a thin boolean layer over those features and one
setup that composes its results. Audit:
`predicate-layer-audit.md` (project files,
`state-transition-architecture/`).

## What Changes

**New internal layer `PreEntryPredicate`.** It is not a strategy role
or component.
- A predicate declares canonical feature and context requirements.
- It reads only the columns the canonical plan produced, plus the
  base-bar price and the existing HTF context bundle.
- It returns a boolean series on the base timeline.
- Supported classes:
  - feature vs constant;
  - feature vs feature;
  - range;
  - context state;
  - temporal `held_for`;
  - temporal `within`.
- HTF is first-class. Any feature timeframe that is `base` or an
  integral multiple of base is allowed, through the existing alignment.

**New setup component `composite_setup`.**
- From the outside it is an ordinary setup. It returns an ordinary
  `SetupMask`, may carry its own `context_consumption`, and is ANDed
  with the other setups exactly as today.
- Inside, it holds named children. Each child is either a predicate or
  one existing semantic setup (`untouched_anchor_setup`,
  `ema_bounce_counter_setup`, `anchor_stack_width_setup`).
- Children are combined by named paths:
  - `require` is an AND;
  - `at_least {k, of}` is an N-of-M;
  - the composite is the OR over its paths.

**Canonical feature-kind contract.** This is a minimal extension of
the indicator layer, in the new module `indicators/feature_kinds.py`.
- It holds one entry per kind: schema, default source, whether the kind
  is requestable, validator, label and identity parameters.
- `IndicatorRegistry`, the planner's allowed kinds and labels, and the
  `resolve_feature` identity all derive from it, so their outputs for
  existing kinds stay unchanged.
- Predicates resolve feature operands only through this contract. They
  own no knowledge of kinds, sources or parameters.
- Extension invariant: a new canonical kind (math, contract entry and
  warm-up policy) becomes a predicate operand without a new `*_setup`,
  without a change to predicates or to `composite_setup`, and without
  a second registry.

**Side semantics.** Predicates are side-free by default, and the short
side differs only through an explicit `short` override. There is no
automatic inversion. `state aligned/countertrend` remains side-relative
through the existing `resolve_htf_regime`.

**Plumbing:**
- `feature_plan` plans the predicate features through the existing
  `add()`, with labels from the canonical contract. A request whose identity differs
  from the feature already stored under its label fails closed.
- `evaluate_setups` and `resolve_setups` receive the already-built
  context bundle and its identities.
- The live history planner recurses into composite children and
  temporal windows.

**Compute cost must not grow:**
- Specs without `composite_setup` evaluate bit-identically, with an
  identical plan hash, identical node identities and identical compute
  counts.
- Composition overhead is limited to vectorized O(n) mask operations.
- Each feature column is converted to a float64 array once per
  evaluation context, not once per predicate.

**BREAKING:** none.

## Non-Goals

- `composite_blocker` and `composite_phase_condition`.
- Any change to blockers, direction, triggers, exits, the managed state
  machine or `HistoricalManagedProjection`.
- Managed or trade-state conditions (MFE, `bars_in_trade`).
- NOT.
- Nested composites.
- An arithmetic DSL or expression AST.
- A new indicator engine, a new HTF engine, or new indicator kinds.
  Bollinger and price-on-HTF are later indicator-layer changes.
- Composer catalog and UI exposure of `composite_setup`. In this change
  it is authored as raw spec only.

## Capabilities

### New Capabilities
- `pre-entry-predicates-v1`: the internal predicate layer. Covers the
  predicate classes, operand kinds, side semantics, temporal semantics,
  non-finite handling, and its dependency on canonical features and
  context only.
- `ema-pullback-composite-setup-v1`: the `composite_setup` spec shape,
  its validation, path semantics, evidence, and the child adapters for
  predicates and semantic setups.

### Modified Capabilities
- `ema-pullback-setups-v1`: adds `composite_setup` as a supported
  setup that participates in setup composition and context
  consumption like any other setup.
- `ema-pullback-feature-plan-v1`: adds deterministic planning of
  predicate feature references through the canonical plan, including
  fail-closed label collisions.
- `live-calculation-window-planning`: adds history policies for
  composite children and temporal predicate windows.
- `batch-computation-reuse`: adds identity twins for predicates, paths
  and composites, and a no-regression requirement on compute counts
  and wall-clock for specs that do not use `composite_setup`.

## Impact

- `strategy_engine/indicators/feature_kinds.py` (new): the canonical
  feature-kind contract. `service/registries.py` (`IndicatorRegistry`)
  and `range_evaluator.resolve_feature` delegate to it, with unchanged
  outputs for existing kinds.
- `strategy_engine/strategies/ema_pullback/predicates.py` (new):
  - predicate parsing and validation;
  - compute and resolve twins;
  - the memoized column-array node.
- `setups.py`:
  - `composite_setup` branch in `_setup` and `resolve_setup_local`;
  - path evaluation and trace;
  - semantic-child adapter;
  - context bundle parameter.
- `feature_plan.py`: recursion into composite children and predicate
  feature references.
- `evaluation.py`: pass the context bundle and its identities to
  setups.
- `raw_spec_identity.py` and `static_semantics.py`: the
  `SETUP_SUPPORTED` entry and composite validation.
- `live_calculation_requirements.py`: recursion into composite
  children.
- No HTTP contract change beyond the setup trace of `composite_setup`
  items. No change to Research Service.
