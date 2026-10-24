## Status

DRAFT for the owner's decision. No code until the owner's word: the market data it needs does not reach the Engine yet.

## Why

Vote **W8 variant 6** for EMA200 has 12 voters. Two read candles only (D1v, Wk: OpenSpec `htf-candle-shape-v1`). The other ten read
market data the Engine never receives today:

- **open interest (OI), Bybit, 15-minute series**: W8_30, W8_14, W8r, W8p, O1, kI, W1r, W1d, W2d;
- **premium index, Bybit, 5-minute kline**: PS_R.

The Engine reads only OHLCV candles from MDS (`MarketFrame`); MDS stores and streams only candles.

## What Changes (proposed)

1. **Market data input (MDS contract, owner 2026-10-24 08:01).** No separate series endpoint: MDS stores OI and premium in the 5m
   candle row next to `volume`: `open_interest` (Bybit OI, `intervalTime=5min`, at the bar open) and `premium_close` (close of the
   5m premium bar with the same open), served by `/v1/candles` and `/v1/historical-candles`, `null` when not loaded;
   `market_data_hash` stays OHLCV-only, an `extras_hash` covers the two fields. Draft: market_data_service branch
   `claude/project-thread-vt9bk5` (95f8944), OpenSpec `mds-candle-open-interest-premium-v1`. The Engine's market frame and MDS client
   SHALL carry the two optional fields; a spec that reads none of them needs none, a spec that reads one fails closed without it.
2. **Timing.** The fields are written right after the candle commit, so live the Engine SHALL briefly wait/re-read when the last bar
   has no fields yet. Research used 15m OI with an as-of lag (`ts + 15m ≤ x + 5m`); the MDS thread checks that the 5m values equal the
   research 15m points at :00/:15/:30/:45 before the as-of rule for the Engine is fixed.
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
## Research references

`/mnt/project-files/ema200_calib/review/`: `oi/w8/var/w8var.py` (W8_30, W8_14, W8r), `oi/w8/w8.py` (W8p), `oi/oi_filters.py` (O1, O2),
`oi/w1/w1.py` (kI, W1r, W1d), `oi/w2/w2.py` (W2d), `oi/premium/p2deep.py` key R (PS_R). Values per entry for parity are saved next to
them. The OI csv files used by research are on the Mac (`BBB_data/research/market_meta/`) and must be copied to
`/mnt/project-files/` before the parity check; the premium files are already in `/mnt/project-files/ema200_calib/market_meta_premium/`.

## Not in this change

The W8 vote weights (curve weight, OpenSpec `w8-curve-weight-vote-v1`), catalog and manifest bindings, deploy.
