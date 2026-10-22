## 1. Field

- [x] 1.1 `own_color_volume` accepted by `leg_sum`, rejected by `leg_mean`; identity of `volume` sums unchanged. Verify: tests.
- [x] 1.2 Series per side and leg against a brute-force loop: impulse with-trade candles, pullback counter candles, doji never, short mirror, non-finite open/close/volume missing. Verify: tests.
- [x] 1.3 Only bars ≤ t are read. Verify: truncation test.

## 2. V1.2

- [x] 2.1 Ratio through the pipeline on the BTC fixture equals the loop; a vote veto step blocks exactly the bars at or below its level. Verify: e2e test.
- [x] 2.2 Candidates differing only in a level share the operands. Verify: batch test.

## 3. Parity with research on EMA200 (cloud)

- [x] 3.1 V1.2 on all research entries of BTC, ETH, SOL against `v12` (1e-9 relative, NaN equal), entries at ≤ 0.0422 equal. Report in `/mnt/project-files/engine-tasks/ema200/parity_v12/`.

Parity result (cloud, 2026-10-22): every research entry with a value (BTC 2812, ETH 2526, SOL 2219) equals `v12` exactly; empties
equal; vetoes at ≤ 0.0422 BTC 11 / ETH 6 / SOL 3 in both.

## 4. Gate

- [x] 4.1 ruff, mypy, affected tests, never `tests/parity/test_all_families_memo.py`.
- [x] 4.2 `openspec validate v1-own-color-volume-ratio-v1 --strict`.
