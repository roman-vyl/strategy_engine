## 0. Baseline

- [x] 0.1 Branch from main dd1ce62. Targeted tests only (`PYTHONPATH=src:.:tests`), never `tests/parity/test_all_families_memo.py`.

## 1. Market bar and client

- [x] 1.1 `MarketBar.open_interest: Decimal | None = None` (default keeps existing constructions valid). Verify: mypy, tests.
- [x] 1.2 `load_range` puts `parse_decimal_text(candle.open_interest)` on the bar (`None` for null or absent); a malformed value is still `upstream_contract_error`. Verify: `tests/test_mds_client.py`, both endpoints.

## 2. Shared arrays

- [x] 2.1 `MarketArrays.values("open_interest")` / `array("open_interest")`: float per bar, NaN for `None`, lazy and cached like OHLCV; `OHLCV_FIELDS`, `ohlcv_columns()`, `dataframe()` unchanged; unknown fields still `KeyError`. Verify: unit tests (gaps, all-None, cache identity, read-only).

## 3. No regression

- [x] 3.1 Every case of the parity corpus (real, synthetic, probe) recorded on the fixture with and without OI gives identical records (`tests/test_open_interest_market_field.py`, self-comparison, no goldens).
- [x] 3.2 60 related test files (MDS client, live, historical, batch, market arrays, predicates, vote) pass, rc 0.

## 4. Verify

- [x] 4.1 ruff, mypy, release check; `openspec validate engine-open-interest-market-field-v1 --strict`.
