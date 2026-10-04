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
  `operand(j) - operand(j - lookback) <op> value`, where `j` is the last completed bar of the operand's own timeframe at that base
  bar, `operand` is a feature reference, `lookback` is a positive integer number of **bars of the operand's timeframe**
  (for a base-timeframe feature, base bars), `op` is one of `>=` `>` `<=` `<` (the same comparison set as `compare`;
  `==` and `!=` stay rejected), and `value` is a finite constant.
  - Both values come from one time series, so the two points are always whole bars of that series (no mixing of base and
    higher-timeframe clocks). Higher timeframes use the last completed bar, no look-ahead.
  - Missing or non-finite operand at `j` or at `j - lookback` (warm-up, history start): False.
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

The trigger is now "ADX(tf) rose by at least `delta` over the last `lookback` bars of that timeframe, and DI is aligned with the trade", which is
**not** the same signal as the signed-ADX-since-entry replay (surface 4). A new replay of this exact rule is needed (a new surface
of its own); surface 4 stays what it is, replay-only. Strict DI alignment (`plus > minus`, ties not aligned) is the Engine's existing
rule, so the tie question disappears.

## Verification

- Unit: the lag arithmetic, lookback in bars of a higher-timeframe feature (and in base bars for a base feature), all four operators, warm-up, history start, non-finite, `short` override,
  `held_for` / `within` around it, composite path with `adx_di_threshold`.
- Gate: ruff, mypy, full suite, `openspec validate predicate-change-class-v1 --strict`.
- Parity with the research replay of the same rule: 20-30 cells run in the Engine must match the replay table in trade count and net PnL.

## Decisions taken in review

- Name: `predicate-change-class-v1` (neutral, not tied to ADX or to one strategy).
- `lookback` counts bars of the feature's own timeframe, because the two compared values are points of one series.
- All four ordering operators, the same set as `compare`.
- Surface 4 (signed ADX since entry) stays a separate historical replay experiment and is not renamed. The new rule gets its own
  fifth surface: replay research first, then selected points in the real Engine with a parity check.
