# Design: EMA Pullback Managed Policy v1

## Boundary

```text
strategy spec + market range + opened-trade facts
→ feature planning
→ Indicator Engine / Market Data Service
→ managed policy replay
→ phase/stop/take/runtime-exit decisions
```

The replay does not determine whether an inherited stop was hit inside OHLC. Decisions produced at end of bar N become effective from bar N+1.

## Endpoint

`POST /v1/strategy-evaluations/managed-replay`

Required trade facts: `trade_id`, `side`, `entry_time_ms`, `entry_price`. The strategy spec remains the authority for phase rules, stop management, take management and runtime exits.

## Supported semantics

- monotonic phases: initial_risk, proven, protected, runner, exhaustion;
- conditions: bars_in_trade, mfe_pct, mfe_atr, adx_di_threshold;
- stops: break_even_stop, lock_profit_stop, tighten-only merge;
- take_profile_switch;
- runtime exits: phase_runtime_exit, rsi_signal_exit, ema_cross_loss_exit;
- end-of-bar activation with `effective_from_bar = N + 1`.

## Ownership

> **Decision under review:** `BBB/Abi own actual execution` must not be read as a direct Strategy Engine → Abi integration. Live execution is mediated by the standalone Strategy Runtime. The exact neutral Engine decision DTO and Runtime-to-Abi mapping require a separate approved contract before Runtime implementation.


Strategy Engine owns policy and next-state calculation. BBB/Abi own actual execution and fill facts.
