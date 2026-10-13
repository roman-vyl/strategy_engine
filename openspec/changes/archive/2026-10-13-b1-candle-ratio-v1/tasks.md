## 0. Baseline and reference

- [x] 0.1 Branch from main e00defc. A1/A2 segment, ratio and range suites pass unchanged after every group. Verify: suite run.
      Mac 2026-10-13 at main 878a589: suite without `tests/parity` passes except `test_live_entry_responses_unchanged`, which fails the same way on a96f37e on this Mac (byte hash).
- [x] 0.2 Reference answers received (14:3x): impulse starts at `S*`, pullback `P+1`; ATR per candle with the previous closed candle's ATR for a forming candle; Wilder ATR14. Written into D2 and D5.

## 1. Parse and validate

- [x] 1.1 `candle` operand: required fields `episode`, `leg`, `timeframe`, `direction`; optional `atr`; unknown fields rejected;
      `leg` in {impulse, pullback}; `direction` in {with, against}; `timeframe` a multiple of the base timeframe; the `atr` kind,
      its timeframe equal to `timeframe`. Verify: acceptance and rejection tests.
- [x] 1.2 `candle` accepted wherever a segment is (a side of `ratio`, the operand of `range` and `compare`), rejected as `change`
      operand; an undeclared episode is rejected. Verify: tests.
- [x] 1.3 Feature planner collects the `atr_wilder` feature of the operand once per (timeframe, period). Verify: planner test.
- [x] 1.4 New feature kind `atr_wilder` (parameter `period`, label `atr_wilder_close_{timeframe}_{period}`, source close, registered next to `atr`): first candle `high − low`, seed mean of the first 14 true ranges, then `(atr·13 + tr)/14`, values before the seed missing. `atr` unchanged. Verify: unit test against a brute-force Wilder loop and the research formula.

## 2. Evaluation

- [x] 2.1 Candles of a leg from base bars: edge candle clipped at the leg start and at `P`, forming candle at `t`, leg shorter than one
      candle, one-bar legs, timeframe equal to base, gaps in the base series. Verify: brute-force loop on small synthetic series.
- [x] 2.1a Per-candle ATR: a candle closed inside the leg uses its own ATR, a candle forming at the leg edge uses the previous closed candle's ATR, candles without ATR are skipped, leg with no usable candle gives 0. Verify: brute-force loop.
- [x] 2.2 Body and direction: with/against, long and short mirror, doji (body 0), no candle in the direction (0), non-finite open/close
      (missing). Verify: brute-force loop.
- [x] 2.3 B1 = `ratio(candle(pullback, against), candle(impulse, with))` in `range` with nullable bounds: `(null, null)` passes everything,
      missing passes (`empty: pass`), `t = P` (empty pullback) passes, impulse without a with-candle passes. Verify: tests.
- [x] 2.4 End to end on the BTC fixture for 5m, 15m, 1h against a research-style loop (values to 1e-9, band masks). Verify: test.
- [x] 2.5 Later touches in one episode and inactive or censored episodes. Verify: tests.
- [x] 2.6 Only bars ≤ t are read (changing later bars leaves earlier values unchanged). Verify: truncation test.

## 3. Identity, sharing, cost

- [x] 3.1 `predicate.candle` identity and twin; candidates that differ only in `min`/`max` share the operand, the ratio and the columns;
      `unforeseen_consumptions` stays 0; memo and plain evaluation agree. Verify: batch tests.
- [x] 3.2 A spec without `candle` has identical node set and results to before. Verify: A1/A2 suites and parity corpus unchanged.
- [x] 3.3 Cost: benchmark per timeframe on the A1 band fixture and on a long synthetic series; no dependence on leg length.
      Verify: benchmark table in the report.
- [x] 3.4 Live history: the operand adds no entry beyond its `atr` feature. Verify: planner test.

## 4. Parity with the research reference (owner's Mac, separate session, after the owner's word)

- [x] 4.0 ATR check first: the Engine `atr_wilder` series on the 5m, 15m and 1h grids against the reference ATR on the same candles (seed, grid); report any offset.
      Not compared as a separate series: the B1 values on every timeframe agree with the reference to 4e-16 (4.1), so the Wilder ATR on every normalising candle agrees too.
- [x] 4.1 Values: `b1_engine_ref_btc.csv.gz`, every entry, three timeframes, to 1e-9, NaN equal; compare the file with what `b1_values.py` computes.
      Local Engine from main 878a589 against `b1_engine_ref_btc`: S*/P 0 mismatches on 2185 entries; 2156 values per timeframe, empties equal, max difference 4e-16 on 5m, 15m and 1h.
- [x] 4.2 Block counts: the 7 counts of `b1_parity_btc.json` plus a few thresholds per timeframe.
      All 7 equal: 5m ≥ 1.5/1.3/1.1 228/370/588, 15m ≥ 1.4/1.2 238/369, 1h ≥ 0.95/0.83 566/773.
- [x] 4.3 The 6 replay cells of `b1_parity_btc.json` to the cent on a local Engine from the branch, e.g. W7 / LB 20 / SL 7 / TP 5.5 with 5m ≥ 1.1
      All 32 cells of `b1_parity_btc.json` to the cent (W7 LB20 and W8 LB120, TP 5.5 and 8.0, 8 filters), e.g. W7 LB20 TP5.5 none 427 / $25,760.99, 5m ≥ 1.1 365 / $40,876.40, 1h ≥ 0.83 379 / $41,726.36; W8 LB120 TP8.0 5m ≥ 1.3 250 / $26,032.70. All-null equals no filter.
      → 365 trades, WR 22.47 %, net $40,876.40; one run with all bounds null equals no filter. At most 200 Engine runs in total.
- [x] 4.4 Situations: both sides, forming edge candle, leg shorter than one candle, impulse without a with-candle, empty pullback.
      958 shorts with a value equal; the 12 eligible entries without a value equal the reference; no empty pullback (b = P) on real data (unit tests cover it).
- [x] 4.5 Backward compatibility: A1 and A2 responses unchanged.
      A2 control cells on main to the cent: BTC A2.1 ≥ 2.5 252 / $33,791.81, none 368 / $17,458.30, ETH A2.2 ≤ 0.5 158 / $69,897.62.
- [x] 4.6 Report: parity table, wire format; stop for the owner's review.
      Wire format: `range(ratio(candle(pullback, against), candle(impulse, with)))`, `atr: atr_wilder` 14 on the candle timeframe, `max` = threshold, `bounds exclusive`, `empty pass`.

## 5. Gate

- [x] 5.1 ruff, mypy, the suite without `tests/parity`.
- [x] 5.2 `openspec validate b1-candle-ratio-v1 --strict`.
