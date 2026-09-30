## Context

### Managed state machine today

- Phases `initial_risk → proven → protected → runner → exhaustion`,
  monotone rank (`managed.py:16`).
- `_evaluate_managed_replay_core` (`managed.py:416`) iterates bars
  from the entry. On each bar it walks `phase_rules` in spec order:
  - it skips a rule whose target rank is ≤ the current rank;
  - it evaluates `_phase_met`;
  - on success it moves the phase at once, so later rules of the same
    bar see the new phase (the same-bar cascade) (`managed.py:460-497`).
- `_phase_met` (`managed.py:308-359`) is an if-chain over four atoms:

| Atom | Reads | Not ready |
|---|---|---|
| `bars_in_trade` | trade state | never |
| `mfe_pct` | trade state | never |
| `mfe_atr` | trade state, ATR column | ATR `None` or ≤ 0 → False |
| `adx_di_threshold` | ADX/DI± columns, trade side | any `None` → False |

- Two entry points share the core:
  - `evaluate_managed_replay` (the `/managed-replay` route, offset 0,
    no evaluation or context bundle, `application/evaluate_managed_replay.py`);
  - `evaluate_start_after_entry_managed_projection` (live open-trade,
    offset 1). Its caller `live_projections/open_trade.py:151-164`
    runs `evaluate_ema_pullback_frame` first, so the context bundle
    exists there.

### Historical projection today

- `build_historical_managed_projection(raw_spec, frame, plan)`
  (`historical_managed_projection.py:62`) is called once per candidate
  from `evaluate_execution_projection` (`evaluator.py:188-190`),
  inside the batch root scope.
- A phase atom becomes one `ManagedPhaseTransitionRule` with exactly
  one of:
  - `condition_id`: a long/short bool series;
  - `distance_id` + `trade_metric`: a per-bar threshold compared with
    `>=` against a consumer-owned trade quantity.
- Contract docstring: "exactly one ... never both, never neither"
  (`strategies/contracts.py:237-250`).
- Parity with the single-trade replay is tested through a reference
  consumer (`tests/test_ema_pullback_historical_managed_projection.py:43`).
- Research Service on main has no projection consumer yet. It calls
  `/managed-replay` once per trade and passes `component_id` and
  `metadata` of events through opaquely
  (`research_service/execution/managed_policy_events.py`).

### Predicate layer (from `composite-setup-pre-entry-predicates-v1`)

- `parse_predicate`, `evaluate_predicate(predicate, frame, side,
  context, identity, bundle)` and the identity twin
  `resolve_predicate` live in `predicates.py`.
- A predicate reads plan columns (a memoized float64 array per feature
  identity), base-bar prices, and HTF state from a `ContextBundle`.
- Side-free unless it carries a `short` override. Non-finite values
  are False. Temporal windows are market-time.
- Memoized strategy nodes need identity twins. The batch pre-pass must
  predict every consumption (`unforeseen_consumptions == 0`).

### Composite setup

`composite_spec.py` parses `children` + `paths`. Only `_child` is
setup-specific: it accepts `setup` or `predicate`.

## Goals / Non-Goals

**Goals:**
- Express `(market AND trade) OR (market AND market AND trade)`, and
  N-of-M over mixed terms, as one `phase_rule.condition`.
- Market children are existing predicates. Trade children are existing
  atoms. There is no new condition language and no new indicator
  dispatch.
- One market evaluation shared by the single-trade replay and the
  projection, so the paths cannot diverge.
- The projection stays candidate-wide: market logic is never evaluated
  per trade.
- Zero change for specs without the composite. No CPU growth.

**Non-Goals:** see `proposal.md`.

## Decisions

**D1. Spec shape.**

