## Why

A managed phase condition can compare a feature with a constant on the current bar (predicates) and can measure how much a
feature moved over a fixed number of bars (`change {operand, lookback, op, value}`). It cannot measure how much a feature moved
since the trade was opened. The reference point of such a comparison is a value fixed at the entry bar of each trade, so it
depends on the trade and cannot be expressed as a market series of the predicate layer.

## What Changes

- One new trade atom `change_since_entry {operand, op, value}`, accepted only as a child `condition` of
  `composite_phase_condition`.
  - `operand`: a feature reference in the predicate layer's operand grammar, resolved through the canonical feature-kind
    contract.
  - `op`: one of `>=`, `>`, `<=`, `<`.
  - `value`: a finite constant (any sign).
- Semantics. For a trade with entry bar `e`, on bar `i ≥ e` the child is True iff `operand(i) − operand(e) <op> value`, where
  `operand(x)` is the operand's aligned value on base bar `x` (for a higher timeframe: its last completed bar at `x`, no
  look-ahead). The anchor `operand(e)` is read once per trade and does not move afterwards.
- Non-finite: if the anchor or the current value is missing or non-finite, the child is False. An anchor that is not finite
  keeps the child False for the whole trade.
- Side: side-free; the same `op` and `value` apply to both sides. No `short` override in this version. Side-relative
  conditions are combined in a path with existing side-aware children (for example a `compare` predicate with a `short`
  override).
- Composition: it is a trade child of `composite_phase_condition`, exactly like `mfe_r`: it may appear in `require` and in
  `at_least`, mixed with market children.
- Projection: a path may carry `entry_changes`, and an `at_least` term may carry `entry_change`, each
  `{series_id, op, value}`. `series_id` names a per-bar float series in the existing `distances` map (NaN where not finite).
  The consumer reads `series[entry_index]` once per trade and compares `series[i] − series[entry_index]` per bar.
- Planning: the operand is planned exactly as a predicate operand of a composite phase condition. No new indicator.
- History: no additional history. The operand's own warm-up is counted by the existing per-feature policies, and the
  open-trade window already contains the entry bar.
- Nothing changes for specs without `change_since_entry`: no new feature, node identity, plan label or wire field; the same
  `plan_hash`, compute counts and byte-identical projection.

## Impact

- `ema-pullback-composite-phase-condition-v1`: MODIFIED `Children` (new atom in the list); ADDED `Entry-anchored change child`.
- `historical-managed-projection-v1`: MODIFIED `Composite phase transitions are projected as paths`; ADDED
  `Entry-anchored change terms`.
- `live-calculation-window-planning`: ADDED `History policy for the entry-anchored change child`.
- `batch-computation-reuse`: ADDED `No compute regression without the entry-anchored change child`.
- Not modified: `pre-entry-predicates-v1` (the predicate layer stays market-only; the atom reuses its operand parser and
  column conversion), `ema-pullback-feature-plan-v1` (the operand is an ordinary feature reference).
- Consumers of the historical projection that execute composite paths need to support the new term before they can execute
  specs that use it. Specs without it are unaffected.

## Verification

- Unit tests: parsing and every rejection; the formula on a base and on a higher-timeframe operand; anchor fixed at the
  entry bar; entry bar itself (`change = 0`); non-finite anchor; non-finite current value; all four operators; both sides;
  historical (offset 0) and live (offset 1) starts.
- Parity: single-trade evaluation and the reference consumer of the projection give identical (bar, `rule_id`, `path_id`)
  transitions on a corpus of entries, for `require` and for mixed `at_least`.
- Invariants: specs without the atom keep `plan_hash`, plan labels, node identities, compute counts and the serialized
  projection unchanged.
- Gate: ruff, mypy, the full suite, `openspec validate entry-anchored-change-v1 --strict`.
