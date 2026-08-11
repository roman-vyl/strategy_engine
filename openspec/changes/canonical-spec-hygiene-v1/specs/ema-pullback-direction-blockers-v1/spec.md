## RENAMED Requirements

- FROM: `### Requirement: Blocker parity`
- TO: `### Requirement: Supported blockers`

## MODIFIED Requirements

### Requirement: Supported blockers

The engine SHALL support `no_blockers`, `counter_candle_blocker`, `rsi_lookback_extreme_blocker`, and `trend_strength_episode_blocker`. `no_blockers` SHALL allow every bar. `counter_candle_blocker` SHALL allow a bar only when its close is on the side-favorable side of its open (`close >= open` for long, `close <= open` for short). `rsi_lookback_extreme_blocker` and `trend_strength_episode_blocker` SHALL follow the "RSI memory semantics" and "Trend-strength episode semantics" requirements respectively.

#### Scenario: Evaluate a supported blocker

- **WHEN** a strategy configures any supported blocker component ID
- **THEN** the engine SHALL return its intrinsic allow mask and evidence per that component's defined semantics.

#### Scenario: Evaluate the counter-candle blocker

- **WHEN** the counter-candle blocker evaluates a bar
- **THEN** it SHALL allow that bar only when the close is on the side-favorable side of the open.
