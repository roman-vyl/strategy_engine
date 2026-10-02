## Context

See proposal.md (Why). The accepted master plan is
`partial-take-profit/v1-frozen-partial-take-ladder-design.md` in the
project files. This change is its stage 1: Strategy Engine only.

How a final take is born today (main 07ff911):

1. `exit_policy.always_on.exits` and `profiles.<p>.exits` are read by
   `raw_spec_identity.resolve_exit_rule_groups`. Component allowlists
   are `EXIT_SIGNAL_SUPPORTED` and `EXIT_DISTANCE_SUPPORTED`
   (`raw_spec_identity.py:21-31`). `static_semantics.py:105-120`
   rejects unknown components and duplicate `instance_id`s.
2. `exits._exit_rule_head` (`exits.py:391-414`) binds the component
   family to `exit_kind`. A distance component is `stop_loss` if its id
   contains `stop_loss`, otherwise `take_profit`, and a mismatch raises.
3. `exits._distance` (`:300-321`) returns `(distance, ratio =
   distance / close)` per rule. The evidence loop (`:518-563`) records
   one `ExitRuleEvidence(instance_id, component_id, exit_kind, group,
   side=None, distance_ratio)` per distance rule.
4. `_profile_selection` (`:417-455`) lists the instance ids per kind.
   Take rules fold into one minimum per profile, and `_ready`
   (`:378-385`) requires the stop and take aggregates to be non-null.
5. Historical: `historical_execution_projection._entry_opportunities`
   (`:116-190`) emits `ExecutableEntryOpportunity` with `initial_stop`
   and `initial_take`, serialized by
   `strategy_serialization._serialize_opportunity`.
6. Live: `potential_entries._project_side` takes the anchor as entry
   and adds the aggregated absolute distances.
   `live_entry._plan_for_side` (`:49-81`) builds `LiveEntryPlan` and
   returns `None` on any missing or invalid value.

`feature_plan.py:278-304` already plans an `atr_distance` feature for
every exit rule that has a `distance`, keyed by `instance_id`.
Memo identities come from `exits.resolve_distance_rule` and the
profile aggregates (`exits.py:717-990`). The live history planner
(`live_calculation_requirements.py:95-102, 442-475`) fails closed on
exit components it does not know.

Downstream decoders are strict:
- Research `ExecutableEntryOpportunity` DTO is `extra="forbid"` with a
  closed `exit_kind` Literal.
- Runtime decodes `desired_entry` by an exact field set.

## Goals / Non-Goals

**Goals:**
- Engine publishes the ladder as data: a frozen relative or absolute
  level, a fraction of initial, and a stable id per leg.
- Every path for a spec without legs stays bit-identical, including
  the wire, the plan and node identities.

**Non-Goals:**
- Engine executing, ordering or simulating legs. The price-ordered
  traversal in the capability spec is a contract for consumers; Engine
  only states it.
- Exposing per-leg data on the `/range` response beyond the existing
  rule evidence.

## Decisions

### D1. A new component family, not `atr_take_profit` with a new kind

`pct_partial_take` and `atr_partial_take` form a third family,
`partial_take`, in `_exit_rule_head`. They have a new allowlist
`EXIT_PARTIAL_TAKE_SUPPORTED` and their kind must be `partial_take`.

- Alternative: let `atr_take_profit` accept `exit_kind: partial_take`.
  This is rejected because it breaks the family-binds-kind rule. It
  would change the meaning of an existing component and the
  validation of every take rule.
- Alternative: a `partial_takes` list outside `exit_policy`. This is
  rejected because profiles, `instance_id` uniqueness, evidence and
  readiness already live in `exit_policy`.

### D2. Legs are distance rules that skip aggregation

- `_distance` gains the `pct` variant: `distance = pct × close`,
  `ratio = pct`. `atr_partial_take` reads the ATR column planned for
  its `instance_id`, exactly as `atr_take_profit`.
- `_ProfileSelection` gains `partial_take: tuple[instance_id, ...]`
  (`always_on` first, then the profile, in declared order). Legs never
  enter the take minimum, so `take_profit_ratio_*` and
  `take_profit_distance_*` are unchanged.
- `_ready` additionally requires each leg in the selection to be
  non-null. A `pct` leg is never null, and an ATR leg is null during
  warm-up.
- Without legs, the selection tuple is empty and `_ready` takes the
  same code path, so the output is identical.

### D3. Legs require a final take in the same profile

Static validation requires a `take_profit` rule in force (`always_on`
or the profile) for every profile that has legs.

This follows from the semantics: a ladder whose fractions sum below 1
must have something that closes the rest. Live already returns no plan
without a take (`live_entry.py:64-65`).

Alternative: legs without a final, with the rest closed by stop or
signal. This is deferred; it can be relaxed later without breaking any
spec.

### D4. V1 components are `pct` and `atr` only

Constant USD and R-multiple legs are out of scope. The family and its
allowlist make adding them later purely additive.

### D5. Static validation lives in the canonical validator

The checks are:
- fraction in (0, 1);
- the fraction sum below 1 per profile (`always_on` plus each of
  `aligned`, `countertrend`, `neutral`);
