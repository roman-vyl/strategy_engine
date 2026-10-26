## MODIFIED Requirements

### Requirement: Build one complete live FeatureFrame

The loaded candle range SHALL be complete, ordered, gap-free, and aligned to the base timeframe.

Each loaded candle MAY carry an `open_interest` field whose value is finite decimal text or `null`; an absent field and `null` SHALL mean the same. Engine SHALL validate a present non-null value and SHALL carry it on the market bar as `open_interest` (a Decimal, or none when absent or `null`); it SHALL NOT change the result of any strategy that does not read open interest. Any other unknown field SHALL still be an upstream contract error.

Engine SHALL build one FeaturePlan and run the existing indicator and HTF feature calculation pipeline once per live request.

The shared acquisition path SHALL stop at the FeatureFrame boundary. The calling live use case SHALL run the existing EMA Pullback strategy evaluation exactly once over that FeatureFrame.

The resulting FeatureFrame SHALL contain target as its final bar.

#### Scenario: Complete live range

- **WHEN** MDS returns the exact complete ordered candle range
- **THEN** Engine SHALL build one FeatureFrame
- **AND** SHALL expose the target index to the calling live use case
- **AND** SHALL NOT precompute a generic strategy projection inside the shared acquisition service.

#### Scenario: Gapped or incomplete range

- **WHEN** MDS returns a gap, wrong order, wrong identity, or an incomplete final boundary
- **THEN** Engine SHALL return `upstream_contract_error`
- **AND** SHALL NOT build a partial FeatureFrame.

#### Scenario: Live candles carry open interest

- **WHEN** MDS returns the exact complete ordered candle range and some candles carry `open_interest` as decimal text or `null`
- **THEN** each market bar SHALL carry the open interest of its own candle, or none
- **AND** a strategy that does not read open interest SHALL produce the same live projection as without `open_interest`.

#### Scenario: Live open interest value is malformed

- **WHEN** a loaded candle carries `open_interest` that is not finite decimal text and not `null`
- **THEN** Engine SHALL return `upstream_contract_error`
- **AND** SHALL NOT build a partial FeatureFrame.
