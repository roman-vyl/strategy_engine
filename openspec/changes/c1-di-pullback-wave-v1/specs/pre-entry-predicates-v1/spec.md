## ADDED Requirements

### Requirement: Segment end at the touch bar

A segment MAY end at `touch`, the touch bar of the selected touch row. `to: touch` SHALL be allowed only with `touch: previous`
and `from: peak`; any other combination SHALL be rejected. The segment SHALL span the peak bar and the touch bar of the touch row
before the current one in the same episode, both ends inclusive, and SHALL be missing on the first touch of an episode.

#### Scenario: Previous pullback

- **WHEN** the current touch is the second of its episode and a segment is `peak → touch`, `touch: previous`
- **THEN** it SHALL span the peak bar and the touch bar of the first touch.

#### Scenario: Touch end rejected

- **WHEN** `to: touch` is used with `touch: current` or with `from: origin`
- **THEN** static validation SHALL reject the spec.

### Requirement: Counter-trade directional index wave ratio

A ratio of a `from_start` segment `peak → current` of `touch` `current` over a `from_start` segment `peak → touch` of `touch`
`previous`, both over a `by_side` series with `long = di_minus` and `short = di_plus`, and `right_floor` 1e-6, SHALL be missing
when the previous pullback's value is not greater than 1e-6 or when either side is missing. A current value not greater than 0
SHALL stay a value.

#### Scenario: Violent pullback

- **WHEN** the current pullback's counter-DI rise is 2 and the previous pullback's rise is 1
- **THEN** the ratio SHALL be 2 and a `range` with `max` 1.5 and `bounds exclusive` SHALL block the bar.

#### Scenario: Previous pullback without a rise

- **WHEN** the previous pullback's value is 0, negative or at most 1e-6
- **THEN** the ratio SHALL be missing and the entry SHALL not be blocked.

#### Scenario: Short side

- **WHEN** the evaluated side is short
- **THEN** the series SHALL be `di_plus`, not negated.
