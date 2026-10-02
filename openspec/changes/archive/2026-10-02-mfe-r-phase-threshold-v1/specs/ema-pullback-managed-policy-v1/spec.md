## ADDED Requirements

### Requirement: Phase atom `mfe_r`

A phase condition `{component_id: "mfe_r", params: {threshold}}` SHALL be
met on a bar when the trade's best excursion, measured in multiples of
its initial risk, has reached `threshold`:

`mfe_r = |mfe_price - entry_price| / initial_risk`, met when
`mfe_r >= threshold`.

- `threshold` SHALL be a positive finite number of R.
- `mfe_price` and its bar range SHALL be those of `mfe_atr` and
  `mfe_pct` (the entry bar's extremes included).
- `initial_risk` SHALL be `|entry_price - initial_stop_price|`, fixed at
  entry. It SHALL NOT change while the managed state advances, and it
  SHALL NOT depend on any bar's ATR.
- When the evaluation has no initial stop, or the initial risk is not
  positive, the condition SHALL be unmet on every bar (fail closed).
- The atom SHALL need no planned feature and no history window.

#### Scenario: Threshold in multiples of initial risk

- **GIVEN** a long entry at 100 with initial stop 98 and `threshold` 2
- **WHEN** the best price reaches 104
- **THEN** the condition SHALL be met on that bar
- **AND** it SHALL NOT be met while the best price is below 104.

#### Scenario: Initial risk is frozen

- **GIVEN** a trade whose active stop has moved after entry
- **WHEN** `mfe_r` is evaluated on a later bar
- **THEN** the denominator SHALL still be `|entry_price - initial_stop_price|`.

#### Scenario: No initial stop

- **WHEN** the evaluation carries no initial stop
- **THEN** a rule gated by `mfe_r` SHALL never fire.

#### Scenario: Start-after-entry evaluation

- **WHEN** an open trade is evaluated from its receipt
- **THEN** the receipt's initial stop SHALL be the one used.

#### Scenario: Managed replay endpoint

- **WHEN** `/managed-replay` evaluates a spec with an `mfe_r` rule
- **THEN** its request carries no initial stop, so the rule SHALL never
  fire
- **AND** that endpoint SHALL NOT be required to support `mfe_r`.
