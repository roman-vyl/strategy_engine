## 1. Feature

- [ ] 1.1 `rolling_sum {source, period, lag}`: validation (period ≥ 1, lag ≥ 0, no other parameter, source any bar field), label, identity, warm-up (`period + lag`). Verify: tests.
- [ ] 1.2 Values equal the loop sum over `[i − lag − period + 1, i − lag]`, missing until `period` finite values; higher timeframe aligned as last completed candle. Verify: tests.

## 2. vol1h

- [ ] 2.1 The vol1h composition through the pipeline on the BTC fixture equals the loop. Verify: e2e test.

## 3. Parity with research (cloud)

- [ ] 3.1 vol1h on every bar and on all EMA200 entries of BTC, ETH and SOL against `vol1h_bars`. Report in `/mnt/project-files/engine-tasks/ema200/parity_vol1h/`.

## 4. Gate

- [ ] 4.1 ruff, mypy, affected tests; never `tests/parity/test_all_families_memo.py`.
- [ ] 4.2 `openspec validate vol1h-rolling-sum-v1 --strict`.
