## Context

`pre-entry-predicates-v1` defines a boolean layer over canonical features. `compare` and `range` read the current bar;
`temporal` (`held_for`, `within`) looks back over a window of booleans in base bars. There is no class that looks back over a
feature's value. Predicates are consumed by `composite_setup` and by `composite_phase_condition` through the same
`parse_predicate`, `evaluate_predicate` and `resolve_predicate` functions (`strategies/ema_pullback/predicates.py`).
The live history planner (`live_calculation_requirements._predicate_history`) fails closed on a predicate class it does not know.

## Decisions

### D1. A class of the predicate layer, not an atom

`change` is a market series: a boolean per base bar from one feature column, with no trade state. It therefore needs no new
consumer, wire field or projection change; every existing consumer of predicates inherits it.

### D2. Lookback in bars of the operand's timeframe

Both compared values are points of one series, so the second point is `lookback` whole bars of that series back. For a base
feature that is `lookback` base bars. For a feature on timeframe T with `k = T / base` (integral, as for any higher-timeframe
operand), the value at base bar `i` is the value of completed bar `j(i)`, and the second point is the value of bar `j(i) - lookback`,
which equals the aligned column at base bar `i - lookback * k`. The predicate therefore reads a shifted copy of the aligned column
and performs no alignment of its own, as the layer requires. The shift is exact because every bucket boundary lies on the
base grid.

### D3. Operators and value

`>`, `>=`, `<`, `<=` against a finite constant, the set `compare` already uses. Equality stays rejected. One operand only: the class
is not an arithmetic expression language, so the layer's rejection of arithmetic expressions stands.

### D4. Side

Side-free by default. The existing explicit `short` override is extended to `change` and may replace `op` and `value`; it may not
replace `operand` or `lookback`, because the shifted column is the identity of the node's input. No automatic inversion.

### D5. Non-finite

False when either point is missing or non-finite, including the first `lookback * k` base bars of a frame. No negation exists, so a
not-ready operand can never make the predicate true.

### D6. History planning owner

The owner of predicate history is the live history planner (`live-calculation-window-planning`). The feature plan only lists
features and carries no history rule, so it is not changed. For `change`, the planner adds `lookback` bars of the operand's
timeframe as an additional requirement on top of the feature's own warm-up (already counted per feature), converted to base bars by
the existing timeframe-aware conversion. Under `held_for`/`within` it adds the window's `bars - 1` base bars on top, as for any inner
predicate. Range and batch evaluation take their frame from the caller: the Engine does not extend it and the predicate is False
where its second point falls before the frame.

### D7. Identity

A new node family `predicate.change` with params `{op, value, lookback}` (and the side only when a `short` override exists),
upstream the column node of the operand. Labels never enter identity. Existing node identities are unchanged.

## Alternatives not taken

- A per-trade "change since entry" atom: needs per-trade state and a contract change in the projection and in consumers.
- Arithmetic operands in `compare`: opens the layer to an expression language the spec rejects.
- Lookback in base bars for a higher-timeframe operand: mixes two clocks and makes a one-bar change on a higher timeframe
  unexpressible without knowing the timeframe ratio.
