## ADDED Requirements

### Requirement: History policy for k-bar segment values

A predicate whose operands include a segment with `value: change_over` SHALL contribute an explicit entry of `span` additional
bars, because the segment reads `span` bars before the window start. Every other segment keeps the zero-additional entry of
A1.

#### Scenario: Peak hit branch

- **WHEN** a composite child is a `range` over a ratio of two segments with `span` 3
- **THEN** the child SHALL contribute an entry of 3 additional bars
- **AND** the requirements SHALL still include `history_bars` of the episode and the EMA warm-up of the series it reads.
