## Context

See `proposal.md` for motivation. Managed replay already owns monotonic MFE,
side-relative candidate arbitration, next-bar effectiveness, and a frozen
`initial_risk` introduced with `mfe_r`. Live start-after-entry supplies the
initial stop, while the public managed-replay wire does not yet expose the
internal evaluator's optional initial-stop input.

The historical projection intentionally hides strategy `component_id` and raw
parameters. Its current `stop_action.distance_id` has one hard-coded meaning:
an absolute per-bar offset from entry. Research mirrors that meaning exactly.
True trailing therefore requires a projection-contract extension rather than
another use of the existing distance field.

## Goals / Non-Goals

**Goals:**

- Express fixed initial-R profit locks and true MFE-following initial-R trails.
- Preserve one managed stop lifecycle and one tighten-only arbitration path.
- Give Research closed, generic execution semantics with opaque numeric references.
- Preserve old projection bytes and old request compatibility.
- Maintain single-trade, live, and historical projection parity at their existing bar boundaries.

**Non-Goals:**

- Removing or redefining `break_even_stop` or `lock_profit_stop`.
- Publishing managed stop components through the composer catalog.
- Changing stop-hit, gap-fill, fees, PnL, exchange order, or unified exit arbitration semantics.
- Adding ATR, price-percent, or dynamically changing risk denominators to the new components.

## Decisions

### D1. Two public policy components, one shared R primitive

Engine adds `initial_r_lock_stop` and `initial_r_trailing_stop`. Both parse a
positive `trigger_r`, read the same frozen `initial_risk`, compare the same
monotonic `mfe_r`, and then differ only in their candidate formula. This keeps
the distinction between a one-time step and a continuously advancing trail
explicit. A single component with a mode field was rejected because it would
mix two policy identities and complicate validation and attribution.

The parser enforces `0 <= lock_r <= trigger_r` and
`0 < trail_distance_r <= trigger_r`. Besides making invalid inputs fail early,
these bounds ensure the first eligible candidate protects at least 0R.

The parser lives in the dependency-neutral `raw_spec_identity.py` and is
called from static semantics, so `ValidateStrategySpec` rejects an invalid
configuration before feature planning, projection building or replay. The
managed evaluator and the projection builder reuse the same resolver.

### D2. Phase activation and R trigger are independent gates

`activate_when.phase_at_least` remains the outer lifecycle gate. The component's
`trigger_r` is an intrinsic stop-policy gate. A candidate exists only when both
hold. Encoding 6R solely as a phase transition was rejected because another
condition could enter the same phase and accidentally activate the stop below
its intended R threshold.

Phase transitions continue to run before stop rules on a bar, so a transition
and R trigger reached together can produce one decision effective next bar.

### D3. Shared candidate calculation, unchanged arbitration

The managed evaluator will parse the new rules through one helper and calculate
their candidates from `entry_price`, `mfe_price`, side, and frozen risk. The
result joins the existing candidate list. Existing max/min selection, active
stop tightening, `1e-8` movement threshold, event creation, and attribution
rules remain authoritative.

The evaluator's existing bar-range conventions remain intact: coarse historical
replay includes its entry bar, while live start-after-entry begins after the
entry bar. In both cases a decision from bar N is effective only on bar N+1.

### D4. `stop_formula` is closed projection execution semantics

`ManagedStopActionRule` gains optional semantic fields at the end of its
contract:

- `stop_formula`: `initial_r_lock | initial_r_trailing`, or `None` for every
  legacy stop action. Engine never emits a legacy formula value: `None` is
  omitted on the wire, and Research normalizes the omitted field to its own
  `entry_offset` meaning (D5);
- `trigger_distance_id`: an opaque reference required for either R formula and
  `None`/omitted otherwise;
- existing `distance_id`: absolute price offset for a legacy action (omitted
  formula), lock R for `initial_r_lock`, and trail-distance R for
  `initial_r_trailing`.

For new rules, both R values are emitted as already resolved constant distance
series. Research knows that the trigger reference is compared with `mfe_r` and
that the action distance is scaled by frozen risk because those meanings belong
to the closed formula. It never sees the source component or named raw fields.

An alternative that added `trigger_r`, `lock_r`, or `trail_distance_r` directly
to the DTO was rejected because it leaks strategy vocabulary across the
projection boundary. Treating a trail as an ordinary entry offset was rejected
because it cannot represent trade-local MFE.

### D5. Omission preserves the legacy wire

Engine serializes no formula or trigger field for existing stop rules. Research
defaults an omitted formula to `entry_offset` and requires no trigger reference
for it. Consequently old payloads still decode, and new Engine output for a
legacy-only spec is byte-identical to the old output.

### D6. Public managed replay exposes the existing optional input

The request model and domain request gain optional `initial_stop_price`, which
the application passes to the already-capable internal evaluator. The field is
side-validated before evaluation. Omission preserves the existing request and
the current fail-closed behavior of R-dependent rules.

### D7. No new feature or authoring-catalog surface

Both components are zero-lookback rules using trade state already maintained by
managed evaluation. Feature planning must not add ATR or another series. They
are registered in live calculation requirements but are not added to the
composer catalog, matching the current boundary for managed stop components.

## Risks / Trade-offs

- [Engine and Research could disagree on formula fields] → Specify a closed enum,
  strict reference invariants, shared cross-repo fixtures, and end-to-end decode tests.
- [Two trade evaluators in Engine can drift] → Test single-trade candidate
  timelines against the historical projection reference consumer for both sides
  and several entries.
- [Floating-point comparison around a trigger] → Preserve the existing float
  model and `>=` semantics used by `mfe_r`; test exact and just-below thresholds.
- [Legacy bytes change accidentally] → Golden/serialization test legacy stop
  actions and omit all new fields rather than serializing defaults.
- [Deploying Engine first causes Research decode failure for new specs] → Do not
  activate specs using new components until compatible Research is deployed.

## Migration Plan

1. Deploy compatible Research code that accepts both legacy and new stop actions.
2. Deploy Engine code that can emit new formulas and accept managed-replay initial stop.
3. Only then enable strategy specifications containing the new components.
4. Rollback by removing the new components from active specs; legacy projection
   and execution remain unchanged in both versions.
