# Design: EMA Pullback potential entry for touch-anchor v1

## 1. Architectural boundary

The existing EMA Pullback calculation order remains authoritative and unchanged:

```text
feature planning
→ indicator evaluation
→ contexts and context consumption
→ direction and blockers
→ setups
→ triggers
→ risk and final entries
→ exit policy
```

Potential entry is an additive projection over already calculated objects:

```text
existing calculation results
        ↓
PotentialEntry projector
        ↓
bar-aligned potential entry/stop/take vectors
```

The projector must not recalculate indicators, ATR, blockers, setups, triggers, risk rules, or exit-rule selection.

## 2. Domain model

Version 1 introduces one minimal immutable vector object per enabled side:

```text
PotentialEntry
- side: long | short
- entry_price: bar-aligned optional numeric values
- stop_price: bar-aligned optional numeric values
- take_price: bar-aligned optional numeric values
```

The model deliberately has no separate eligibility field. On a bar, eligibility is represented by the presence of the complete price triple.

The three vectors have identical length and obey this invariant at every index:

```text
entry, stop, and take are all present
or
entry, stop, and take are all absent
```

## 3. Projector inputs

The projector consumes only existing calculation outputs:

- `SideSetupEvaluation.pre_trigger_allowed` for the side;
- the already evaluated `SideTriggerEvaluation` for trigger identity and the touch-anchor `close_ok` side precondition;
- `FeatureFrame` and `EmaPullbackFeaturePlan` for the anchor EMA vector;
- selected raw initial stop-loss distance for the side and bar;
- selected raw initial take-profit distance for the side and bar.

`pre_trigger_allowed` remains an internal existing field. This change does not publish it as a new top-level strategy state.

## 4. Trigger scope

The projector produces `PotentialEntry` records only when the configured trigger component is `touch_anchor`.

For other trigger components, version 1 returns an empty `potential_entries` object. It does not infer a price and does not change their existing trigger or final-entry behavior.

For `touch_anchor`, the response contains only enabled-side keys. Disabled sides are omitted rather than represented by all-null vectors.

## 5. Potential price calculation

For every enabled side and bar, a potential entry may be produced only when:

```text
pre_trigger_allowed is true
AND touch_anchor.close_ok is true
AND anchor EMA is available, finite, and greater than zero
AND selected initial stop distance is available, finite, and greater than zero
AND selected initial take distance is available, finite, and greater than zero
```

For `touch_anchor`:

```text
entry_price = anchor EMA
```

Long prices:

```text
stop_price = entry_price - stop_distance
take_price = entry_price + take_distance
```

Short prices:

```text
stop_price = entry_price + stop_distance
take_price = entry_price - take_distance
```

The projector emits the complete triple only when all source values and all derived prices are finite and strictly greater than zero. Otherwise all three values at that bar are absent.

The projector reuses the already calculated touch-anchor `close_ok` trace instead of re-reading the spec or recalculating market geometry. For long, `close_ok` means close is at or above anchor; for short, it means close is at or below anchor. This prevents publishing an anchor price on the wrong side of the current market, where the intended resting touch plan would become immediately marketable.

The projector intentionally does not require the touch itself or `trigger.allowed` to be false. If `touch_anchor` fires on the same bar while `pre_trigger_allowed`, `close_ok`, and all required values remain valid, the existing final entry may be true and the potential-entry triple remains present. This additive projection describes the bar's potential price geometry; it does not infer Runtime position state.

## 6. Raw exit-distance preservation

The current exit-policy implementation calculates an absolute distance and then publishes a legacy-compatible ratio:

```text
raw distance
→ distance / close
→ existing stop_loss_ratio or take_profit_ratio
```

Potential-entry calculation must use the raw distance, not reconstruct a price directly from the published ratio and anchor.

Exit-policy evaluation shall therefore retain both forms internally:

- the existing selected ratio vectors, unchanged;
- additive selected raw distance vectors for long and short initial stop and take.

Rule composition remains unchanged:

- always-on and current profile rules are combined exactly as today;
- multiple rules of the same distance kind use the same minimum-distance selection;
- current side-relative profile selection remains authoritative.

The existing `ExitPolicyEvaluation.to_wire()` payload does not need to expose raw distances. Existing ratio fields and rule evidence remain byte-for-byte semantically compatible.

## 7. Range result integration

`StrategyRangeResult` gains an additive `potential_entries` object. The HTTP strategy range response serializes it alongside the existing `entries` and `exit_policy` groups. The object is always present in a successful response.

For a non-`touch_anchor` trigger, the exact wire shape is:

```json
{
  "potential_entries": {}
}
```

For `touch_anchor`, only enabled-side keys are emitted. A disabled side is omitted. For each included side, the wire representation is:

```text
potential_entries:
  long|short:
    entry_price: [decimal text | null, ...]
    stop_price:  [decimal text | null, ...]
    take_price:  [decimal text | null, ...]
```

Numeric API values use the existing normalized decimal-text convention. Missing values use JSON `null`.

No `allowed`, `armed`, `trigger_type`, `order_kind`, label, plan ID, config hash, or market-data hash is duplicated inside this group. Existing parent response identity and provenance remain authoritative.

## 8. Calculation reuse

A range request must still execute feature and strategy calculation once.

The EMA Pullback evaluator passes its existing setup, trigger, feature, and exit-policy results directly to the new projector. A larger public pipeline rewrite or a mandatory new public evaluation bundle is not required for v1.

Any internal structural extraction introduced for reuse must:

- preserve the current calculation order;
- preserve existing public request and response behavior except for the additive `potential_entries` field;
- avoid a second indicator or strategy evaluation;
- keep the projector independent of HTTP and Runtime concerns.

## 9. Compatibility and failure behavior

This change must not alter:

- final long/short entry masks;
- `touch_anchor` trigger masks or trace fields;
- stop/take ratios and readiness;
- selected exit profiles;
- component evidence;
- managed replay;
- capability readiness stage.

Warmup or unavailable source data results in an absent triple on the affected bar, not a partial potential entry.

Invalid strategy specs continue to fail through existing validation/evaluation errors. The projector does not invent fallback ATR multipliers, fallback anchor prices, or fallback stop/take rules.
