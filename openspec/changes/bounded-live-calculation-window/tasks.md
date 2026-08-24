## 1. Contracts and package scaffold (A)

- [x] 1.1 Create `src/strategy_engine/strategies/live_calculation/__init__.py`
- [x] 1.2 Create `contracts.py` with `HistoryRequirement(timeframe, bars, reason)`, `PlannedHistoryStart(from_ms, winning_indicator_requirement, winning_strategy_requirement, requirements)`, and the `StrategyHistoryRequirements` Protocol boundary between the generic planner and a concrete strategy family's own semantic-history knowledge (design.md Decision 2/2a)
- [x] 1.3 Add architecture tests asserting `live_calculation/` modules import no MDS client, pandas, or HTTP dependency, and import no concrete strategy-family package (`live_calculation/` depends only on `StrategyHistoryRequirements`)

## 2. Generic indicator requirement resolution (A + B)

- [x] 2.1 Implement `indicator_requirements.py`: `ResolveIndicatorHistoryRequirements` reading the existing `IndicatorPlan` and emitting one `HistoryRequirement` per planned feature, including an explicit zero-additional-warm-up entry for upstream-scaling features (e.g. `atr_distance` inherits ATR's requirement, contributes none of its own)
- [x] 2.2 Implement finite-bar lookback policy for RSI and ATR
- [x] 2.3 EMA convergence-tolerance policy against the actual `.ewm(adjust=False)` recursion (`y[n] = alpha*x[n] + (1-alpha)*y[n-1]`, seed decay `(1-alpha)^n < tolerance` — not `alpha^n`), behind its own `ema_tolerance` constant, calibrated independently of ADX/DI's
- [x] 2.4 ADX/DI convergence-tolerance policy against Wilder's two-stage RMA cascade in `compute_adx_dmi` (TR/+DM/-DM smoothing, then a second pass smoothing DX into ADX — two independent bootstrap windows, not one), behind its own `adx_dmi_tolerance` constant. Deliberately over-provisioned, documented as a provisional structural policy rather than a precisely derived exact bound.
- [x] 2.5 Fail-closed behavior for any indicator kind in the plan with no registered policy
- [x] 2.6 (B) Unit test each indicator's resolved requirement against hand-computed expected bar counts (RSI, ATR finite; EMA, ADX/DI recursive with correct decay base; `atr_distance` zero-additional case; fail-closed case)

## 3. ema_pullback strategy-component requirements (A + B)

- [x] 3.1 Create `src/strategy_engine/strategies/ema_pullback/live_calculation_requirements.py` with `EmaPullbackLiveCalculationRequirements`
- [x] 3.2 Audit every currently live-supported `ema_pullback` context, blocker, setup, trigger, risk/entry, and exit component and assign each an explicit history policy: zero additional history, finite semantic lookback, or bounded stateful semantic policy. Covers `anchor_stack_width`, `untouched_anchor` (lookback + active_bars - 1), trigger reclaim (object and bare-string forms), RSI/trend-strength blockers, `contexts.*`/`components.direction`/`components.risk` (zero additional), and exit temporal windows (`confirm_bars`, including the `shift(1)` dependency). Every resolved lookback is counted on the base FeatureFrame axis, not the timeframe axis of whichever indicator feeds the component. Fail-closed on every unrecognized component_id.
- [x] 3.3 Implement bounded semantic warm-up for `ema_bounce_counter_setup`'s trend-episode memory, documented as a policy approximation (no fixed lookback bounds `completed_count`), not a provably sufficient window
- [x] 3.4 Fail-closed behavior for any live-supported component not covered by the audit in 3.2
- [x] 3.5 (B) Unit test each strategy-component requirement against its configured lookback, the fail-closed case, and the axis rule (a component's span does not scale with an unrelated indicator's timeframe)

## 4. Window planner (A + B)

- [x] 4.1 Implement `plan_window.py`: `PlanLiveHistoryStart` accepting a `StrategyHistoryRequirements` implementation (required, not defaulted — design.md Decision 2a), `IndicatorPlan`, `base_timeframe`, and history anchor
- [x] 4.2 Additive composition: `required_pre_anchor_span = indicator_warmup_span + strategy_semantic_span` (max within each source, summed across sources — not `max()` across both), returning `winning_indicator_requirement` and `winning_strategy_requirement` as separate fields
- [x] 4.3 `(timeframe, bars)` -> base-timeframe span conversion using fixed per-timeframe candle duration and the supplied `base_timeframe`
- [x] 4.4 HTF bucket alignment: for every distinct higher timeframe present in the indicator plan, roll `from_ms` back to the start of that timeframe's fixed-duration UTC resample bucket, applied simultaneously for all higher timeframes in use, via LCM of all in-use HTF durations
- [x] 4.5 (B) Unit test additive composition with a composite case (e.g. RSI14 blocker with lookback=20) asserting the consumer's lookback window contains no bars backed by not-yet-valid upstream indicator values
- [x] 4.6 (B) Unit test aggregation/winner selection across mixed-timeframe requirement sets, including a randomized case, and against a fake `StrategyHistoryRequirements` implementation to prove the planner is generic
- [x] 4.7 (B) Unit test timeframe-conversion edge cases (base timeframe, HTF multiples)
- [x] 4.8 (B) Unit test HTF bucket alignment: target inside a `1h` bucket, target inside a `4h` bucket, an unaligned `from` candidate that must snap to a bucket start, and a spec using `1h` and `4h` simultaneously

## 5. Calibration and production readiness of the disconnected planner (C)

**Acceptance principle (design.md/proposal.md):** the gate is numeric parity — every `IndicatorPlan` output and every numeric/intermediate value strategy components compute on top of it, over the downstream-consumed tail each component reads — not categorical business outcomes, which are secondary smoke only.

- [x] 5.1 EMA convergence tolerance calibrated against real BTCUSDT.P/ETHUSDT.P history under the numeric-parity gate; fixed at `1e-4`
- [x] 5.2 ADX/DI convergence tolerance calibrated independently under the same gate; fixed at `1e-4`
- [x] 5.3 `ema_bounce_counter_setup`'s anchor-EMA-period tier policy established from real `trend_active` episode-length measurement across three production-family anchor-stack sizes (design.md Decision 12):

  | anchor EMA period | observed max episode | policy `history_bars` |
  |---|---|---|
  | ≤ 200 | 1,832 | 2,500 |
  | 201-500 | 4,736 | 6,000 |
  | 501-1,000 | 11,000 | 15,000 |
  | > 1,000, bounce present | — | fail closed |

  Empirical V1 policy, not a mathematical upper bound. Conditional: present only when `ema_bounce_counter_setup` is configured; classified solely by `anchor_stack.anchor.period` (fast/slow EMA periods do not affect tier selection).
- [x] 5.4 Boundary, conditional-presence, fail-closed, and planner-aggregation regression tests for the tier policy (`tests/test_live_calculation_ema_pullback_requirements.py`)
- [x] 5.5 Production requirement resolvers, planner, and contracts unit-tested to production-ready state (groups 1-4)
- [x] 5.6 Architecture cleanup complete: `live_calculation/` depends only on `StrategyHistoryRequirements` (design.md Decision 2a), no concrete strategy family import, no registry/factory/plugin framework, no composition helper created ahead of a real caller; bounce tier policy is a non-overridable private production constant (`_BOUNCE_HISTORY_TIERS`); production diagnostics and comments carry only stable, load-bearing information — full empirical basis and rationale live in this file and design.md, not in source comments

Calibration/validation tooling used to reach 5.1-5.3 (full-history reference harness, tolerance sweeps, episode-distribution measurement, tier validation runs) was disposable research infrastructure and is not retained in the production repository — the calibrated constants and the tier table above are the artifacts that carry forward.

**Group 5: CLOSED.**

## 6. Wire into live acquisition (D) — NOT STARTED

The bounded planner (`PlanLiveHistoryStart`, `ResolveIndicatorHistoryRequirements`, `EmaPullbackLiveCalculationRequirements`) is implemented, unit-tested, and calibrated, but remains fully disconnected from the production live path. This group performs the wiring; a later, separate task.

- [ ] 6.1 Modify `evaluate_live_entry_projection.py` to compute and pass `history_anchor_open_time_ms = target_bar_open_time_ms`
- [ ] 6.2 Modify `evaluate_open_trade_projection.py` to compute and pass `history_anchor_open_time_ms = min(source_plan_bar_open_time_ms, entry_bar_open_time_ms)`
- [ ] 6.3 Add `history_anchor_open_time_ms` to the internal live feature frame request used by `load_live_feature_frame.py`; `LoadLiveFeatureFrame` SHALL only consume this value, never compute or re-derive it
- [ ] 6.4 Modify `load_live_feature_frame.py`: invoke `PlanLiveHistoryStart` (passing `request.market.base_timeframe` and the received anchor) before `MDS.load_bounds()`, then compute `actual_from_ms = max(planned_from_ms, bounds.earliest_committed_open_time_ms)`; keep `to_ms = target_bar_open_time_ms + base_timeframe_duration` unchanged
- [ ] 6.5 Emit a structured diagnostic when `bounds.earliest_committed_open_time_ms > planned_from_ms` (truncation), including `winning_indicator_requirement` and `winning_strategy_requirement`
- [ ] 6.6 Wire `PlanLiveHistoryStart` to a concrete `EmaPullbackLiveCalculationRequirements()` (and `ResolveIndicatorHistoryRequirements`) at the composition boundary in `service/wiring.py` — this is where the "ema_pullback is the current live strategy family" knowledge is allowed to live

## 7. Integration, regression, and performance tests (E)

- [ ] 7.1 Add/confirm a test asserting Research/Backtest range evaluation never invokes the new planner and is unaffected by this change
- [ ] 7.2 Integration test: live-entry request with a spec producing a small requirement set reads only the expected bounded range
- [ ] 7.3 Integration test: open-trade request with anchor before target reads a range covering anchor warm-up through target
- [ ] 7.4 Integration test: planned window predates MDS bounds -> request is clamped, diagnostic emitted, request still succeeds
- [ ] 7.5 Integration test: spec containing a component with no registered history policy -> live request fails closed with a clear error, not a silently under-provisioned window
- [ ] 7.6 Measure live-entry and open-trade latency separately, before and after this change is wired in

## 8. Rollout (F)

- [ ] 8.1 Review group 6/7 results; if parity or latency is insufficient for any component, adjust the relevant policy constant and re-run calibration before re-attempting rollout
- [ ] 8.2 Enable the bounded live path in production once parity, numeric drift, and latency targets are met
- [ ] 8.3 Document the open-trade long-position latency limitation as a known follow-up item
