## 1. Structure

- [ ] 1.1 Parse and validate `raw_spec.market_structure` and `trend_episode` (defaults from `anchor_stack`, ordered periods, unknown keys rejected); plan its EMA columns through the existing EMA planning
- [ ] 1.2 Per-side state machine (episode, zones, false break, comeback, stack break) and range tracker (zones, false breaks, impulses, pullbacks with `known_at`) in one pass per side
- [ ] 1.3 Censoring at the evaluated-range start
- [ ] 1.4 Unit tests on hand-built bars for every rule, the short mirror, truncation invariance
- [ ] 1.5 Fixtures of the two owner-approved drawings

## 2. Bundle and result

- [ ] 2.1 Build the market-structure bundle once per evaluation beside the ContextBundle; reject structures under `contexts`, in gates and in exit consumption
- [ ] 2.2 `market_structure` in the strategy range result (state series and range table per side); `contexts` output unchanged

## 3. Structure-state predicate

- [ ] 3.1 Parse the structure form of `state` (`op`/`value` or `in`), validate field types, reject `short` override
- [ ] 3.2 Evaluate from the bundle for the evaluated side; missing or censored is False
- [ ] 3.3 End-to-end test: `composite_setup` with `touch_number < 3` gives the expected entries; temporal over a structure state

## 4. Identity, history, cost

- [ ] 4.1 Node identity and resolve twins; memo tests with zero unforeseen consumptions
- [ ] 4.2 Live history entry `history_bars`; planner tests
- [ ] 4.3 No-regression tests for specs without `market_structure`
- [ ] 4.4 Time one evaluation on the full BTCUSDT.P 5m range and report

## 5. Parity and gate

- [ ] 5.1 Parity with the research reference `counter_v6.py` (v6_reference: bars and ranges) on BTCUSDT.P and ETHUSDT.P 5m, both sides, compared by `time_ms` (run on the owner's Mac)
- [ ] 5.2 ruff, mypy, full suite, `openspec validate trend-episode-structure-v1 --strict`
