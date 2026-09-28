## 1. Contract

- [x] 1.1 Add optional `HistoricalManagedProjection` field
      (`conditions`, `distances`, `rules`) to
      `HistoricalExecutionProjection` in
      `strategy_engine/strategies/contracts.py`; `None` unless
      `exit_management.mode == "managed"`.
- [x] 1.2 Implement the `rules[]` discriminated union per
      `design.md` D6a: four kinds (`phase_transition`, `take_action`,
      `stop_action`, `runtime_exit`), each carrying `rule_id`,
      `activation_phase`, `confirm_bars`, opaque `condition_id`/
      `distance_id` references, and (for `take_action`/`stop_action`/
      `runtime_exit`) a closed generic `action`/`exit_class` enum —
      never a `component_id` or raw strategy parameter.

## 2. Strategy Engine: candidate-wide managed evaluator

- [x] 2.1 Implement a new vectorized condition/distance evaluator
      (separate module, not `exits.py`) that mirrors `managed.py`'s
      exact per-component formulas: `bars_in_trade`, `mfe_pct`,
      `mfe_atr`, `adx_di_threshold` (phase conditions);
      `phase_runtime_exit`, `rsi_signal_exit`, `ema_cross_loss_exit`
      (runtime exits); `break_even_stop`, `lock_profit_stop` (stop
      management); `take_profile_switch`/`disable_fixed_tp` (take
      management). Done in
      `strategy_engine/strategies/ema_pullback/historical_managed_projection.py`
      -- reuses `managed.py`'s own parsing/formula helpers directly
      (not a duplicate implementation) for parity safety.
- [x] 2.2 Produce pre-confirm boolean `conditions` (both sides) —
      no confirm-bars window applied at this layer.
- [x] 2.3 Produce fully parameterized `distances` with each
      strategy's multiplier/threshold already applied. Missing/not-
      ready values are `float('nan')` internally (`None` on the wire)
      so a consumer's `>=` comparison naturally reproduces
      `managed.py`'s "not ready" behavior with no special-casing.
- [x] 2.4 Distill phase transitions and actions into ordered `rules[]`
      per Decision D6 (generic enum, no raw `phase_rules`/
      `take_management`/`stop_management`/`runtime_exits` passthrough).
- [x] 2.5 Wire the evaluator into the existing candidate-wide
      evaluation lifetime `/range-batch` already uses
      (`EmaPullbackRangeEvaluator.evaluate_execution_projection`),
      gated on `exit_management.mode == "managed"`; runs at most once
      per candidate regardless of trade count. Wire-serialized in
      `strategy_engine/adapters/http/strategy_serialization.py`
      (`managed` key, `None` when not managed).

## 3. Semantic parity verification (Strategy Engine side)

- [x] 3.1 Built the parity corpus (not the full RSI87 Stage-1 spec
      verbatim, but one hand-built spec exercising all ten managed
      components at once: `adx_di_threshold`, `bars_in_trade`,
      `mfe_pct`, `mfe_atr` phase gates; `break_even_stop`,
      `lock_profit_stop`; `take_profile_switch`; `phase_runtime_exit`,
      `rsi_signal_exit`, `ema_cross_loss_exit`) in
      `tests/test_ema_pullback_historical_managed_projection.py`,
      parametrized over long/short and four different entry indices.
- [x] 3.2 `_replay_from_projection` (a minimal reference consumer,
      the same role Research's real primitives play) asserts bar-for-
      bar equality against `evaluate_managed_replay`'s oracle output
      for phase, active stop price, active take profile, and armed
      runtime-exit rule ids, across the whole corpus. All green.
- [x] 3.3 Gate honored — section 4 only started after 3.2 passed.

## 4. Research Service: generic managed lifecycle primitives

- [x] 4.1 Implemented in
      `research_service/execution/managed_policy.py::
      build_managed_policy_timeline_from_projection` — ports the
      exact `start = index - confirm_bars + 1; start < entry_index`
      boundary. Boundary + entry-anchoring covered by
      `tests/test_managed_policy_from_projection.py::
      test_runtime_confirm_bars_is_entry_anchored`.
- [x] 4.2 Phase-advancement (rank comparison, `condition_id` or
      `distance_id`+`trade_metric` threshold gate) implemented in the
      same function, dispatching on `rules[].kind` only.
- [x] 4.3 Stop ratchet (extremum + tighten-only) and take-profile
      switch implemented in the same function, consuming `distances`/
      `resulting_profile` only.
- [x] 4.4 Produces the existing `ManagedEffectiveState`/
      `ManagedPolicyTimeline` shape unchanged — verified by
      `test_managed_policy_from_projection.py`'s hand-computed trace
      (phase/stop/take/runtime timeline across 5 bars, plus stop
      ratchet rule-id attribution). `active_stop_component_id`/
      `active_take_component_id`/`runtime_exit_components` are always
      `None` on this path — `component_id` is not part of this
      contract by design (D2/D6); this is a diagnostic-field-only gap,
      documented in the function's docstring.

## 5. Historical batch path cutover

- [x] 5.1 Wired in `research_service/execution/projection_loop.py::
      _resolve_managed_timeline`: when
      `projection_index.projection.managed` is present, builds the
      timeline locally (zero Strategy Engine calls); otherwise falls
      back to the existing per-position `managed_replay_provider`
      (`/managed-replay`). This fallback *is* the comparison path 5.1
      originally asked for a "switch" for — no separate manual toggle
      was needed since presence of `managed` on the projection already
      selects the path. `materialize_backtest_projection.py` needed no
      changes: its `_managed_provider` closure is simply never invoked
      once `managed` is present.
- [ ] 5.2 NOT done. Requires the live Docker-orchestrated
      Strategy-Engine/Research-Service stack (per this session's
      earlier infra work) running a real managed batch end-to-end and
      diffing full trade records/aggregate metrics against a
      `/managed-replay`-sourced run of the same candidates. Unit-level
      coverage exists (`test_single_instance_backtest.py::
      test_managed_candidate_with_projection_skips_managed_replay_http_call`
      proves the wiring end-to-end through `RunSingleInstanceBacktest`
      with a fixture projection, but not against a real Engine/oracle
      pair).
- [x] 5.3 (partial) `test_managed_candidate_with_projection_skips_managed_replay_http_call`
      proves zero Strategy Engine managed-replay requests for one
      managed candidate through the real `RunSingleInstanceBacktest`
      seam. NOT done: instrumenting `ValidateStrategySpec`/feature-
      plan/indicator-range call counts specifically, and confirming
      O(1) against a real multi-hundred-trade candidate (needs the
      live stack, same as 5.2).
- [x] 5.4 Achieved as a side effect of the 5.1 design: there is no
      separate default/flag to switch — any candidate whose spec sets
      `exit_management.mode == "managed"` automatically gets a
      populated `managed` projection from Strategy Engine and
      automatically takes the local-timeline path in Research Service.
      `/managed-replay` and the live open-trade projection path are
      untouched (no call site of either was modified).

## 6. Cleanup

- [ ] 6.1 NOT applicable as originally phrased: there is no manual
      comparison switch to remove — the `managed_replay_provider`
      fallback in `_resolve_managed_timeline` is the permanent
      migration-parity safety net (proposal.md: "/managed-replay ...
      serves as a parity oracle during migration"), not a temporary
      one. Revisit only if a future change decides to retire the
      fallback entirely.
- [ ] 6.2 NOT done. No operator-facing docs were found/updated this
      pass.
