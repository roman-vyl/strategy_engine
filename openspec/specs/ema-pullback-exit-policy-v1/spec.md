# ema-pullback-exit-policy-v1 Specification

## Purpose

Define standard EMA Pullback exit policy: the supported signal and stop/take components, profile-aware composition of always-on and selected-profile rules, the stable range-response shape and protection readiness rules, decision readiness signaling, and the boundary that execution and accounting stay external.
## Requirements
### Requirement: Standard exit components

The engine SHALL implement `no_signal_exit`, `rsi_signal_exit`, `ema_close_loss_exit`, `ema_cross_loss_exit`, `atr_stop_loss`, `atr_take_profit`, `constant_usd_stop_loss`, and `constant_usd_take_profit`. Signal components SHALL return a bar-aligned signal output. Stop and take components SHALL return a bar-aligned protection distance output according to their configuration.

#### Scenario: Evaluate a standard exit component

- **WHEN** a supported standard exit is evaluated
- **THEN** a signal component SHALL return a bar-aligned signal output
- **AND** a stop or take component SHALL return a bar-aligned protection distance output according to its configuration.

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

### Requirement: Positional, fail-closed profile selection

Per-bar profile selection within exit-policy evaluation SHALL be positional (selecting by bar position/index-position, not by pandas label/index alignment): for bar `i`, the value SHALL come from the series belonging to the profile assigned to bar `i`, matched by position, not by any join/merge/reindex operation. An unrecognized profile name encountered during selection SHALL cause evaluation to fail (raise an error) rather than silently substitute a default or null value.

#### Scenario: Selection is positional, not label-aligned

- **WHEN** exit-policy evaluation selects a per-bar value according to the bar's assigned profile
- **THEN** the selected value SHALL be the value at that same bar position in the chosen profile's series
- **AND** the selection SHALL NOT depend on pandas index/label alignment between the profile assignment and the series being selected from.

#### Scenario: Unrecognized profile name fails closed

- **WHEN** a bar is assigned a profile name that does not correspond to any evaluated profile series
- **THEN** exit-policy evaluation SHALL raise an error
- **AND** SHALL NOT silently produce a null, default, or otherwise substituted value for that bar.
