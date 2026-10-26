## ADDED Requirements

### Requirement: Open interest in the shared market arrays

The shared market arrays of one evaluation or range batch SHALL serve `open_interest` through the same lazily converted, cached `values` and `array` reads as the OHLCV fields: one float per bar, converted from the bar's Decimal, and NaN where the bar has no open interest. A missing value SHALL NOT be filled from another bar or replaced by zero. The OHLCV field set, the OHLCV columns and the indicator DataFrame SHALL NOT include open interest.

#### Scenario: Open interest with gaps
- **WHEN** a range has open interest on some bars and none on others
- **THEN** `array("open_interest")` is a read-only float64 array with each bar's own value and NaN on the bars without one
- **AND** repeated reads in the same evaluation return the same cached array.

#### Scenario: Existing computations are unchanged
- **WHEN** any strategy that does not read open interest is evaluated on bars that carry open interest
- **THEN** its indicator frames, intermediate results and output are bit-identical to the evaluation of the same bars without open interest.
