## ADDED Requirements

### Requirement: MACD feature kinds

The Indicator Engine SHALL provide three canonical feature kinds of one MACD calculation: `macd`, `macd_signal` and
`macd_hist`. For a close series `c` and parameters `fast`, `slow`, `signal`:

- `macd = EMA(c, fast) − EMA(c, slow)`;
- `macd_signal = EMA(macd, signal)`;
- `macd_hist = macd − macd_signal`;

where `EMA(x, n)` is the Engine's EMA, `x.ewm(span=n, adjust=False).mean()`. The three kinds SHALL share one computation
per evaluation for equal timeframe and parameters.

#### Scenario: Histogram matches an independent implementation

- **WHEN** `macd_hist` with `fast` 48, `slow` 78, `signal` 48 is evaluated on a 5m close series
- **THEN** every value SHALL equal the independent pandas computation of the formula above to 1e-12.

#### Scenario: One computation for the three kinds

- **WHEN** a plan requests `macd`, `macd_signal` and `macd_hist` with equal timeframe and parameters
- **THEN** the two EMAs and the signal EMA SHALL be computed once for that evaluation.

### Requirement: MACD plan validation

Each MACD kind SHALL require `source = close`, exactly the parameters `fast`, `slow`, `signal`, each a strict positive
integer, `fast < slow`, and no dependencies.

#### Scenario: Reject an invalid MACD feature

- **WHEN** a MACD feature has another source, a missing, extra, non-integer or non-positive parameter, `fast ≥ slow`, or a
  dependency
- **THEN** validation SHALL reject it before market data is loaded.

### Requirement: MACD labels and identity

The column label SHALL be `<kind>_close_<timeframe>_<fast>_<slow>_<signal>`. The node identity SHALL carry the timeframe,
the source and `fast`, `slow`, `signal`.

#### Scenario: Different signal period

- **WHEN** two `macd_hist` features differ only in `signal`
- **THEN** their labels and identities SHALL differ.

### Requirement: Completed HTF visibility for MACD

A higher-timeframe MACD value SHALL become visible on the base grid only after its bucket is complete, through the existing
completed-bar alignment.

#### Scenario: Incomplete 1h bucket

- **WHEN** a 1h `macd_hist` bucket has not completed
- **THEN** its value SHALL NOT be visible on the base grid.

### Requirement: Public MACD capability

The catalog, schema and readiness APIs SHALL advertise `macd`, `macd_signal` and `macd_hist`. The range evaluation API SHALL
return them as decimal text or `null` with deterministic validity metadata, like every other kind. Each kind SHALL be
usable as a predicate feature operand without any change to the predicate layer.

#### Scenario: MACD as a predicate operand

- **WHEN** a `compare` predicate references `macd_hist` on `1h` with `{fast: 12, slow: 26, signal: 9}` `>` 0
- **THEN** the spec SHALL be valid and the feature SHALL be planned as a canonical plan column.
