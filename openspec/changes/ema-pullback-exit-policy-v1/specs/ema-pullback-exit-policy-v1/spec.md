# EMA Pullback Exit Policy v1 Specification

## ADDED Requirements

### Requirement: Standard exit component parity

The engine SHALL implement `no_signal_exit`, `rsi_signal_exit`, `ema_close_loss_exit`, `ema_cross_loss_exit`, `atr_stop_loss`, `atr_take_profit`, `constant_usd_stop_loss`, and `constant_usd_take_profit` with BBB-compatible bar semantics.

#### Scenario: Evaluate a standard exit component

- **WHEN** a supported standard exit receives identical inputs to BBB
- **THEN** its bar-aligned signal or distance output SHALL match BBB semantics.

### Requirement: Profile-aware composition

Always-on exit rules SHALL be combined with the currently selected aligned, countertrend, or neutral profile for each side and bar. Signal rules SHALL combine with OR. Distance rules of the same exit kind SHALL combine by minimum relative distance.

#### Scenario: Compose always-on and selected-profile rules

- **WHEN** standard exit policy is evaluated for one side and bar
- **THEN** always-on rules SHALL be combined with the selected profile
- **AND** signals SHALL use OR while like-kind distances SHALL use the minimum.

### Requirement: Stable response and protection readiness

A successful strategy range evaluation SHALL return bar-aligned signal-exit masks, stop-loss ratios, take-profit ratios, stop-readiness masks, selected profiles, per-profile outputs, and rule evidence. Relative numeric values SHALL be normalized decimal text or `null`. When a stop or take rule is configured, readiness SHALL be false on every bar where its selected output is null; an absent rule kind SHALL NOT block readiness.

#### Scenario: Configured ATR protection is still warming up

- **WHEN** a selected stop or take rule is configured but its value is null on a bar
- **THEN** protection readiness SHALL be false for that bar.

#### Scenario: No rule exists for one protection kind

- **WHEN** no stop or take rule of one kind is configured for the selected profile
- **THEN** the absent kind SHALL NOT by itself block readiness.

### Requirement: Decision readiness

After standard entries and exit policy are available, the engine SHALL mark `stage=decisions_ready`, `exits_ready=true`, and `decisions_ready=true`. Managed policy SHALL remain available through its separate managed replay and open-trade projection contracts.

#### Scenario: Return standard strategy decisions

- **WHEN** a standard strategy range evaluation succeeds
- **THEN** it SHALL advertise decision and exit readiness
- **AND** SHALL keep managed lifecycle decisions on their dedicated contracts.

### Requirement: Execution remains external

The engine SHALL NOT simulate fills, decide which OHLC stop/take hit wins, calculate fees or PnL, or claim that any exit decision was executed.

#### Scenario: Return exit policy intent

- **WHEN** signal, stop, or take policy is returned
- **THEN** it SHALL remain policy intent only
- **AND** SHALL contain no fabricated execution or accounting outcome.
