## 1. Features

- [x] 1.1 `candle_body_atr {period}` and `candle_close_position` as feature kinds: contract, validator, range evaluator branch, identity, public order. Verify: `tests/test_htf_candle_shape.py`, registry and catalog tests.
- [x] 1.2 Values on 1d and 1w equal a loop written like the research reference; strong-yesterday example; flat candle missing; malformed requests rejected. Verify: tests.
- [x] 1.3 Weekly candles start on Monday and align from the next Monday. Verify: test.
- [x] 1.4 Live warm-up: body = `atr_wilder` + 1 candle, close position = 1 candle. Verify: test.

## 2. Parity with research on EMA200 (cloud)

- [x] 2.1 Yesterday's body and close position (1d), previous week's body (1w), signed by side as research, and D1v composed as research (`body ≥ 1 and close_position ≥ 0.85`, else 9) on all research entries of BTC, ETH, SOL, 1e-9 relative. Report in `/mnt/project-files/engine-tasks/ema200/parity_cc/`.
  Result: equal on every entry. Body BTC 2811 / ETH 2530 / SOL 2223 (max relative 0), close position 2824 / 2542 / 2232 (max relative 1.3e-15, short side as `1 − x`), Wk 2713 / 2386 / 2113 (0), D1v 2811 / 2528 / 2223 (0); D1v ≤ −0.2 cuts 86 / 96 / 65 in both. Engine run 40-52 s per coin.

## 3. Gate

- [x] 3.1 ruff, mypy, the whole suite except `tests/parity/test_all_families_memo.py` (never run): the only failures are the 51 parity golden tests that fail on main too, and the local egg-info check; the indicator contract baseline is updated for the two kinds.
- [x] 3.2 `openspec validate htf-candle-shape-v1 --strict`.
