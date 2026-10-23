## Why

Vote **W8 variant 6** for EMA200 (owner, 2026-10-23: «создать все новые компоненты, которые участвуют в нашем голосовании») has two
voters that read only candles:

- **D1v**: today's D1 (already in the Engine as `forming_candle 1d`), but only when **yesterday's** UTC day had a body of at least
  1 daily ATR our way and closed in the top 15% of its range (otherwise the voter is silent).
- **Wk**: the body of the **previous UTC week** (weeks start Monday 00:00), our way, in weekly ATR.

Both need the last **completed** candle of a higher timeframe, which no operand gives today.

## What Changes

- **New operand `completed_candle`** `{episode, timeframe, field, atr}`, `field` one of:
  - `body`: `g · (close − open) / ATR`, the ATR being the Wilder ATR of the candle **before** the completed one;
  - `close_position`: `(close − low) / (high − low)` on the long side, `(high − close) / (high − low)` on the short side.
  Missing without a valid wave of the current touch, before the first completed candle, or without a positive ATR / range.
- **Weekly candles start on Monday 00:00 UTC** (exchange weekly candles): the `1w` feature timeframe used to bin from Sunday.
  No config uses `1w` today. The completed candle is aligned by a fixed duration instead of an anchored pandas offset.
- The Engine holds no threshold: D1v's condition (`body ≥ 1`, `close_position ≥ 0.85`) and the weights live in the vote config
  (OpenSpec of the W8 vote module, separate).
- **Cost**: O(bars), vectorised; a spec without the operand pays nothing.

Not in this change: the open interest and premium voters (need new market data), the curve weight of the W8 vote, catalog and
manifest bindings, deploy.
