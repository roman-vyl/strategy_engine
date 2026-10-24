## Status

DRAFT for the owner's decision. No code until the owner's word: the market data it needs does not reach the Engine yet.

## Why

Vote **W8 variant 6** for EMA200 has 12 voters. Two read candles only (D1v, Wk: OpenSpec `htf-candle-shape-v1`). The other ten read
market data the Engine never receives today:

- **open interest (OI), Bybit, 15-minute series**: W8_30, W8_14, W8r, W8p, O1, kI, W1r, W1d, W2d;
- **premium index, Bybit, 5-minute kline**: PS_R.

The Engine reads only OHLCV candles from MDS (`MarketFrame`); MDS stores and streams only candles.

## What Changes (proposed)

1. **Market series input.** The evaluation MAY read named extra series next to the candles:
   `open_interest` (15m points) and `premium_index` (5m closes), each as `(time_ms, value)` pairs. A spec that reads none of them
   needs none; a spec that reads one fails closed without it.
2. **As-of alignment to base bars** (no look-ahead):
   - OI: at the close of 5m bar `x` the value is the last OI point whose 15-minute bucket has closed (`ts + 15m ≤ x + 5m`).
   - premium: the premium bar with the same open as the candle, not older than 15 minutes.
3. **Atomic operands** over the aligned series and the wave points `S*` (impulse start), `P` (peak), `t` (entry), `g` side sign:
   - `series_window_share {series, window_days, at: t|P}`: value at `t` (or `P`) ÷ max over the last `window_days` (W8_30, W8_14,
     W8p); `series_window_rank`: (value − min) ÷ (max − min) (W8r). Missing until a full window of history.
   - `series_leg_change {series, leg: impulse|pullback|previous_impulse}`: `100 · (value at leg end ÷ value at leg start − 1)`
     (O1 = impulse `S*→P`, O2 = pullback `P→t`, O1p = previous impulse).
   - `series_leg_mean {series, leg: pullback, scale}`: mean of `g · premium` in bp over `P..t` ÷ a per-coin constant from config
     (PS_R; research scale = robust std of 5m premium: BTC 2.706, ETH 2.653, SOL 3.501).
   - Derived voters by existing composition: kI = `ratio(O1, |price change % S*→P|)`; kR = `ratio(O2, |price change % P→t|)`;
     W1r = `ratio(kR, kI)` only when kI > 0; W1d = kR − kI; W2d = O1 − O1p. The Engine has `ratio` but no difference and no nested
     ratio, so this change adds a `difference` operand and allows one level of nesting, or adds `kI`/`kR` as operands (to decide
     in design).
4. **Reading the series.** The Engine reads its candles from MDS itself (`adapters/market_data_service/client.py`), in live and in
   research runs; Research Service and Runtime do not pass candles. The Engine's MDS client SHALL read the new series the same way,
   from the MDS contract drafted in market_data_service (branch `claude/project-thread-vt9bk5`, OpenSpec
   `mds-open-interest-premium-series-v1`): `GET /v1/series?ticker=&series=open_interest_15m|premium_index_5m&from_ms=&to_ms=` and
   `GET /v1/series-streams/{ticker}/{series}/bounds`. An OI point is stamped with the start of its 15-minute bucket, a premium point
   with the open of its 5m bar; the as-of rule above stays in the Engine. Storing and downloading the series is MDS work, in its own
   thread.

## Research references

`/mnt/project-files/ema200_calib/review/`: `oi/w8/var/w8var.py` (W8_30, W8_14, W8r), `oi/w8/w8.py` (W8p), `oi/oi_filters.py` (O1, O2),
`oi/w1/w1.py` (kI, W1r, W1d), `oi/w2/w2.py` (W2d), `oi/premium/p2deep.py` key R (PS_R). Values per entry for parity are saved next to
them. The OI csv files used by research are on the Mac (`BBB_data/research/market_meta/`) and must be copied to
`/mnt/project-files/` before the parity check; the premium files are already in `/mnt/project-files/ema200_calib/market_meta_premium/`.

## Not in this change

The W8 vote weights (curve weight, OpenSpec `w8-curve-weight-vote-v1`), catalog and manifest bindings, deploy.
