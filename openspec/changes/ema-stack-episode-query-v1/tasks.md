## 1. Shared parameters

- [ ] 1.1 Extract `parse_episode_params` from `parse_episode_section`; the section parser adds only the `anchor_stack` defaults
- [ ] 1.2 `episode_params_by_ref` in the feature plan wire (only when episodes are declared); no-regression test on plan and `plan_hash`

## 2. Query

- [ ] 2.1 Request model and validation (`market`, `episode`, `sides`, `series`, `expected_market_data_hash`)
- [ ] 2.2 History: `computed_from_ms` from the slow-EMA warm-up and `history_bars`, clamped to the earliest committed candle
- [ ] 2.3 EMAs through the indicator range evaluation; projection through `project_side`
- [ ] 2.4 Clip of entities to the display range, segments, optional series, identity fields
- [ ] 2.5 Route `POST /v1/ema-stack-episodes/range`

## 3. Tests

- [ ] 3.1 Equality with diagnostics episode tables for the same parameters and computed range, both sides
- [ ] 3.2 Clip, segments and series on hand-built bars; an episode started before `from_ms` keeps its touch numbers
- [ ] 3.3 Parameter errors equal to the strategy section; determinism and identity
- [ ] 3.4 Size and time of one year of BTCUSDT.P 5m, reported

## 4. Parity and gate

- [ ] 4.1 HTTP parity with `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m, both sides (owner's Mac)
- [ ] 4.2 ruff, mypy, full suite without `tests/parity`, `openspec validate ema-stack-episode-query-v1 --strict`
