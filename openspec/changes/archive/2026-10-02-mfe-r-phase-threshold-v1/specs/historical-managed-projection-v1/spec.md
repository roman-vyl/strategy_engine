## ADDED Requirements

### Requirement: Trade metric `mfe_r`

`TradeMetric` SHALL include `mfe_r`. For an `mfe_r` phase atom, the
projection SHALL emit the rule (or composite trade child) with
`trade_metric: "mfe_r"` and a distance series equal to the atom's R
threshold on every bar.

The consumer SHALL evaluate the metric as
`|mfe_price - entry_price| / initial_risk` with
`initial_risk = |entry_price - initial_stop_price|` of that position,
frozen at entry, and compare it with `>=`. When the position has no
initial stop or its initial risk is not positive, the metric SHALL be
unavailable and the comparison false.

#### Scenario: Projection shape

- **WHEN** a phase rule uses `mfe_r` with `threshold` 6
- **THEN** the rule SHALL carry `trade_metric: "mfe_r"`
- **AND** its distance series SHALL be 6 on every bar.

#### Scenario: Agreement with single-trade evaluation

- **WHEN** a trade has an initial stop
- **THEN** a consumer of the projection SHALL reach the same phase on
  the same bar as the single-trade evaluation.
