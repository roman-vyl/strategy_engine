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
