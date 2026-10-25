## Why

Vote **W8 variant 6** for EMA200 has two voters that read only higher-timeframe candles:

- **D1v**: today's D1 (already in the Engine as `forming_candle 1d`), counted only when **yesterday's** UTC day had a body of at
  least 1 daily ATR our way and closed in the top 15% of its range.
- **Wk**: the body of the **previous week** (Monday 00:00 UTC to Monday), our way, in weekly ATR.

The owner (2026-10-24): these are ordinary higher-timeframe components and must be built as such, like any other HTF feature.

## What Changes

- **Two indicator kinds** on any feature timeframe, computed on that timeframe's own candles and seen by the base bars as the value
  of the last completed candle (the existing HTF path: candles aggregated from the base candles the Engine reads from MDS, then
  `align_completed_to_base`):
  - `candle_body_atr {period}`: `(close − open) / atr_wilder(period)` of the **previous** candle;
  - `candle_close_position`: `(close − low) / (high − low)`.
- **Weekly candles start on Monday 00:00 UTC**, as exchange weekly candles: the `1w` timeframe used to bin from Sunday. No config
  uses `1w` today. The completed candle is aligned by a fixed duration instead of an anchored pandas offset.
- Live warm-up: `candle_body_atr` as `atr_wilder` plus one candle; `candle_close_position` one candle.
- The side and the thresholds live in the vote config (long `body ≥ 1`, short `body ≤ −1`; long `close_position ≥ 0.85`, short
  `≤ 0.15`), not in the Engine.

Not in this change: the gate that makes D1v vote only after a strong yesterday, and the curve weights (vote module, separate
OpenSpec); the open interest and premium voters; catalog and manifest bindings; deploy.
