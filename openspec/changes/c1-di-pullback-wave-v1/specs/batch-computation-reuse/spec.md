## ADDED Requirements

### Requirement: Touch end identity

`to: next_origin` SHALL enter the identity of a segment as its end point, so a `peak → next_origin` segment never shares a node with a
`peak → current` or `peak → touch` segment. A spec without the next-origin end point SHALL keep every segment identity and result it had before this
change.

#### Scenario: Unchanged identities

- **WHEN** a spec has no `to: next_origin`
- **THEN** its segment identities and results SHALL equal those before this change.

### Requirement: Counter-trade waves share nodes

Candidates that differ only in `min` or `max` of the range over a C1 ratio SHALL share both segments and the ratio. C1.1 and C1.2
SHALL share the counter-trade directional index columns and the touch points, and SHALL share the DI columns with B2 when the
period is equal.

#### Scenario: Band candidates

- **WHEN** a batch contains candidates that differ only in a bound of one range over a ratio of two segments
- **THEN** the directional index columns, both segments and the ratio SHALL each be computed once per batch per side.
