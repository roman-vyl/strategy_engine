## ADDED Requirements

### Requirement: Open interest as a base-bar field

The base-bar `price` operand SHALL also accept `open_interest`. Its value SHALL be the bar's own open interest, read from the shared
market arrays, and missing where the bar has none.

#### Scenario: Current open interest over its maximum

- **WHEN** a ratio has left `{price: open_interest}` = 90 000 and right `rolling_max open_interest 8640` = 120 000 on a bar
- **THEN** the ratio SHALL be 0.75 on that bar.
