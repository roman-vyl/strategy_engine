## 1. Contract

- [ ] 1.1 Add optional `HistoricalManagedProjection` field
      (`conditions`, `distances`, `rules`) to
      `HistoricalExecutionProjection` in
      `strategy_engine/strategies/contracts.py`; `None` unless
      `exit_management.mode == "managed"`.
- [ ] 1.2 Define the `rules[]` element shape: `rule_id`,
      `activation_phase`, `target_phase`/generic action enum,
      `condition_id`/`distance_id` references, `confirm_bars`.

## 2. Strategy Engine: candidate-wide managed evaluator

- [ ] 2.1 Implement a new vectorized condition/distance evaluator
      (separate module, not `exits.py`) that mirrors `managed.py`'s
      exact per-component formulas: `bars_in_trade`, `mfe_pct`,
      `mfe_atr`, `adx_di_threshold` (phase conditions);
      `phase_runtime_exit`, `rsi_signal_exit`, `ema_cross_loss_exit`
      (runtime exits); `break_even_stop`, `lock_profit_stop` (stop
      management); `take_profile_switch`/`disable_fixed_tp` (take
      management).
- [ ] 2.2 Produce pre-confirm boolean `conditions` (both sides) —
      no confirm-bars window applied at this layer.
- [ ] 2.3 Produce fully parameterized `distances` with each
      strategy's multiplier/threshold already applied.
- [ ] 2.4 Distill phase transitions and actions into ordered `rules[]`
      per Decision D6 (generic enum, no raw `phase_rules`/
      `take_management`/`stop_management`/`runtime_exits` passthrough).
- [ ] 2.5 Wire the evaluator into the existing candidate-wide
      evaluation lifetime `/range-batch` already uses, gated on
      `exit_management.mode == "managed"`; confirm it runs at most
      once per candidate regardless of trade count.

## 3. Semantic parity verification (Strategy Engine side)

- [ ] 3.1 Build the parity corpus from `proposal.md` acceptance
      criterion 1: one candidate per — adx_di_threshold +
      take_profile_switch + rsi_signal_exit (EMA500 RSI87 Stage-1
      spec), bars_in_trade/mfe_pct/mfe_atr phase gates,
      break_even_stop/lock_profit_stop, ema_cross_loss_exit,
      phase_runtime_exit.
- [ ] 3.2 For each corpus candidate, assert the new evaluator's
      projection is consistent with `/managed-replay`'s per-trade
      output for every historical trade in that candidate: phase
      transition timestamps, active take-profit timeline, managed
      stop price timeline, runtime-exit trigger bar/rule.
- [ ] 3.3 Do not proceed to section 4 until 3.2 passes for the full
      corpus.

## 4. Research Service: generic managed lifecycle primitives

- [ ] 4.1 Implement the entry-anchored confirm-bars sustain-window
      primitive over a pre-confirm boolean series, using the exact
      boundary from `managed.py::_runtime_signal`
      (`start = index - confirm_bars + 1; start >= entry_index +
      offset`); add a boundary-case unit test.
- [ ] 4.2 Implement generic phase-advancement state tracking (phase
      rank, activation ordering) consuming `rules[]`, without any
      strategy-specific branching.
- [ ] 4.3 Implement generic stop/take state application (break-even,
      lock-profit, take-profile-switch/disable) consuming `rules[]`
      and `distances`, without any strategy-specific branching.
- [ ] 4.4 Wire these primitives to produce the same
      `ManagedEffectiveState`/`ManagedPolicyTimeline` shape
      `research_service/execution/managed_policy.py` already defines
      — no changes to that shape itself.

## 5. Historical batch path cutover

- [ ] 5.1 Add a new projection source for
      `materialize_backtest_projection.py::_managed_provider` that
      reads `HistoricalManagedProjection` from the candidate-wide
      response instead of calling `/managed-replay` per trade; keep
      the existing per-trade call path available behind a switch for
      comparison.
- [ ] 5.2 Run full acceptance criterion 1 (semantic parity) end to end
      through Research Service's arbitration
      (`execution/unified_exits.py`) for the corpus in 3.1, confirming
      final trade records and aggregate candidate metrics match the
      `/managed-replay`-sourced path bar-for-bar and trade-for-trade.
- [ ] 5.3 Instrument and verify acceptance criterion 2
      (computational parity): assert `ValidateStrategySpec`
      calls, feature-plan builds, and indicator-range evaluations per
      managed candidate are O(1), independent of trade count.
- [ ] 5.4 Switch the historical managed-batch path's default provider
      to the candidate-wide projection; leave `/managed-replay` and
      the live open-trade projection path untouched.

## 6. Cleanup

- [ ] 6.1 Remove the now-unused per-trade-call comparison switch from
      5.1 once 5.2/5.3 are confirmed green and the cutover is stable.
- [ ] 6.2 Update any research-batch operator documentation that
      referenced `/managed-replay` as the historical execution path,
      to describe the new candidate-wide projection path instead
      (`/managed-replay` remains documented as the live/parity-oracle
      path).