```yaml
trade_management:
  exit_management:
    mode: managed
    phase_rules:
      - rule_id: to-proven
        to_phase: proven
        condition:
          component_id: composite_phase_condition
          params:
            children:
              - child_id: adx5
                predicate: {kind: compare, op: ">", right: {const: 35},
                            left: {feature: {kind: adx, timeframe: base, params: {period: 14}}}}
              - child_id: adx1h
                predicate: {kind: compare, op: ">", right: {const: 25},
                            left: {feature: {kind: adx, timeframe: 1h, params: {period: 14}}}}
              - child_id: di1h
                predicate: {kind: compare, op: ">",
                            left:  {feature: {kind: di_plus,  timeframe: 1h, params: {period: 14}}},
                            right: {feature: {kind: di_minus, timeframe: 1h, params: {period: 14}}},
                            short: {left:  {feature: {kind: di_minus, timeframe: 1h, params: {period: 14}}},
                                    right: {feature: {kind: di_plus,  timeframe: 1h, params: {period: 14}}}}}
              - child_id: mfe
                condition: {component_id: mfe_atr,
                            params: {threshold: 3.0, atr: {timeframe: base, period: 14}}}
            paths:
              - {path_id: fast, require: [adx5, mfe]}
              - {path_id: htf,  require: [adx1h, di1h, mfe]}
```

- `children` (non-empty). Each has a `child_id` and exactly one of:
  - `predicate`: any predicate accepted by `parse_predicate`
    (compare, range, state, temporal), unchanged;
  - `condition`: `{component_id, params}` with `component_id` ∈
    {`bars_in_trade`, `mfe_pct`, `mfe_atr`, `adx_di_threshold`}. The
    params are exactly the atom's current params.
- `paths` (non-empty). Each has a `path_id`, an optional `require`
  (AND), and an optional `at_least {k, of}` (count ≥ k). At least one
  of the two is present.
- The condition is true on a bar iff some path is true.
- The structural rules of `composite_setup` apply unchanged:
  - unique ids;
  - no `/` in ids;
  - no unknown or repeated references;
  - `1 ≤ k ≤ len(of)`;
  - every child referenced by some path.
- Rejected:
  - nested `composite_phase_condition`;
  - `setup` or blocker children;
  - any other atom id;
  - a predicate as a top-level `phase_rule.condition`;
  - NOT.

**D2. Shared structure parser, role-specific child parser.**
`composite_spec.py` keeps one parser for children, paths and
references. It takes the child parser as a parameter:
- `composite_setup` passes its current `_child` (setup | predicate).
  Its behavior and error messages are unchanged.
- `composite_phase_condition` passes a phase child parser
  (predicate | condition).
- `CompositeChild` gains an optional `condition` field. Setup code never
  sees it set.
- Error paths name the rule (`phase_rules[i].condition...`) because a
  phase condition has no `instance_id`.

**D3. Child kinds are separable, and this is the invariant that makes
the projection possible.**

| Child | Kind | Per-bar value |
|---|---|---|
| `predicate` (any class) | market | `mask_side[i]` from `evaluate_predicate` |
| `adx_di_threshold` | market | `series_side[i]`: the existing formula, `None` → False, alignment by side |
| `mfe_atr` | trade | `mfe_distance ≥ threshold·ATR[i]` (NaN distance → False) |
| `mfe_pct` | trade | `mfe_pct ≥ threshold` |
| `bars_in_trade` | trade | `bars_in_trade ≥ threshold` |

- A market term depends only on the bar and the trade side. A trade
  term is "consumer-owned trade quantity ≥ per-bar threshold", which is
  exactly the existing `distance_id` + `trade_metric` contract.
- Without NOT, every combination of them is monotone, so "not ready =
  False" stays sound at every level.
- A future child that is neither (for example one that needs entry-anchored
  state) is out of scope. It would have to extend this table explicitly.

**D4. One market fold, used by every execution path.** A new module
`managed_composite.py` owns:
- `fold_phase_paths(spec, frame, plan, side, *, bundle, context,
  identities) -> FoldedPaths`. Per path it returns:
  - `market`: the AND of all market `require` children as one read-only
    bool array. If the path's `at_least` has only market terms, it is
    ANDed with `count ≥ k` here. The value is `None` if the path has no
    market part;
  - `trade_require`: the trade children of `require`, in order;
  - `mixed_at_least`: `k` plus its terms, each either a market array or
    a trade child. Present only when `at_least` mixes kinds;
  - the per-child market arrays, used for attribution only.

  Market arrays come from `evaluate_predicate` for predicates, and from
  the existing `adx_di_threshold` series formula for that atom. The
  formula is extracted from `historical_managed_projection.py` into one
  function that the atomic projection rule also uses, so both stay
  byte-identical.