- a final take present;
- `pct > 0` and `multiplier > 0`.

They live in `static_semantics.py`, next to the existing exit-component
checks, so `/validate` and evaluation reject the same specs without
market data. There is deliberately no check of leg levels against the
final take; the owner removed it.

### D6. Wire: omit `partial_takes` when empty, no version bump

- `PartialTakeLeg(take_id, ratio, fraction_of_initial, attribution)`
  is added to `strategies/contracts.py`.
  `ExecutableEntryOpportunity.partial_takes` defaults to `()`.
- `_serialize_opportunity` writes the key only when the tuple is
  non-empty.
- `ExitAttribution.exit_kind` widens to include `"partial_take"`. It
  is used only inside legs.

Effect: specs without legs stay byte-identical on
`strategy_evaluation_execution.v2`. Strict consumers reject specs with
legs, which is the intended fail-closed behavior until Research
lands its stage.

Alternative: a `v3` envelope. This is rejected: it would force every
consumer to migrate for specs that do not use the feature.

### D7. Historical legs come from rule evidence plus static config

- For each opportunity, the legs are those of `always_on` plus the
  locked profile.
- `ratio` is read from that rule's `ExitRuleEvidence.distance_ratio`
  at `bar_index`. Attribution is direct: `rule_id = take_id =
  instance_id`. This is unlike `_pick_leg_attribution`, which has to
  recover the winner of a minimum.
- `fraction_of_initial` is static. It is taken from the parsed exit
  rules once per evaluation, not added to `ExitRuleEvidence`, so the
  `/range` evidence wire is unchanged.
- Legs are sorted by `ratio` ascending, ties by declared order.

### D8. Live leg prices use the same basis as the final take

The live entry is the anchor, and the final take is `entry ±
aggregated distance` (`potential_entries.py`). The leg prices are:
- `atr_partial_take`: `entry ± k·ATR`, using the leg's own absolute
  distance on the target bar, the same series as the final take
  formula;
- `pct_partial_take`: `entry × (1 ± pct)`, relative to the planned
  entry, not `pct × close`.

Per-leg absolute distances are kept on the internal exit-policy result
for the live projection only. They are not serialized on `/range`.

- `LivePartialTake(take_id, price, fraction_of_initial)`, normalized
  decimal text, is added. `LiveEntryPlan` and `DesiredEntry` gain
  `partial_takes = ()`.
- The HTTP model omits the key when the tuple is empty.
- If any leg in force has a missing, non-positive or non-profit-side
  price, `_plan_for_side` returns `None`, the same rule as for the
  stop and take.
- There is no comparison of leg prices with `initial_take_price`.

Pre-existing and unchanged: the live entry basis (anchor) differs from
the historical basis (the signal bar close). Legs inherit this exactly
as the final take does.

### D9. Feature plan and memo

- `atr_partial_take` is already planned by the existing exit-distance
  loop. The only change is that `exit_columns.setdefault(exit_kind,
  ...)` is skipped for `partial_take`, because no consumer reads a
  kind-level alias for legs. Specs without legs keep the same plan
  and `plan_hash`.
- `resolve_distance_rule`:
  - `atr_partial_take` returns the existing `exit.distance.atr`
    identity over its column, so it is shared with SL/TP on the same
    ATR;
  - `pct_partial_take` returns a new `exit.distance.pct` identity with
    `params={"pct": pct}`.
- The readiness aggregate includes leg identities only when legs
  exist, so identities without legs are unchanged.
- `fraction_of_initial` and `instance_id` never enter an identity.

### D10. Live history policy

Both components are registered in `_ZERO_LOOKBACK_EXITS`. The ATR
history comes from the planned ATR feature, as for `atr_take_profit`.

### D11. Managed, open-trade and the managed projection are untouched

- `managed.py` works from prices, not quantity.
- `desired_take_price` stays the initial take or `None`.
- The receipt is built field by field and never carries
  `DesiredEntry`.

No code in `managed.py`, `historical_managed_projection.py`,
`live_projections/open_trade.py` or `/managed-replay` changes. The
`disable_initial_tp` scope ("final only") is a consumer rule stated in
the capability spec.

## Risks / Trade-offs

- [A consumer silently ignores `partial_takes`] → The key is
  top-level and the downstream decoders are strict. An unaware
  consumer fails instead of trading without legs.
- [Float drift between the historical `ratio` and the live `price`] →
  Both derive from the same distance series. Live normalizes to
  decimal text exactly like the existing take.
- [An ATR leg delays readiness during warm-up] → This is intended and
  identical to an ATR final take on the same column.
- [A leg beyond the final never fills, which may surprise authors] →
  This is allowed by decision of the owner. The capability spec states
  the traversal rule, and Research will test it.
- [The ATR distance column is shared by label between a leg and SL/TP]
  → This is the existing behavior for any two ATR exits with the same
  timeframe, period and multiplier. The memo identity is shared on
  purpose.

## Migration Plan

- The change is additive. Deploy Engine first: existing specs are
  unaffected.
- Do not author specs with legs until Research (stage 2) accepts
  `partial_takes`.
- Rollback: revert the Engine change. No stored data references legs.
