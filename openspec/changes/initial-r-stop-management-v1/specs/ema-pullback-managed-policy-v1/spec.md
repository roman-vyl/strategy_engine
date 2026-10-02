## MODIFIED Requirements

### Requirement: Required inputs

The request SHALL include the canonical strategy input
(`strategy-evaluation-canonical-input-v1`: `strategy_id`, `raw_spec`),
canonical market range, trade identity, side, entry timestamp, and entry
price. It MAY include `initial_stop_price` for policy that uses the trade's
frozen initial risk. It SHALL NOT include `strategy_version`, caller-supplied
`instance_id`, or `compatibility_profile`.

When supplied, `initial_stop_price` SHALL be finite and positive, SHALL differ
from entry price, and SHALL be below entry for a long trade or above entry for
a short trade. The evaluator SHALL freeze `initial_risk` as
`|entry_price - initial_stop_price|`. When it is absent, policy that requires
initial risk SHALL fail closed while policy that does not require it SHALL be
unchanged.

#### Scenario: Submit managed replay inputs

- **WHEN** managed replay is requested without an initial stop
- **THEN** the request SHALL remain valid
- **AND** R-dependent phase and stop rules SHALL remain unmet.

#### Scenario: Submit initial risk basis

- **WHEN** managed replay is requested with a side-correct `initial_stop_price`
- **THEN** R-dependent phase and stop rules SHALL use the resulting frozen initial risk.

#### Scenario: Invalid initial stop

- **WHEN** `initial_stop_price` is non-finite, non-positive, equal to entry, or on the profit side of entry
- **THEN** the request SHALL be rejected before managed replay begins.

#### Scenario: Legacy envelope field is supplied

- **WHEN** a managed-replay request's `strategy` object contains
  `strategy_version`, `instance_id`, or `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  replay begins.

## ADDED Requirements

### Requirement: Initial-R lock stop

A stop-management rule with `component_id: initial_r_lock_stop` SHALL require
finite numeric `trigger_r` and `lock_r` parameters. With
`initial_risk = |entry_price - initial_stop_price|` and
`mfe_r = |mfe_price - entry_price| / initial_risk`, it SHALL produce no
candidate until both its phase activation gate is met and `mfe_r >= trigger_r`.

Once eligible, its candidate SHALL be:

- long: `entry_price + lock_r * initial_risk`;
- short: `entry_price - lock_r * initial_risk`.

#### Scenario: Lock four R after six R

- **GIVEN** a long entry at 100, initial stop at 98, `trigger_r: 6`, and `lock_r: 4`
- **WHEN** monotonic MFE reaches 112
- **THEN** the rule SHALL propose a stop at 108.

#### Scenario: Short lock mirrors long

- **GIVEN** a short entry at 100, initial stop at 102, `trigger_r: 6`, and `lock_r: 4`
- **WHEN** monotonic MFE reaches 88
- **THEN** the rule SHALL propose a stop at 92.

#### Scenario: Trigger not reached

- **WHEN** the rule's phase gate is met but monotonic MFE remains below `trigger_r`
- **THEN** the rule SHALL produce no stop candidate.

### Requirement: Initial-R trailing stop

A stop-management rule with `component_id: initial_r_trailing_stop` SHALL
require finite numeric `trigger_r` and `trail_distance_r` parameters. It SHALL
produce no candidate until both its phase activation gate is met and
`mfe_r >= trigger_r`. Once eligible, its candidate SHALL follow monotonic MFE:

- long: `mfe_price - trail_distance_r * initial_risk`;
- short: `mfe_price + trail_distance_r * initial_risk`.

The candidate SHALL use the accumulated best favorable extreme, not current
close and not a non-monotonic single-bar extreme.

#### Scenario: Long trailing sequence

- **GIVEN** a long trade with `trigger_r: 6` and `trail_distance_r: 2`
- **WHEN** monotonic MFE advances through 6R, 7R, 8R, and 11.5R
- **THEN** the candidate stop SHALL advance through 4R, 5R, 6R, and 9.5R.

#### Scenario: Short trailing mirrors long

- **GIVEN** a short trade with `trigger_r: 6` and `trail_distance_r: 2`
- **WHEN** its favorable low advances from 6R to 7R
- **THEN** its candidate stop SHALL advance from 4R to 5R on the short profit side.

#### Scenario: Favorable extreme does not advance

- **WHEN** price retraces without setting a new favorable extreme
- **THEN** the trailing candidate SHALL NOT move backward.

### Requirement: Initial-R stop parameter validity

`trigger_r` SHALL be strictly positive. `lock_r` SHALL satisfy
`0 <= lock_r <= trigger_r`. `trail_distance_r` SHALL satisfy
`0 < trail_distance_r <= trigger_r`. All values SHALL be finite numbers.
An initial-R stop SHALL produce no candidate when initial risk is absent or
non-positive.

These parameter checks SHALL run at the strategy-specification validation
boundary (static semantics), so an invalid configuration is rejected before
feature planning, indicator evaluation, projection building, or replay. The
evaluators SHALL reuse the same shared resolver.

#### Scenario: Break-even specialization

- **WHEN** `initial_r_lock_stop` is configured with `lock_r: 0`
- **THEN** its eligible candidate SHALL equal entry price.

#### Scenario: Invalid lock parameters

- **WHEN** lock R is negative, exceeds trigger R, or either value is non-finite
- **THEN** strategy-specification validation SHALL reject the specification before any evaluation.

#### Scenario: Invalid trailing parameters

- **WHEN** trail distance is non-positive, exceeds trigger R, or either value is non-finite
- **THEN** strategy-specification validation SHALL reject the specification before any evaluation.

#### Scenario: Initial risk unavailable

- **WHEN** an initial-R stop is evaluated without positive frozen initial risk
- **THEN** it SHALL fail closed without emitting a candidate or stop-update event.

### Requirement: Initial-R stops reuse managed stop arbitration and timing

Initial-R candidates SHALL participate in the same ordered set of active stop
candidates as every existing managed stop. The effective stop SHALL tighten
only: the greatest candidate wins for long and the smallest candidate wins for
short, including the stop already active before the current bar. A candidate
that does not tighten the effective stop SHALL NOT change active rule
attribution or emit an active-stop update. A stop calculated from bar N SHALL
be effective from bar N+1 and SHALL NOT execute against bar N.

#### Scenario: Multiple stop policies are eligible

- **WHEN** legacy and initial-R stop rules are eligible on the same bar
- **THEN** the most protective candidate for the trade side SHALL become effective.

#### Scenario: Non-tightening trailing candidate

- **WHEN** another active stop is already more protective than a trailing candidate
- **THEN** price, rule attribution, and stop-update events SHALL remain unchanged.

#### Scenario: Decision cannot hit its source bar

- **WHEN** bar N first reaches an initial-R trigger and also crosses the resulting candidate price
- **THEN** the candidate SHALL only be executable on bar N+1 or later.

### Requirement: Legacy managed stop compatibility

`break_even_stop` and `lock_profit_stop` SHALL retain their existing public
parameters, calculations, planning, events, and outputs. The addition of
initial-R components SHALL NOT reinterpret or migrate existing rules.

#### Scenario: Existing managed specification

- **WHEN** a specification contains no initial-R stop component
- **THEN** its managed replay and live open-trade outputs SHALL be unchanged.

#### Scenario: Buffered break-even remains legacy

- **WHEN** `break_even_stop` uses a fixed or ATR buffer
- **THEN** that buffer SHALL retain its existing entry-offset semantics.
