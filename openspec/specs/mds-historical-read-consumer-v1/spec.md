# MDS historical read consumer v1

## Purpose

Define how Strategy Engine consumes audited historical candle ranges from Market Data Service while preserving MDS ownership of the market-data hash.

## Requirements

### Requirement: Consume audited historical candle ranges

Strategy Engine SHALL use the MDS historical endpoint when an audited expected hash is supplied, SHALL reject malformed or mismatched MDS responses, and SHALL propagate the returned MDS-owned hash without redefining its algorithm.

#### Scenario: Request a range with an audited hash

- **WHEN** a strategy range request supplies `expected_market_data_hash`
- **THEN** Strategy Engine SHALL request the range through the MDS historical endpoint
- **AND** SHALL reject a malformed, incomplete, or identity-mismatched response
- **AND** SHALL propagate the MDS-owned `market_data_hash` unchanged.

### Requirement: Accept optional open interest on historical candles

A candle MAY carry `open_interest`: finite decimal text, or `null`, which means the same as an absent field. Strategy Engine SHALL validate a present value and carry it on the market bar as a Decimal, or none. It SHALL NOT change the OHLCV values, the propagated hash, or the result of a strategy that does not read open interest. Any other unknown field SHALL still make the response malformed.

#### Scenario: Candles carry open interest

- **WHEN** the historical response carries `open_interest` as decimal text on some candles and `null` or no field on others
- **THEN** Strategy Engine SHALL accept the response
- **AND** each bar SHALL carry the Decimal value of its own candle, or none where the candle has `null` or no field
- **AND** the OHLCV values, the results of strategies that do not read open interest and the propagated `market_data_hash` SHALL be the same as for the same response without `open_interest`.

#### Scenario: Open interest value is malformed

- **WHEN** a candle carries `open_interest` that is not finite decimal text and not `null`
- **THEN** Strategy Engine SHALL reject the response as `upstream_contract_error`.
