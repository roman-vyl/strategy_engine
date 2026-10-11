## ADDED Requirements

### Requirement: History policy for segment and ratio operands

A `compare` or `range` predicate whose operands include a segment or a ratio SHALL contribute the explicit
zero-additional-history entry of a current-bar predicate. The bars a segment reads back to `S*` of the current touch (and one
bar earlier for `change`) lie inside the history of the episode it names, which every declared episode already requires
(`history_bars`), and the warm-up of the series is counted by the per-feature policy.

#### Scenario: Band filter child

- **WHEN** a composite child is a `range` over a ratio of two segments on episode `trend`
- **THEN** the child SHALL contribute a zero-additional entry
- **AND** the requirements SHALL still include `history_bars` of `trend` and the EMA warm-up of the series it reads.
