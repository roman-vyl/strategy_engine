## 1. Provider

- [ ] 1.1 Parse and validate the `ema_stack_episode` provider (defaults from `anchor_stack`, ordered periods, unknown keys rejected); plan its EMA columns through the existing EMA planning
- [ ] 1.2 Implement the per-side state machine (episode, touch, zone, false break, comeback, break) and the wave/leg tracker in one pass per side
- [ ] 1.3 Censoring at the evaluated-range start
- [ ] 1.4 Unit tests on hand-built bars for every rule in the capability spec, the short mirror, and causality (truncation invariance)
- [ ] 1.5 Fixtures of the two owner-approved drawn examples with the drawn numbers

## 2. Bundle and API

- [ ] 2.1 Build the provider in `build_context_bundle`; `ContextOutput` carries per-side fields and the zone table; `htf_context` output unchanged
- [ ] 2.2 Reject gates, exit consumption and `state` predicates on an episode context
- [ ] 2.3 Wire serialization of the episode output and the composer catalog entry

## 3. Predicate operand

- [ ] 3.1 Parse `{"episode": {...}}` in `compare` and `range`; reject it in `change` and in `short` overrides; validate field and wave selector
- [ ] 3.2 Evaluate by reading the bundle for the evaluated side; NaN is False
- [ ] 3.3 Tests: wave selectors, both sides, composite_setup usage, temporal over an episode predicate

## 4. Identity, history, cost

- [ ] 4.1 Node identity and resolve twins for the provider and episode-reading predicates; memo tests with zero unforeseen consumptions
- [ ] 4.2 Live history entry `history_bars`; planner tests
- [ ] 4.3 No-regression tests: plan_hash, identities and compute counts for specs without the provider
- [ ] 4.4 Time one evaluation on the full BTCUSDT.P 5m range and report

## 5. Parity and gate

- [ ] 5.1 Parity with the research reference `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m: every zone, touch number and leg point (run on the owner's Mac)
- [ ] 5.2 ruff, mypy, full suite, `openspec validate ema-stack-episode-context-v1 --strict`
