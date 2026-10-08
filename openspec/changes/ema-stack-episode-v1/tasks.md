## 1. Episode projection

- [ ] 1.1 Parse and validate `raw_spec.ema_stack_episode` (defaults from `anchor_stack`, ordered periods, unknown keys rejected); plan its EMA columns through the existing EMA planning
- [ ] 1.2 Per-side state machine (episode, zones, false breaks, comeback, stack break) and entity lists (zones, false breaks, waves with origin, peak, up leg, down leg, `known_at`, forming values) in one pass per side
- [ ] 1.3 Censoring at the evaluated-range start
- [ ] 1.4 Unit tests on hand-built bars for every rule and the short mirror; wave geometry with and without a false break, peak before the low; truncation invariance
- [ ] 1.5 Fixtures of the two owner-approved drawings

## 2. Bundle and result

- [ ] 2.1 Build the episode bundle once per evaluation beside the ContextBundle; reject episodes as contexts, gates and exit consumption
- [ ] 2.2 `ema_stack_episode` in the strategy range result (state series and entity tables per side); `contexts` output unchanged

## 3. Episode operand

- [ ] 3.1 Parse `{"episode": {...}}` in `compare` and `range`; validate entity, index and field; reject it in `change` and as a `short` override operand
- [ ] 3.2 Evaluate as O(bars) gathers from the entity lists for the evaluated side; missing is False
- [ ] 3.3 End-to-end test: `composite_setup` with `touch_number < 3`; relative leg comparison; temporal over an episode predicate

## 4. Identity, history, cost

- [ ] 4.1 Node identity and resolve twins; memo tests with zero unforeseen consumptions
- [ ] 4.2 Live history entry `history_bars`; planner tests
- [ ] 4.3 No-regression tests for specs without `ema_stack_episode`
- [ ] 4.4 Time one evaluation on the full BTCUSDT.P 5m range and report

## 5. Parity and gate

- [ ] 5.1 Parity with the research reference `counter_v6.py` (rebuilt to this geometry) on BTCUSDT.P and ETHUSDT.P 5m, both sides, per bar and per entity, compared by `time_ms` (run on the owner's Mac)
- [ ] 5.2 ruff, mypy, full suite, `openspec validate ema-stack-episode-v1 --strict`
