## ADDED Requirements

### Requirement: Forming candle range operand
The system SHALL accept optional field body or range in forming_candle while retaining existing required episode, timeframe and ATR validation. Omitted field and body SHALL preserve existing results and canonical identity. Unknown field values MUST be rejected. Range SHALL return the observed current HTF high minus low, divided by the preceding HTF bucket's Wilder ATR, without a long/short sign multiplier. Existing episode validity gating SHALL remain in force.

#### Scenario: Side independent observed range
- **WHEN** a valid episode has observed high 110, low 100 and previous bucket ATR 5
- **THEN** range equals 2 on either side, including the evaluation candle's extrema.

#### Scenario: Backward compatibility
- **WHEN** an existing operand omits field or explicitly selects body
- **THEN** its legacy signed-body values and canonical identity are unchanged.

#### Scenario: Invalid selector
- **WHEN** field is unknown or is not a string
- **THEN** validation rejects the operand with its field path.

### Requirement: Range normalization is causal and bucket stable
The range mode MUST use only base candles from the current HTF bucket start through the evaluation candle inclusive. Its denominator SHALL remain ATR of the immediately preceding bucket even at the final base candle of the current bucket. Future candle values MUST NOT influence the result.

#### Scenario: Last base candle and rollover
- **WHEN** a 5m evaluation reaches 11:55 in the 08:00–12:00 bucket
- **THEN** the range includes 11:55 and ATR is taken through the preceding 04:00–08:00 bucket; at 12:00 the range resets and ATR advances by one bucket.

#### Scenario: Future mutation
- **WHEN** highs and lows after the evaluation candle are changed
- **THEN** the evaluated range remains unchanged.

### Requirement: Range missing data and execution integration
The system SHALL return missing for an invalid episode, incomplete current bucket prefix, nonfinite prefix extrema or missing/nonpositive ATR. Zero observed range with positive ATR SHALL return zero. History requirements SHALL cover complete bucket history and existing ATR warmup. Range SHALL be usable in predicates and weighted votes with distinct cache identity and explainable field selection, consistently across full and sufficiently warmed prefix execution.

#### Scenario: Insufficient history
- **WHEN** supplied base history starts in the middle of the current bucket
- **THEN** range is missing rather than computed from partial extrema.

#### Scenario: Zero range
- **WHEN** all observed highs and lows equal 100 and preceding ATR is positive
- **THEN** range returns zero.

#### Scenario: Manifest and prefix parity
- **WHEN** a range operand is reconstructed from a manifest and evaluated with sufficient planned history
- **THEN** its values, missing masks and voting inputs agree with full-history execution within the existing ATR numerical policy, and evidence identifies range mode.
