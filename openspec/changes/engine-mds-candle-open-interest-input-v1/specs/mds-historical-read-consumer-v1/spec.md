## MODIFIED Requirements

### Requirement: Consume audited historical candle ranges

Strategy Engine SHALL use the MDS historical endpoint when an audited expected hash is supplied, SHALL reject malformed or mismatched MDS responses, and SHALL propagate the returned MDS-owned hash without redefining its algorithm.

Each candle of the response MAY carry an `open_interest` field whose value is finite decimal text or `null`; an absent field and `null` SHALL mean the same. Strategy Engine SHALL validate a present non-null value and SHALL otherwise ignore it: the value SHALL NOT change the parsed OHLCV bars, the FeatureFrame, any strategy result, or the propagated hash. Any other unknown field SHALL still make the response malformed.

#### Scenario: Request a range with an audited hash

- **WHEN** a strategy range request supplies `expected_market_data_hash`
- **THEN** Strategy Engine SHALL request the range through the MDS historical endpoint
- **AND** SHALL reject a malformed, incomplete, or identity-mismatched response
- **AND** SHALL propagate the MDS-owned `market_data_hash` unchanged.

#### Scenario: Candles carry open interest

- **WHEN** the historical response carries `open_interest` as decimal text on some candles and `null` or no field on others
- **THEN** Strategy Engine SHALL accept the response
- **AND** the bars, the FeatureFrame, the results and the propagated `market_data_hash` SHALL be the same as for the same response without `open_interest`.

#### Scenario: Open interest value is malformed

- **WHEN** a candle carries `open_interest` that is not finite decimal text and not `null`
- **THEN** Strategy Engine SHALL reject the response as `upstream_contract_error`.
