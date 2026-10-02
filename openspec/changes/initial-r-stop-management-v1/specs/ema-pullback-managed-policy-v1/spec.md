## ADDED Requirements

### Requirement: Stop component `r_stop`

A stop-management rule `{component_id: "r_stop", params: {mode, ...}}`
SHALL propose a stop price measured in the trade's initial R:

- `mode: "lock"` with `lock_r` (finite, `>= 0`): `stop_R = lock_r`;
- `mode: "trail"` with `trail_r` (finite, `> 0`):
  `stop_R = |mfe_price - entry_price| / initial_risk - trail_r`.

The candidate price SHALL be `entry_price + stop_R × initial_risk` for
long and `entry_price - stop_R × initial_risk` for short, where
`initial_risk = |entry_price - initial_stop_price|` is fixed at entry
and `mfe_price` is the one `mfe_r` uses through the current bar.

- The rule SHALL be gated only by `activate_when.phase_at_least`.
- The candidate SHALL join the existing selection and ratchet: the
  tightest active candidate is chosen and the active stop never moves
  away from the market.
- A candidate that is not tighter than the initial stop SHALL be
  discarded.
- Without an initial stop, or with a non-positive initial risk, the
  rule SHALL propose no candidate on any bar.
- A missing or unknown `mode`, or an invalid `lock_r` / `trail_r`,
  SHALL be rejected as an invalid request.
- The component SHALL need no planned feature and no history window.
- `break_even_stop` and `lock_profit_stop` SHALL be unchanged.

#### Scenario: Lock after the trigger

- **GIVEN** a long entry at 100, initial stop 98, a phase rule
  `mfe_r >= 6` to `proven` and `r_stop{lock, lock_r: 4}` active from
  `proven`
- **WHEN** the best price reaches 112 on bar N
- **THEN** the active stop SHALL become 108, effective from bar N+1
- **AND** it SHALL stay 108 while the best price rises further.

#### Scenario: Trail follows the best price and never moves back

- **GIVEN** a long entry at 100, initial stop 98 and
  `r_stop{trail, trail_r: 2}` active from `proven` (`mfe_r >= 6`)
- **WHEN** the best price reaches 112, then 114, then the price falls
  to 110
- **THEN** the active stop SHALL be 108, then 110, and SHALL stay 110.

#### Scenario: Short mirror

- **GIVEN** a short entry at 100, initial stop 102 and
  `r_stop{trail, trail_r: 2}` active
- **WHEN** the best price reaches 88
- **THEN** the active stop SHALL be 92.

#### Scenario: Break-even shorthand

- **GIVEN** a trade with an initial stop
- **WHEN** one spec uses `break_even_stop{buffer_type: none, buffer: 0}`
  and another `r_stop{lock, lock_r: 0}`, with the same activation
- **THEN** their active-stop timelines SHALL be identical.

#### Scenario: No initial stop

- **WHEN** the evaluation carries no initial stop
- **THEN** an `r_stop` rule SHALL never move the active stop.