- The single-trade replay core:
  - calls `fold_phase_paths` once per call per composite rule, for the
    trade side only;
  - on each bar checks the paths in declared order: `market[i]`, then
    each trade child through the existing `_phase_met`, then the mixed
    count;
  - takes the first true path.
- The projection calls `fold_phase_paths` for both sides and emits the
  arrays (D6).
- The composite is therefore one piece of code evaluated in two
  places. Neither side re-implements the other's logic.

**D5. Runtime semantics are unchanged outside the composite.**
- The composite is dispatched from `_phase_met`, but with a per-call
  fold cache created next to `series_cache`. Atomic conditions keep
  their current code path.
- Rule order, target-rank skip, the same-bar cascade, offsets 0/1,
  `activate_when` and stop/take/runtime logic are unchanged.
- `phase_changed` for a composite rule:
  - `component_id` = `composite_phase_condition`;
  - `metadata` = `{"path_id": <winning path>, "children": {child_id:
    bool}}`, covering every child referenced by the winning path.
  Market values come from the per-child arrays. Trade values come from
  `_phase_met`, which is evaluated only at the transition bar.

**D6. Projection contract: additive `paths` variant.**

```
ManagedPhaseTransitionRule(kind, rule_id, target_phase,
                           condition_id, distance_id, trade_metric,
                           paths: tuple[ManagedTransitionPath, ...] | None = None)

ManagedTransitionPath(path_id, condition_id: str | None,
                      thresholds: tuple[ManagedTransitionThreshold, ...],
                      at_least: ManagedTransitionAtLeast | None)
ManagedTransitionThreshold(distance_id, trade_metric)
ManagedTransitionAtLeast(k, terms: tuple[ManagedTransitionTerm, ...])
ManagedTransitionTerm(condition_id | (distance_id, trade_metric))   # exactly one
```

- Exactly one of `condition_id`, `distance_id` + `trade_metric`, or
  `paths` is set on a rule.
- Atomic rules are emitted exactly as today. The serializer omits
  `paths` when it is `None`, so the wire bytes of non-composite
  candidates are unchanged.
- A path is true on bar `i` for side `s` iff:
  - `condition_id` is absent or `conditions[condition_id].s[i]`;
  - every threshold holds, `metric ≥ distances[distance_id][i]`
    (NaN → False);
  - `at_least` is absent or `count(true terms) ≥ k`.

  The rule fires on the first true path in order, and a consumer
  attributes `path_id`.
- Id convention (opaque to consumers):
  - `phase:{rule_id}:path:{path_id}:condition` for a folded mask;
  - `phase:{rule_id}:child:{child_id}:condition|distance` for mixed
    terms and trade thresholds.

  A trade child used by several paths has one distance entry.
- Wire size: one condition series per path, however many market
  children it folds. Only mixed `at_least` market terms travel
  individually.

**D7. Context bundle.** `state` predicates (directly or inside
`temporal`) need the `ContextBundle`.
- Projection: `evaluate_execution_projection` passes
  `evaluation.contexts`.
- Live open-trade: `open_trade.py` passes the `evaluation.contexts` it
  already computes.
- `/managed-replay` has no evaluation. It calls `build_context_bundle`
  only when some composite phase condition contains a `state`
  predicate, and otherwise passes `None`. This is zero extra work for
  every other spec.
- A `state` predicate reached without a bundle fails closed, as the
  predicate layer already does.

