## 0. Baseline

- [x] 0.1 Branch from main 42d8bad. Targeted tests only (`PYTHONPATH=src:.:tests`), never `tests/parity/test_all_families_memo.py`.

## 1. Accept the field

- [x] 1.1 `CandlePayload`: optional `open_interest` (strict text or `null`, default absent); `extra="forbid"` stays on the candle and on the range envelope. Verify: tests.
- [x] 1.2 `load_range`: a present non-null value must be finite decimal text, otherwise `upstream_contract_error` for the whole response; the value is not stored on `MarketBar` and not passed on. Verify: tests.

## 2. Tests (`tests/test_mds_client.py`)

- [x] 2.1 `/v1/candles` and `/v1/historical-candles` responses with OI as text, `null` and absent (mixed in one range) give the same `MarketFrame` (bars and `market_data_hash`) as the response without OI.
- [x] 2.2 OI as a JSON number, boolean, object, `"abc"`, `"NaN"` or `"Infinity"` is rejected as `upstream_contract_error`.
- [x] 2.3 Another unknown candle field (for example `turnover`) is still rejected.
- [x] 2.4 Existing MDS client, live acquisition and historical read tests pass unchanged (26 related files, 383 passed).

## 3. Verify

- [x] 3.1 Lint/type checks as in CI; `openspec validate engine-mds-candle-open-interest-input-v1 --strict`.
