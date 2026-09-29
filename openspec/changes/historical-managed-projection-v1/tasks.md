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
      timeline locally (zero Strategy Engine calls).

      **Hardened after independent code review** (production blocker):
      the fallback to per-trade `/managed-replay` is no longer silent.
      A caller that supplies `managed_replay_provider` (i.e. requested
      managed execution) but whose acquired projection carries no
      `managed` now gets `UpstreamServiceError` — the eliminated
      O(trades x full-history) path can never be silently re-entered
      in production. The old per-trade path survives only behind an
      explicit, code-level opt-in
      (`allow_legacy_managed_replay_fallback=True`, set at
      `RunSingleInstanceBacktest`/`MaterializeBacktestProjectionOutcome`/
      `Container` construction — never a request-body field, never a
      global default), for parity/oracle test scenarios only. See
      `tests/test_managed_projection_fail_closed.py` (A: projection
      present → local path, zero calls; B: projection absent → fails
      closed, zero calls; C: explicit opt-in → legacy path restored)
      and `test_managed_policy_from_projection.py::
      test_confirm_bars_positive_boundary_arms_exactly_on_the_nth_consecutive_bar`.
      Component-attribution impact audit (`active_stop_component_id`/
      `active_take_component_id`/`runtime_exit_components` always
      `None` on the projection path): traced every consumer
      (`execution/managed_policy.py::collect_managed_exit_candidates`
      is the only one; feeds `ExitCandidate.component_id` and the
      `active_stop` reason-string suffix only) through arbitration
      (`unified_exits.py::arbitrate_unified_exit_candidates`, tie-break
      key is `(priority, reason)` — the stop candidate is structurally
      singular per bar so this tie-break is never actually exercised
      by it) to persistence (`accounting/contracts.py::
      TradeRecord.exit_component_id`, already-nullable, zero other
      readers in the codebase) to the API surface (no route exposes
      it). Confirmed: cosmetic/diagnostic only, does not affect
      arbitration winner, fill price/timing, or any required persisted
      field — a disclosed, intentional gap for a future pass, not a
      5.2 blocker.
- [x] 5.2 DONE, live. Ran a real EMA500-anchor-stack managed candidate
      (ADX(14)≥25+DI-aligned→proven→disable TP; break_even_stop at
      proven; RSI(14) 87/13 runtime exit, confirm_bars=1 — the same
      shape as the RSI87 Stage-1 spec that triggered this whole
      investigation) against a locally-run instance of this branch's
      Strategy Engine (commit `e95a252`) and the real market-data-
      service, over two windows: `A_short` (2025-07-01..2025-09-01, 7
      trades) and `B_long` (2023-01-01..2025-09-01, 196 trades). Each
      window run twice through the real `RunSingleInstanceBacktest`
      seam — OLD (`allow_legacy_managed_replay_fallback=True`, forced
      oracle override, see D-note below) vs NEW (default) — and
      diffed trade-for-trade on every execution-semantic field (side,
      entry/exit bar_index+time_ms+price, quantity, gross/net pnl,
      equity_before/after, exit_candidate_type, exit_rule_id, R
      multiples). **All 203 trades across both windows matched exactly
      on every semantic field.** Two disclosed diagnostic-only
      differences confirmed present, exactly as predicted by the 5.1
      audit, on the trades where they apply: `exit_reason`/
      `exit_component_id` (stop-exit trades) and, newly found during
      this run, `exit_kind`'s literal string on *runtime*-exit trades
      (OLD carries the raw spec string, e.g. `"signal"`; NEW carries
      the canonical representative of the resolved `exit_class`
      bucket, e.g. `"market_close"` — see the D-note below for why
      this is inert). Zero `exit_candidate_type` mismatches anywhere —
      arbitration outcome is unaffected.

      **D-note (design correction found live):** the initial 5.1
      `allow_legacy_managed_replay_fallback` implementation only
      triggered the legacy path when `managed` was *absent* — running
      it against a real candidate (where `managed` is always present)
      silently took the NEW path regardless of the flag, defeating the
      oracle comparison. Fixed in `_resolve_managed_timeline`:
      `allow_legacy_managed_replay_fallback=True` now *forces* the
      legacy path even when `managed` is present (a genuine override,
      not just a missing-projection rescue). Covered by a new test,
      `test_c2_explicit_opt_in_overrides_a_present_projection_too`.
      Production default (`False`) behavior is unchanged by this fix.

      **New audit finding — `exit_kind` joins the disclosed-gap list.**
      Traced the same way as 5.1's component_id audit: the managed
      runtime-exit `exit_kind` string only ever feeds
      `_runtime_candidate_type(exit_kind)` (already proven identical-
      bucket by construction between `historical_managed_projection.py`'s
      `_runtime_exit_class` and `managed_policy.py`'s own
      `_runtime_candidate_type`) and the `reason` string/storage —
      confirmed via the same `grep -rn "\.exit_kind\b"` sweep as the
      component_id audit: every other reader is the *unrelated*
      static-exit-policy `exit_kind` (`stop_loss`/`take_profit`/
      `signal` attribution validation), not this one. Zero behavioral
      consequence, confirmed live across 90 runtime-exit trades in
      `B_long`, not just by static trace.
- [x] 5.3 DONE, live. Table (NEW path, real HTTP call counts from the
      Strategy Engine access log, not a fixture):

      | window  | trades | `/range` calls | `/managed-replay` calls |
      |---------|--------|-----------------|--------------------------|
      | A_short | 7      | 1               | 0                        |
      | B_long  | 196    | 1               | 0                        |

      `/range` internally runs `ValidateStrategySpec` ->
      `BuildStrategyFeaturePlan` -> `EvaluateIndicatorRange` exactly
      once per HTTP call (that invariant is what I7/I8 already
      established and is unrelated to this change) — one call per
      window, at a ~28x trade-count spread (7 -> 196), directly proves
      those three steps run candidate-level, not trade-level, for the
      real code path. For contrast, the OLD oracle's real call counts
      on the same two windows: `managed-replay` = 7 and 196
      respectively (exactly one per opened trade, confirming the
      eliminated pathology is real, not theoretical) — and wall time:
      `A_short` OLD 4.9s vs NEW 1.4s; `B_long` OLD 2012.5s (~33.5 min)
      vs NEW 199.0s (~3.3 min), a ~10x speedup already visible on a
      *single* 196-trade candidate over 2.7 years — well short of
      8352-candidate-batch scale, but the shape of the win is now
      measured live, not projected.
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
