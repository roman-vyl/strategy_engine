## ADDED Requirements

### Requirement: Stop action basis

`ManagedStopActionRule` SHALL carry an optional
`stop_basis: "lock_r" | "trail_r"`. It SHALL be omitted from the wire
when absent, and it SHALL be absent for every component other than
`r_stop`, so projections of existing specs are unchanged.

For `r_stop` the projection SHALL emit `stop_basis` equal to the mode
(`lock` → `lock_r`, `trail` → `trail_r`) and a distance series equal to
`lock_r` or `trail_r` on every bar.

The consumer SHALL compute the candidate as:

- no `stop_basis`: `entry ± distance` (unchanged);
- `lock_r`: `entry ± distance × initial_risk`;
- `trail_r`: `mfe_price ∓ distance × initial_risk`;

with the sign by side, `initial_risk` frozen at entry as for `mfe_r`,
and SHALL discard an R-based candidate that is not tighter than the
initial stop or that has no initial risk.

#### Scenario: Existing projection unchanged

- **WHEN** a managed spec has no `r_stop` rule
- **THEN** its serialized projection SHALL be byte-identical to the one
  before this change.

#### Scenario: Agreement with single-trade evaluation

- **WHEN** a trade with an initial stop is replayed with `r_stop`
- **THEN** a consumer of the projection SHALL reach the same active stop
  on the same bar as the single-trade evaluation.
