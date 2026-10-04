## Why

The predicate layer can compare a feature with a constant or with another feature at the same instant (`compare`, `range`,
`state`) and can look back over a window of booleans (`held_for`, `within`). It cannot ask how much a feature has moved over
a number of bars. A change of a feature over a short span is a basic building block that cannot be composed from the existing
classes, so it is added to the language once, generically, for every supported feature.

## What Changes

- One new predicate class `change {operand, lookback, op, value}`.
  - `operand`: a feature reference, resolved through the same canonical feature-kind contract as the other classes.
  - `lookback`: a positive integer number of bars of the operand's own timeframe.
  - `op`: one of `>=`, `>`, `<=`, `<` (the comparison set of `compare`; `==` and `!=` stay rejected).
  - `value`: a finite constant.
- Semantics. On a base bar, let `j` be the last completed bar of the operand's timeframe. The predicate is True iff
  `operand(j) - operand(j - lookback) <op> value`. Both values are points of one series, so the two points are always whole bars
  of that series. For a base-timeframe feature, bars are base bars. A higher timeframe uses its last completed bar, with no
  look-ahead.
- Non-finite values: if the operand is missing or non-finite at `j` or at `j - lookback` (indicator warm-up, start of history),
  the predicate is False. There is no negation.
- Side: side-free, with the existing explicit `short` override. No automatic side inversion.
- Composition: usable wherever a predicate is already allowed, and wrappable by the existing temporal classes (`held_for`,
  `within`) and by composite conditions, without any change to them.
- Planning and history: the operand is requested through the existing feature plan and is computed once per evaluation like any
  other feature. The history window needed before the first evaluated bar grows by `lookback` bars of the operand's timeframe,
  and the plan accounts for it so that results do not depend on where the evaluated range starts.
- Determinism: the same inputs give the same result.
- Nothing changes for specs that do not use `change`: no new indicator, no new wire field, no change in compute cost or output.

## Impact

- `pre-entry-predicates-v1`: ADDED requirement for the `change` class and its scenarios; the list of supported classes gains
  one entry; every class outside the list stays rejected.
- `ema-pullback-feature-plan-v1`: MODIFIED, history window for a `change` operand.

## Verification

- Unit tests: the lag arithmetic on a base-timeframe and on a higher-timeframe feature, all four operators, `lookback`
  validation, warm-up, start of history, non-finite values, `short` override, wrapping by `held_for` and `within`, determinism.
- History: evaluating a range that starts later gives the same values on the common bars.
- Gate: ruff, mypy, the full suite, `openspec validate predicate-change-class-v1 --strict`.
