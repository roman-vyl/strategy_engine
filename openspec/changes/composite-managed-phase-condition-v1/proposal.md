## Why

Research wants to express a managed phase transition as a combination
of market conditions and trade-state conditions. The first real case:

```
(ADX 5m > 35  OR  (ADX 1h > 25 AND DI 1h directional))  AND  MFE >= X  →  proven
```

Today this is not expressible.

- A `phase_rule` carries exactly one `condition` out of four atoms:
  `bars_in_trade`, `mfe_pct`, `mfe_atr`, `adx_di_threshold`
  (`managed.py:308-359`).
- OR works through several rules with the same `to_phase`, but AND
  inside a rule and N-of-M are impossible.
- The market half of the case (ADX/DI on any timeframe, HTF state,
  compare/range/temporal) already exists as the `PreEntryPredicate`
  layer from `composite-setup-pre-entry-predicates-v1`. Managed cannot
  use it. The only alternative would be a second market-condition
  language inside managed, and this change rules that out.

The explore (`composite-phase-condition-explore.md`, project files,
`state-transition-architecture/`) checked the one risk that matters: a
composite condition must not force the candidate-wide
`HistoricalManagedProjection` back into per-trade recomputation of
market logic.
- Every child in scope is separable. It is either purely market (a
  predicate, `adx_di_threshold`) or "trade metric ≥ per-bar threshold"
  (`mfe_atr`, `mfe_pct`, `bars_in_trade`).
- So a path decomposes into one candidate-wide market mask plus
  per-trade thresholds. An N-of-M with any trade child (trade-only
  or mixed) keeps its terms separate. Only an all-market N-of-M
  folds into the mask.
- A prototype compared the real `managed.py` replay loop against a
  reference projection consumer: 400 trades, 1182 transitions, three
  paths including a mixed N-of-M, 0 mismatches including path
  attribution. Two deliberate consumer faults each produced 400/400
  mismatches.

## What Changes

**New managed phase condition `composite_phase_condition`.**
- From the outside it is an ordinary `phase_rule.condition`. The state
  machine, phases, rule order, the same-bar cascade and
  stop/take/runtime actions are unchanged.
- Inside, it holds named children. Each child is either:
  - a `predicate`: literally a `PreEntryPredicate` from
    `pre-entry-predicates-v1`, parsed and evaluated by the existing
    predicate layer; or
  - a `condition`: one of the four existing managed atoms, in its
    current `{component_id, params}` form, evaluated by the existing
    atom formulas.
- Children are combined by named paths: `require` is an AND,
  `at_least {k, of}` is an N-of-M (market, trade or mixed terms), and
  the condition is the OR over its paths. The first satisfied path in
  declared order wins and is attributed.

**One market evaluation, shared by every execution path.** A single
function folds the market part of each path into one boolean array per
side. Market children come from `evaluate_predicate`, and
`adx_di_threshold` from its existing series formula. This function is
used by:
- the single-trade replay core (`/managed-replay` and live
  open-trade), which reads the folded arrays at the bar index and
  checks trade atoms with the existing `_phase_met`;
- the historical projection, which emits the folded arrays.

There is no managed predicate type and no second indicator dispatch.

**Projection contract, additive.** `ManagedPhaseTransitionRule` gains a
third, mutually exclusive variant, `paths`:

```
ManagedPhaseTransitionRule =
    condition_id                       (existing)
  XOR distance_id + trade_metric       (existing)
  XOR paths                            (new, composite only)
```

- Each `ManagedTransitionPath` carries:
  - `path_id`;
  - an optional folded market `condition_id`;
  - trade `thresholds` (`distance_id` + `trade_metric`, ANDed);
  - an optional `at_least` over its terms, present whenever the
    N-of-M contains a trade child.
- Atomic rules keep their current form byte for byte. There is no
  migration to one-element paths.
- No projection consumer exists yet in Research, so the contract is
  extended in one repository.

**Plumbing:**
- feature planning of predicate children through the existing
  canonical plan and collision check;
- the `ContextBundle` reaches the managed evaluators for `state`
  predicates, and `/managed-replay` builds it only when needed;
- live history planning recurses into children;
- the memo pre-pass predicts predicate-child consumptions of the
  projection, and composite paths are not memo nodes;
- static validation;
- path attribution in `phase_changed` events and projection paths.

**Compute cost must not grow:**
- For specs without `composite_phase_condition`, the following are
  identical to before this change:
  - plan hash;
  - node identities and compute counts;
  - `/range-batch` output, including the projection;
  - `/managed-replay` and live open-trade outputs.
- Predicate children are memoized and shared across candidates and with
  `composite_setup`. Path folding is O(n) vectorized per candidate. Per
  trade, the projection path costs only scalar threshold checks.

**BREAKING:** none.

## Non-Goals

- New atoms: `mfe_r`, `phase_at_least`, `bars_in_phase`, giveback,
  trailing stop.
- NOT, nested composites, setup or blocker children.
- A managed predicate type or any new indicator or feature dispatch.
- Changes to the state machine, phases, `activate_when`,
  stop/take/runtime actions, or the historical/live evaluation offset
  (0 vs 1).
- Research Service: consuming the projection, or any Research change.
  Research keeps calling `/managed-replay`, which supports the
  composite.
- Composer catalog and UI exposure. The composite is authored as raw
  spec only.

## Capabilities

### New Capabilities
- `ema-pullback-composite-phase-condition-v1`: the
  `composite_phase_condition` spec shape, its validation, children,
  path semantics, side and readiness semantics, attribution, and
  equivalence across the single-trade replay and the projection.

### Modified Capabilities
- `pre-entry-predicates-v1`: `composite_phase_condition` becomes the
  second allowed consumer of predicates. Predicates are still never a
  top-level strategy item.
- `ema-pullback-managed-policy-v1`: single-trade replay (the
  `/managed-replay` route and the live start-after-entry projection)
  evaluates `composite_phase_condition` and attributes the winning
  path.
- `historical-managed-projection-v1`: the `paths` variant of phase
  transitions, and parity of path attribution.
- `ema-pullback-feature-plan-v1`: planning of predicate features
  referenced by composite phase conditions.
- `live-calculation-window-planning`: history policy for composite
  phase condition children.
- `batch-computation-reuse`: memoized predicate children in the
  projection, and no regression for existing managed specs.

## Impact

- `composite_spec.py`: the shared children/paths parser, with a
  role-specific child parser (setup vs phase). The `composite_setup`
  behavior is unchanged.
- New module `managed_composite.py`: parse helpers, the shared path
  folding and the runtime path check.
- `managed.py`:
  - composite branch of `_phase_met`;
  - folded arrays built once per replay call;
  - optional `bundle` parameter.
- `historical_managed_projection.py`:
  - composite emits a `paths` rule;
  - the atom → term code is extracted so single rules and children
    share it;
  - optional `bundle` and memo `context`.
- `strategies/contracts.py` and `adapters/http/strategy_serialization.py`:
  `ManagedTransitionPath`, `ManagedTransitionThreshold`,
  `ManagedTransitionAtLeast`, and the optional `paths` field.
- `feature_plan.py`, `live_calculation_requirements.py`,
  `static_semantics.py`: composite branches.
- `evaluation.py` and `evaluator.py`: the managed stage in the memo
  pre-pass; the context bundle and memo context passed to the
  projection builder.
- `application/evaluate_managed_replay.py` and
  `live_projections/open_trade.py`: the bundle for `state` predicates.
- No HTTP request-shape change. The response adds `paths` on composite
  rules only. No Research Service change.
