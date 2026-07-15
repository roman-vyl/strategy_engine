# EMA Pullback exit policy v1

The Strategy Engine now owns the standard BBB exit-policy calculation. One range evaluation returns final entries together with signal-exit masks and initial relative stop/take distances.

Supported exit components:

- `no_signal_exit`;
- `rsi_signal_exit`;
- `ema_close_loss_exit`;
- `ema_cross_loss_exit`;
- `atr_stop_loss` / `atr_take_profit`;
- `constant_usd_stop_loss` / `constant_usd_take_profit`.

The output remains a strategy decision artifact, not an execution artifact. BBB still decides OHLC hit ordering, constructs trades, applies fees, and calculates PnL. Managed exit behavior remains the next separate seam.
