## ADDED Requirements

### Requirement: Closed stop execution formula

A projected `stop_action` SHALL support the optional closed execution
semantic `stop_formula` with values `initial_r_lock` and `initial_r_trailing`.
Engine SHALL represent every legacy stop action with no formula (`None`),
omitted on the wire; a consumer MAY name that omitted case `entry_offset`
internally, but Engine SHALL NOT emit `entry_offset`.

`stop_formula` SHALL describe generic execution semantics owned by the
projection contract. It SHALL NOT contain or reproduce a strategy
`component_id`, and the rule SHALL NOT expose named raw strategy parameters.
Strategy-specific numeric values SHALL be resolved by Strategy Engine into
opaque entries of the projection's distance map.

#### Scenario: Initial-R lock projection

- **WHEN** Engine projects an `initial_r_lock_stop`
- **THEN** its stop action SHALL use `stop_formula: initial_r_lock`
- **AND** opaque distance references SHALL identify its trigger-R threshold and lock-R value.

#### Scenario: Initial-R trailing projection

- **WHEN** Engine projects an `initial_r_trailing_stop`
- **THEN** its stop action SHALL use `stop_formula: initial_r_trailing`
- **AND** opaque distance references SHALL identify its trigger-R threshold and trail-distance-R value.

#### Scenario: Strategy identity does not cross the boundary

- **WHEN** either new stop component is serialized
- **THEN** its projection rule SHALL contain neither `component_id` nor fields named `trigger_r`, `lock_r`, or `trail_distance_r`.

### Requirement: Legacy stop action wire compatibility

A legacy stop action that omits `stop_formula` SHALL keep the legacy
entry-offset meaning (Research's `entry_offset`) and SHALL continue to interpret `distance_id` as the per-bar absolute price offset
from entry. Engine SHALL omit the new formula and trigger-reference fields when
serializing existing `break_even_stop` and `lock_profit_stop` rules.

#### Scenario: Decode old projection

- **WHEN** a consumer receives a pre-change stop action containing only kind,
  rule id, activation phase, and distance id
- **THEN** it SHALL execute that action with the legacy entry-offset meaning.

#### Scenario: Serialize existing specification

- **WHEN** Engine projects a specification containing only legacy stop rules
- **THEN** its stop-action wire objects SHALL be byte-identical to their pre-change representation.

### Requirement: Initial-R projection execution inputs

For `initial_r_lock` and `initial_r_trailing`, the opaque trigger distance
SHALL be compared with the consumer-local `mfe_r`. The action distance SHALL
be interpreted as a multiple of consumer-local frozen initial risk. The
consumer SHALL derive candidate prices from its entry, monotonic MFE, side,
and frozen initial risk according to `stop_formula` and SHALL require no raw
strategy parameter.

#### Scenario: One projection serves trades with different risk distances

- **WHEN** two trades consume the same initial-R stop projection but have different entry-to-initial-stop distances
- **THEN** each trade SHALL derive its candidate using its own frozen initial risk.

#### Scenario: Initial risk missing

- **WHEN** a trade has no positive frozen initial risk
- **THEN** either initial-R stop formula SHALL be unavailable for that trade and produce no candidate.

### Requirement: Stop projection parity

For each trade side and entry, candidate stop prices, effective stop timeline,
update attribution, and next-bar boundaries produced from the historical
projection SHALL equal the single-trade managed evaluator supplied with the
same initial stop.

#### Scenario: Lock and trailing parity corpus

- **WHEN** the parity corpus exercises initial-R lock and trailing rules across multiple entries and both sides
- **THEN** every projected effective stop price, update bar, and rule id SHALL equal the single-trade oracle.
