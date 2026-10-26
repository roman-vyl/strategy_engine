## MODIFIED Requirements

### Requirement: Accept optional open interest on historical candles

Each candle of the response MAY carry an `open_interest` field whose value is finite decimal text or `null`; an absent field and `null` SHALL mean the same. Strategy Engine SHALL validate a present non-null value and SHALL carry it on the market bar as `open_interest` (a Decimal, or none when absent or `null`). The value SHALL NOT change the parsed OHLCV values, the propagated hash, or the result of any strategy that does not read open interest. Any other unknown field SHALL still make the response malformed.

#### Scenario: Candles carry open interest

- **WHEN** the historical response carries `open_interest` as decimal text on some candles and `null` or no field on others
- **THEN** Strategy Engine SHALL accept the response
- **AND** each bar SHALL carry the Decimal value of its own candle, or none where the candle has `null` or no field
- **AND** the OHLCV values, the results of strategies that do not read open interest and the propagated `market_data_hash` SHALL be the same as for the same response without `open_interest`.

#### Scenario: Open interest value is malformed

- **WHEN** a candle carries `open_interest` that is not finite decimal text and not `null`
- **THEN** Strategy Engine SHALL reject the response as `upstream_contract_error`.
