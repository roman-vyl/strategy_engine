## MODIFIED Requirements

### Requirement: Standard exit components

The engine SHALL implement `no_signal_exit`, `rsi_signal_exit`, `ema_close_loss_exit`, `ema_cross_loss_exit`, `atr_stop_loss`, `atr_take_profit`, `constant_usd_stop_loss`, `constant_usd_take_profit`, `pct_partial_take`, and `atr_partial_take`. Signal components SHALL return a bar-aligned signal output. Stop, take and partial take components SHALL return a bar-aligned protection distance output according to their configuration.

#### Scenario: Evaluate a standard exit component

- **WHEN** a supported standard exit is evaluated
- **THEN** a signal component SHALL return a bar-aligned signal output
- **AND** a stop, take or partial take component SHALL return a bar-aligned protection distance output according to its configuration.

#### Scenario: Partial take evidence

- **WHEN** a partial take rule is evaluated
- **THEN** its per-bar distance ratio SHALL appear in rule evidence under its `instance_id` with `exit_kind` `partial_take`.

### Requirement: Profile-aware composition

Always-on exit rules SHALL be combined with the currently selected aligned, countertrend, or neutral profile for each side and bar. Signal rules SHALL combine with OR. Stop-loss and take-profit distance rules of the same exit kind SHALL combine by minimum relative distance. Partial take rules SHALL NOT be combined: each stays a separate leg and SHALL NOT enter the take-profit minimum.

#### Scenario: Compose always-on and selected-profile rules

- **WHEN** standard exit policy is evaluated for one side and bar
- **THEN** always-on rules SHALL be combined with the selected profile
- **AND** signals SHALL use OR while like-kind stop and take distances SHALL use the minimum.

#### Scenario: Partial take closer than the final take

- **WHEN** a profile has an `atr_take_profit` at ratio 0.05 and a `pct_partial_take` at ratio 0.01
- **THEN** the selected take-profit ratio SHALL be 0.05
- **AND** the partial take SHALL remain a separate leg at 0.01.

### Requirement: Stable response and protection readiness

A successful strategy range evaluation SHALL return bar-aligned signal-exit masks, stop-loss ratios, take-profit ratios, stop-readiness masks, selected profiles, per-profile outputs, and rule evidence. Relative numeric values SHALL be normalized decimal text or `null`. When a stop, take or partial take rule is configured, readiness SHALL be false on every bar where its selected output is null; an absent rule kind SHALL NOT block readiness.

#### Scenario: Configured ATR protection is still warming up

- **WHEN** a selected stop or take rule is configured but its value is null on a bar
- **THEN** protection readiness SHALL be false for that bar.

#### Scenario: Configured ATR partial take is still warming up

- **WHEN** an `atr_partial_take` rule is in force for the selected profile and its distance is null on a bar
- **THEN** protection readiness SHALL be false for that bar.

#### Scenario: No rule exists for one protection kind

- **WHEN** no stop or take rule of one kind is configured for the selected profile
- **THEN** the absent kind SHALL NOT by itself block readiness.

#### Scenario: Readiness without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** readiness SHALL equal its value before partial takes were introduced on every bar.
