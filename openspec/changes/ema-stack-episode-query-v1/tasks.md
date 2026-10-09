## 1. Shared parameters

- [ ] 1.1 Extract `parse_episode_params` from `parse_episode_section`; the section parser adds only the `anchor_stack` and `history_bars` defaults
- [ ] 1.2 `episode_params_by_ref` in the feature plan wire (only when episodes are declared); no-regression test on plan and `plan_hash`

## 2. History

- [ ] 2.1 Request model and validation (`market`, `episode`, `side`, `page`, `expected_market_data_hash`)
- [ ] 2.2 Whole committed history from market-data bounds; EMAs through the indicator range evaluation; projection through `project_side`
- [ ] 2.3 Bounded in-memory LRU keyed by market, parameters, side and the latest committed candle; single compute for concurrent misses
- [ ] 2.4 Pages of whole finished episodes, current episode, identity fields
- [ ] 2.5 Route `POST /v1/ema-stack-episodes/history`

## 3. Tests

- [ ] 3.1 Equality with diagnostics episode tables for the same parameters over the same history, both sides
- [ ] 3.2 Paging covers the history once with stable touch numbers; current episode and refresh after a new candle
- [ ] 3.3 Cache: one compute for two pages and for concurrent requests; a new candle recomputes
- [ ] 3.4 Parameter errors equal to the strategy section; determinism and identity
- [ ] 3.5 Time and size of the full BTCUSDT.P 5m history, reported

## 4. Parity and gate

- [ ] 4.1 HTTP parity with `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m, both sides (owner's Mac)
- [ ] 4.2 ruff, mypy, full suite without `tests/parity`, `openspec validate ema-stack-episode-query-v1 --strict`
