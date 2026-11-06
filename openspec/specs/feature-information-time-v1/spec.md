# feature-information-time-v1 Specification

## Purpose
TBD - created by archiving change feature-information-time-v1. Update Purpose after archive.
## Requirements
### Requirement: Explicit information time for completed features
Standalone feature requests SHALL accept availability bar_open or bar_close,
with bar_open as default. For HTF bar_close the evaluator SHALL expose only
buckets completed at or before the selected base candle close. It SHALL NOT
require or read a following base candle. Base features retain their existing
closed-bar computation. Derived features SHALL inherit dependency timing.

#### Scenario: Peak closes an HTF bucket
- **WHEN** peak P is the last 5m bar of a 4h bucket and ATR4h requests bar_close
- **THEN** at_point(peak) SHALL use the ATR including that completed 4h bucket
- **AND** a prefix ending at P SHALL produce the same value as full history.

#### Scenario: Peak lies inside an HTF bucket
- **WHEN** P closes before the HTF bucket ends
- **THEN** bar_close SHALL expose the preceding completed bucket only.

### Requirement: Backward compatible identities
Default feature labels, canonical payloads and semantic identities SHALL remain
unchanged. Nondefault availability SHALL have a distinct label and identity.
Invalid availability SHALL fail closed.

#### Scenario: Both variants requested together
- **WHEN** open and close availability are requested for the same indicator
- **THEN** both columns SHALL coexist without cache or label collision.

