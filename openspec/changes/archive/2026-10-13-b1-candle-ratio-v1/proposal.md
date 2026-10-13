## Why

Research metric **B1 "pullback candle against impulse candle"** found the cleanest "almost only stop-loss" zone of the B group
(group B: strength of the rising half-wave). The strongest body against the trade on the pullback, relative to the strongest body
with the trade on the impulse, says whether the seller came back with the force of the buyer. Cut from above on BTC EMA500
(W7 / LB 20 / SL 7 / TP 5.5, 427 trades, 339 stops): the trades cut at 5m ≥ 1.3–1.5, 15m ≥ 1.4–1.6 and 1h ≥ 0.95–1.0 are 91–97 %
stop-losses; the single filter 5m ≥ 1.1 gives 365 trades, WR 22.5 %, net about $40.9k (no filter about $25.8k).

The owner wants B1 as an Engine component read on the same two legs as A1 and A2: the left leg (impulse) and the right leg
(pullback) of the current touch of the EMA-stack episode. The weighted vote over components is a later step and a separate change.

## What Changes

Everything builds on the A1/A2 blocks (`ratio`, `range` with nullable bounds, the EMA-stack episode, archived as
`a1-band-filter-v1` and `a2-shape-aggregates-v1`). No new indicator kind and no new predicate class.

- **One new operand, `candle`**: the largest body of a given direction among higher-timeframe candles assembled from the base 5m
  bars inside one leg of the current touch, divided by that timeframe's ATR.
  - Timeframe `5m`, `15m` or `1h` (any multiple of the base timeframe).
  - Candles are built from the base bars of the leg only, so the candles at the edges of the leg are clipped to the leg.
  - A candle that is still forming at the current bar is taken as it is at that bar (updated every base bar, not on close).
  - Direction `with` or `against` the trade; the short side mirrors it.
- **B1 as a block**: `ratio(candle(pullback, against), candle(impulse, with))` inside a `range` with nullable bounds, `bounds`
  `exclusive`, `empty: pass`; one threshold per timeframe, held by the Research manifest, not by the Engine.
- **ATR per candle** (reference, settled): every candle is divided by the ATR14 of its own timeframe at that candle. A candle that
  closes inside the leg uses its own ATR; a candle still forming at the leg edge uses the ATR of the previous, last closed candle.
  The operand is the maximum over candles of `body ÷ ATR`, in both legs, so ATR does not cancel in B1.
- **Wilder ATR feature**: the reference ATR is Wilder (seed = mean of the first 14 true ranges, then `(atr·13 + tr) / 14`), while
  Engine's `atr` feature is a simple rolling mean of the true range. The change adds a feature kind `atr_wilder` (same period
  parameter, any timeframe); `atr` is untouched.
- The pullback of B1 starts at `P+1` (the peak bar belongs to the impulse). A1/A2 pullbacks start at `P`; the `candle` operand
  therefore has its own two legs and does not reuse the segment's `from`/`to` pairs.
- **Cost**: O(n) per series by running maxima per candle, independent of leg length; a spec without a `candle` operand pays
  nothing. The live history requirement stays zero-additional on top of the ATR feature the spec already declares.

Not in this change: the vote over timeframes (the owner's weights combine the three timeframes by MAX, Step 2), the catalog and
manifest bindings, research surfaces, deploy.
