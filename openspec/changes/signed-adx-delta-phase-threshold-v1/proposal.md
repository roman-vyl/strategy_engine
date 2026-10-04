## Why

Research needs a trailing-stop trigger of the kind "the trend strength is rising in the trade direction". The Engine can only
test a level (`adx_di_threshold`: ADX at or above N, with DI aligned to the side). It cannot test a *change* of a feature.

The first design (an entry-relative `signed_adx_delta` phase atom) was rejected in review: it needs per-trade state (entry
reference, running maximum, side) that the `HistoricalManagedProjection` and the Research consumers cannot carry without a
wire-contract change in two services.

This design avoids per-trade state completely. The change is a market-only series, so it fits the existing predicate layer,
which already feeds composite phase conditions, the projection and both Research consumers.

## What Changes

- One new predicate class `change` in the pre-entry predicate layer:
  `change {operand, lookback, op, value}` is True on a base bar when
  `operand(t) - operand(t - lookback) <op> value`, with `operand` a feature reference, `lookback` a positive number of
  **base bars**, `op` one of `>=` `>` `<=` `<`, and `value` a finite constant.
  - The operand is the value the other predicates see (higher timeframes: last completed bar, no look-ahead).
  - Missing or non-finite operand at `t` or at `t - lookback` (warm-up, history start): False.
  - Side-free, with the existing explicit `short` override (no automatic inversion).
- Nothing else. The scheme is composed from existing parts as a composite phase condition path:
  `require: [adx_rising, di_aligned]` with `adx_rising = change{adx(1h,14), lookback, >=, delta}` and
  `di_aligned = adx_di_threshold{timeframe, period, adx_threshold: 0, require_di_alignment: true}`; then
  `to_phase: runner` and `initial_r_trailing_stop` activated at `phase_at_least: runner`, as in the confirmed ADX state runs.
- No projection change (a predicate child is a market series), no Research Service change, no per-trade state, no new indicator,
  no change for specs that do not use `change`. `/managed-replay` and the single-trade path inherit it because predicate children already work there.

## Impact

- `pre-entry-predicates-v1`: ADDED requirement `change` class (and its scenarios); the "any other class is rejected" list gains one entry.
- `ema-pullback-composite-phase-condition-v1`: no text change (predicate children already allowed).
- Research Service: no change. `scripts/experiments/fill_*_runs.py` gain a request builder (not a contract).

## Consequences for the research

The trigger is now "ADX(tf) rose by at least `delta` over the last `lookback` base bars, and DI is aligned with the trade", which is
**not** the same signal as the signed-ADX-since-entry replay (surface 4). A new replay of this exact rule is needed (a new surface
of its own); surface 4 stays what it is, replay-only. Strict DI alignment (`plus > minus`, ties not aligned) is the Engine's existing
rule, so the tie question disappears.

## Verification

- Unit: the lag arithmetic, base-bar lookback on a higher-timeframe feature, warm-up, history start, non-finite, `short` override,
  `held_for` / `within` around it, composite path with `adx_di_threshold`.
- Gate: ruff, mypy, full suite, `openspec validate signed-adx-delta-phase-threshold-v1 --strict`.
- Parity with the research replay of the same rule: 20-30 cells run in the Engine must match the replay table in trade count and net PnL.

## Open questions for review

1. Rename the change to `predicate-change-class-v1`?
2. `lookback` in base bars (proposed, matches `held_for`/`within` market-time windows) or in operand-timeframe bars?
3. Operators: only `>=` and `<=` (enough for the research) or all four?
