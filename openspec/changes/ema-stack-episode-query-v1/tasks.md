## 1. Shared parameters

- [x] 1.1 Extract `parse_episode_params` from `parse_episode_section`; the section parser adds only the `anchor_stack` and `history_bars` defaults
- [x] 1.2 `episode_params_by_ref` in the feature plan wire (only when episodes are declared); no-regression test on plan and `plan_hash`

- [x] 1.3 Market data contract checked on the owner's Mac (`market_data_service`, `consumer_read/provenance.py`): `market_data_hash` is sha256 of ticker, timeframe, `from`, `to` and every candle's open time and OHLCV in the range, so any correction inside the range changes it; the range bounds are part of the hash; `/v1/historical-candles` rejects a mismatching `expected_market_data_hash`

## 2. History

- [x] 2.1 Request model and validation (`market`, `episode`, `side`, `page`, `expected_market_data_hash`)
- [x] 2.2 Whole committed history from market-data bounds; EMAs through the indicator range evaluation; projection through `project_side`
- [x] 2.3 Bounded in-memory LRU keyed by market and parameters, both sides in one entry; entry version = bounds + `market_data_hash` + load time; revalidation after `STRATEGY_ENGINE_EPISODE_HISTORY_REVALIDATE_SECONDS` (default 300); single compute for concurrent misses
- [x] 2.3a Pinned version: `expected_market_data_hash` mismatch on a valid entry gives 409 `market_data_version_changed` at once, without a candle read; an expired entry is revalidated first
- [x] 2.4 Pages of whole finished episodes, current episode, identity fields
- [x] 2.5 Route `POST /v1/ema-stack-episodes/history`

## 3. Tests

- [x] 3.1 Equality with diagnostics episode tables for the same parameters over the same history, both sides
- [x] 3.2 Paging covers the history once with stable touch numbers; current episode and refresh after a new candle
- [x] 3.3 Cache: one compute for two pages and for concurrent requests; a new candle recomputes
- [x] 3.3a Repaired historical candle with unchanged bounds: recomputed after revalidation; unchanged hash after revalidation does not recompute
- [x] 3.3b Pinned pages: all pages with the first hash succeed; a history change between pages gives 409 and no page; a wrong pin on a valid entry gives 409 with no extra read; a pin on an expired entry is checked after revalidation
- [x] 3.4 Parameter errors equal to the strategy section; determinism and identity
- [ ] 3.5 Time and size of the full BTCUSDT.P 5m history, reported

## 4. Parity and gate

- [ ] 4.1 HTTP parity with `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m, both sides (owner's Mac)
- [x] 4.2 ruff, mypy, full suite without `tests/parity`, `openspec validate ema-stack-episode-query-v1 --strict`
