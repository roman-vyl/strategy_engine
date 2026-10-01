## Why

Research wants to take part of a position off at prices fixed at entry,
for example 25% at +1% and 25% at +3%, while the existing take-profit
closes the rest. Today an exit policy has exactly one take per profile:
all `take_profit` rules of a profile fold into one minimum
(`exits.py::_profile_selection`), and every entry projection carries a
single `initial_take`. A ladder of partial takes is not expressible.

This change is the Strategy Engine stage of the accepted master plan
"Frozen Partial Take Ladder V1"
(`partial-take-profit/v1-frozen-partial-take-ladder-design.md`). Engine
goes first because it owns the strategy semantics that Research, Runtime
and the executor will consume.

## What Changes

**New exit components with their own exit kind.**
- `pct_partial_take` (`pct`, `fraction_of_initial`) and
  `atr_partial_take` (`distance{timeframe, period, multiplier}`,
  `fraction_of_initial`), both with `exit_kind: "partial_take"`.
- They live in `exit_policy` (`always_on` and the three profiles), next
  to the existing stop and take rules.
- The component family binds the exit kind, as for existing distance
  components. `atr_take_profit` and every other existing component keep
  their meaning.

**Canonical ladder semantics, owned by Engine.**
- A leg closes `fraction_of_initial` of the initial position quantity,
  never a fraction of the remainder.
- The existing final take closes all remaining exposure at the moment
  its level is reached.
- Leg levels are frozen at the entry boundary.
- `disable_initial_tp` (managed) disables only the final take; legs
  stay.
- The relative order of legs and the final take does not affect spec
  validity. Consumers traverse touched take levels in price order away
  from entry, and the final take stops the traversal.
- A partial fill never feeds back into Engine. The managed state
  machine and `HistoricalManagedProjection` are unchanged.

**Static validation:**
- `0 < fraction_of_initial < 1`;
- for each profile, the sum of fractions of the legs in force
  (`always_on` plus the profile) is below 1;
- a profile with legs must also have a final `take_profit`;
- `instance_id` stays unique across the whole exit policy and is the
  canonical `take_id`;
- `pct > 0` and `multiplier > 0`, so a leg is on the profit side by
  construction.

There is no validation of a leg's position relative to the final take.

**Additive contracts, omitted when empty:**
- `ExecutableEntryOpportunity.partial_takes`: legs as
  `{take_id, ratio, fraction_of_initial, attribution}`, with the new
  canonical `exit_kind` value `"partial_take"`;
- `LiveEntryPlan` / `DesiredEntry` and the HTTP `desired_entry`:
  `partial_takes` as `{take_id, price, fraction_of_initial}` in
  normalized decimal text.

The key is omitted when there are no legs. The wire for existing specs
is byte-identical, and there is no contract version bump. A consumer
that does not know the field rejects a spec with legs (fail closed).

**Exit policy evaluation:**
- legs are evaluated as distance rules with per-instance evidence;
- they are not min-aggregated into `take_profit_ratio_*`;
- protection readiness also requires every configured leg of the
  selected profile.

**Plumbing:**
- `atr_partial_take` plans its `atr_distance` through the existing exit
  distance loop, and ATR columns are shared by label;
- memo identities for leg nodes;
- live history policy entries for both components (zero additional
  lookback).

**Compute cost must not grow.** For specs without partial takes, the
following are identical to before:
- `plan_hash`;
- node identities and compute counts;
- `/range`, `/range-batch` and `/live-entry` output;
- `/managed-replay` and open-trade output.

**BREAKING:** none.

## Non-Goals

- Research execution and accounting of legs, Runtime and executor
  support. These are later stages of the master plan.
- Signal- or RSI-driven partial exits, market reductions, legs created,
  moved or cancelled by a managed phase, scale-in, partial stop-loss.
- Any change to the managed state machine,
  `HistoricalManagedProjection`, `/managed-replay`, the open-trade
  request, response or receipt.
- Gap and slippage modelling.
- Other leg components (constant USD, R multiples).
- Composer catalog and UI exposure. Legs are authored as raw spec only.

## Capabilities

### New Capabilities
- `ema-pullback-partial-take-ladder-v1`: the partial take components,
  ladder semantics (fraction of initial, final closes all remaining,
  frozen levels, price-ordered traversal, `disable_initial_tp` scope),
  static validation, and the stable `take_id`.

### Modified Capabilities
- `ema-pullback-exit-policy-v1`: partial take components join the
  standard set, are excluded from like-kind minimum composition, and
  gate protection readiness.
- `strategy-research-execution-contract-v1`: optional `partial_takes`
  on executable entry opportunities, and the `"partial_take"` exit
  kind.
- `live-entry-projection-v1`: optional `partial_takes` in the desired
  entry contract, and leg geometry.
- `ema-pullback-feature-plan-v1`: planning of `atr_partial_take`
  distances.
- `live-calculation-window-planning`: history policy for partial take
  components.
- `batch-computation-reuse`: identity twins for leg nodes, and no
  compute regression for specs without legs.

## Impact

- `strategies/ema_pullback/raw_spec_identity.py`: a
  `EXIT_PARTIAL_TAKE_SUPPORTED` allowlist.
- `static_semantics.py`: ladder validation.
- `exits.py`:
  - a `partial_take` family in `_exit_rule_head`;
  - the `pct` distance;
  - `partial_take` in `_ProfileSelection` and `_ready`;
  - memo resolve.
- `feature_plan.py`: ATR distance for `atr_partial_take`.
- `strategies/contracts.py`: `PartialTakeLeg`, `LivePartialTake`, the
  optional fields, and `ExitAttribution.exit_kind`.
- `historical_execution_projection.py`: legs on opportunities.
- `potential_entries.py`, `live_projections/live_entry.py`: leg prices.
- `adapters/http/strategy_serialization.py`, `adapters/http/models.py`:
  serialization that omits empty legs.
- `live_calculation_requirements.py`: zero-lookback policy entries.
- Downstream:
  - Research Service and Strategy Runtime decoders are strict, so they
    reject specs with legs until their own stages land;
  - specs without legs are unaffected everywhere.
