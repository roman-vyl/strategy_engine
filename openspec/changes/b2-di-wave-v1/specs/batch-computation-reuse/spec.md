## ADDED Requirements

### Requirement: Touch, side series, from-start and ratio floor identity

`touch`, a `by_side` series and `value: from_start` SHALL enter the identity of a segment, and `right_floor` that of a ratio, only when set, so that
the identity of every A1 and A2 segment and ratio is unchanged. A `by_side` series SHALL enter it with the identities of both features.

#### Scenario: Unchanged identities

- **WHEN** a spec has no `touch`, no `by_side` and no `from_start`
- **THEN** its segment identities and results SHALL equal those before this change.

### Requirement: Directional index waves share nodes

Candidates that differ only in `min` or `max` of the range over a B2 ratio SHALL share both segments and the ratio. B2.1 and B2.2
SHALL share the directional index columns and the touch points.

#### Scenario: Band candidates

- **WHEN** a batch contains candidates that differ only in `min` of one range over a ratio of two segments
- **THEN** the directional index columns, both segments and the ratio SHALL each be computed once per batch per side.

### Requirement: From-start cost

`sum` and `mean_per_bar` of `from_start` SHALL cost O(n) per series; `max` and `min` SHALL cost at most O(n log n) per series and
O(1) per bar, independent of leg length. A `previous` segment SHALL add no pass over bars.

#### Scenario: No compute regression

- **WHEN** a spec has no `touch`, `by_side` or `from_start`
- **THEN** no extra node SHALL be created and no extra work done.
