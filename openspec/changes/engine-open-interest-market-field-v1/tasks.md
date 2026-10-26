## 0. Baseline

- [ ] 0.1 Branch from main dd1ce62. Targeted tests only (`PYTHONPATH=src:.:tests`), never `tests/parity/test_all_families_memo.py`.

## 1. Market bar and client

- [ ] 1.1 `MarketBar.open_interest: Decimal | None = None` (default keeps existing constructions valid). Verify: mypy, tests.
- [ ] 1.2 `load_range` puts `parse_decimal_text(candle.open_interest)` on the bar (`None` for null or absent); a malformed value is still `upstream_contract_error`. Verify: `tests/test_mds_client.py`, both endpoints.

## 2. Shared arrays

- [ ] 2.1 `MarketArrays.values("open_interest")` / `array("open_interest")`: float per bar, NaN for `None`, lazy and cached like OHLCV; `OHLCV_FIELDS`, `ohlcv_columns()`, `dataframe()` unchanged; unknown fields still `KeyError`. Verify: unit tests (gaps, all-None, cache identity, read-only).

## 3. No regression

- [ ] 3.1 The same strategy specs (EMA pullback with vote B components, managed replay, live entry) on bars with and without OI give identical results. Verify: tests.
- [ ] 3.2 Existing MDS client, live acquisition, historical, batch and predicate test files pass unchanged.

## 4. Verify

- [ ] 4.1 ruff, mypy, release check; `openspec validate engine-open-interest-market-field-v1 --strict`.