**D8. Memo: predicate children are memoized, paths are not.**
- In the projection, under the same gate as `_memo_identities` (a
  native frame over the context's market arrays), every predicate child
  is evaluated through `evaluate_predicate` with its `PredicateIdentity`.
  Identities come from `resolve_predicate` with the candidate's feature
  and context identities. An identical predicate in a `composite_setup`
  or in another rule or candidate therefore shares one node per batch.
- `MemoizedStageIdentities` gains a `managed` stage, resolved after
  `exit_policy` by the single resolution function both the pre-pass and
  the projection use. The stage is empty (no predictions) unless
  `exit_management.mode == "managed"` and some phase rule is a
  composite with a predicate child, so the predictions for existing
  specs are unchanged. If the stage cannot be resolved it is `None`,
  like the other stages, and the projection then evaluates its
  predicate children unmemoized. Its consumptions are `local` plus `nested` per
  predicate child per side, in projection order, like composite_setup
  children (`evaluation.py:275`).
- Folding, `at_least` counting and the `adx_di_threshold` series are
  not memo nodes. They are O(n) local work over ready arrays, and the
  atom series keeps its current `_cached_series` path.
- Single-trade replay (live, `/managed-replay`) runs with no memo
  context, as today.
- Over-prediction: routes that evaluate without building the projection
  (diagnostics) predict the managed stage but do not consume it. The
  root releases those counts on exit, which is existing behavior for
  unconsumed predictions. It affects retention only, never results.

**D9. Planning.**
- `feature_plan.py`: the `phase_rules` loop recognizes the composite.
  - Predicate children append their `features()` to the existing
    `predicate_features` list, so they are planned last through
    `add()`, with the existing fail-closed collision check.
  - Atom children are planned by the existing atom branches (ATR for
    `mfe_atr`, ADX/DMI for `adx_di_threshold`).
- `live_calculation_requirements.py`: a composite contributes its
  children.
  - Predicates use `_predicate_history` from stage 1: zero for
    compare/range/state, `bars − 1` plus inner for temporal.
  - Atoms use their existing explicit zero entries.
  - Anything unknown fails closed.
  - The open-trade window is anchored at `min(plan bar, entry bar)`
    (`application/evaluate_open_trade_projection.py:39`), so a temporal
    window before the entry is covered.

**D10. Static validation.** `static_semantics.py` validates every
composite phase condition without market data:
- the structure (D1, D2);
- each predicate through `parse_predicate` with the declared
  `context_refs`;
- atom ids against the four-atom allowlist.

Atom parameter validation stays where it is today (evaluation), so
atomic rules behave exactly as before.

**D11. Side and readiness.**
- The trade side selects the predicate side, and the projection emits
  both.
- A predicate is side-free unless it has a `short` override, so
  "directional DI" is written with an override (D1) or with the
  `adx_di_threshold` atom.
- Temporal predicates are market-time windows, not entry-anchored. A
  `held_for` may include bars before the entry, and this is intended.
- Not-ready and non-finite values are False for every child kind.

**D12. Equivalence gate.**
- The parity corpus (`test_ema_pullback_historical_managed_projection.py`)
  gains composite specs. The reference consumer implements the path
  rule of D6.
- For every side and entry, the phase trajectory, including
  `rule_id` and `path_id`, SHALL equal `evaluate_managed_replay`.
- Specs covered:
  - the owner's case;
  - a mixed `at_least`;
  - a pure-market `at_least`;
  - a trade-only path;
  - a `state` predicate;
  - a `temporal` predicate;
  - two composite rules in one spec (cascade).
- Live start-after-entry is covered for the same specs against its own
  offset-1 expectation.

## Risks / Trade-offs

- **Projection size.** Each path adds two bool series. This is bounded
  by the number of paths, not children. It is the same order as today's
  per-rule series.
- **Fold cost per replay call.** On `/managed-replay` and live the fold
  is O(n) numpy per composite rule per call. The existing atoms already
  convert whole columns per call (`_cached_series`), so the order of
  cost is unchanged. The per-call fold is not memoized.
- **Attribution change for composite only.** `phase_changed.component_id`
  and `metadata` differ for composite rules. Research passes both
  through opaquely, and non-composite events are unchanged.
- **Temporal children look before the entry.** This is by design
  (D11), and it matches how the same predicate behaves pre-entry. An
  entry-anchored window would be a trade-relative child, which is out
  of scope.

## Migration Plan

Additive only.
- Specs without `composite_phase_condition` keep identical plans,
  identities, compute counts, projection bytes, and replay/live outputs.
  This is pinned by the declared-invariant gate, which gains managed
  cases first (tasks 0).
- Rollback is a revert.
