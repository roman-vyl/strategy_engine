## MODIFIED Requirements

### Requirement: Evidence

The composite `SetupMask.trace` SHALL contain:

- `child:<child_id>` masks;
- `child:<child_id>:value` for a child that is a `range` predicate whose operand is a `segment` or a `ratio`: the operand
  value per bar for the evaluated side, `null` where it is missing;
- `path:<path_id>` masks;
- `path:<path_id>:at_least_count` series for paths with `at_least`;
- `winning_path`: the first True path in declared order, or null.

No other child SHALL add a value series, so the trace of a composite without such a child is unchanged.

#### Scenario: Inspect which path admitted a bar

- **WHEN** both paths are True on a bar
- **THEN** `winning_path` on that bar SHALL be the path declared first.

#### Scenario: Band filter value on the chart

- **WHEN** a composite child is a `range` over a `ratio` of two `segment` operands
- **THEN** the trace SHALL contain `child:<child_id>:value` with the ratio on every bar, `null` where it is missing
- **AND** the child mask SHALL be computed from exactly those values.
