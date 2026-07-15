# EMA Pullback exit policy v1 specification

## Requirement: Standard exit component parity

The engine SHALL implement `no_signal_exit`, `rsi_signal_exit`, `ema_close_loss_exit`, `ema_cross_loss_exit`, `atr_stop_loss`, `atr_take_profit`, `constant_usd_stop_loss`, and `constant_usd_take_profit` with BBB-compatible bar semantics.

## Requirement: Profile-aware composition

Always-on exit rules SHALL be combined with the currently selected aligned, countertrend, or neutral profile for each side and bar. Signal rules SHALL combine with OR. Distance rules of the same exit kind SHALL combine by minimum relative distance.

## Requirement: Stable response

A successful strategy range evaluation SHALL return bar-aligned signal-exit masks, stop-loss ratios, take-profit ratios, stop-readiness masks, selected profiles, per-profile outputs, and rule evidence. Relative numeric values SHALL be normalized decimal text or `null`.

## Requirement: Decision readiness

After standard entries and exit policy are available, the engine SHALL mark `stage=decisions_ready`, `exits_ready=true`, and `decisions_ready=true`. It SHALL include an explicit warning that managed exit decisions are not yet ported when the strategy spec contains or may rely on managed exit behavior.

## Requirement: Execution remains external

The engine SHALL NOT simulate fills, decide which OHLC stop/take hit wins, calculate fees or PnL, or claim that any exit decision was executed.
