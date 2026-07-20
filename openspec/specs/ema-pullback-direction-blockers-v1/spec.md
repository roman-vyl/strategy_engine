# EMA Pullback Direction and Blockers v1 Specification

## Purpose

Define side-aware direction, BBB-compatible blockers, context composition, downstream intermediate artifacts, market-read reuse, and parity for EMA Pullback.

## Requirements

### Requirement: Side-aware direction

The engine SHALL evaluate `ema_anchor_stack_trend` as `fast > anchor > slow` for long and `fast < anchor < slow` for short. Missing feature values SHALL evaluate to false.

#### Scenario: Evaluate anchor-stack direction

- **WHEN** anchor-stack direction is evaluated for a trade side
- **THEN** strict EMA order SHALL be applied in the side-appropriate direction
- **AND** missing feature values SHALL produce false.

### Requirement: Blocker parity

The engine SHALL support `no_blockers`, `counter_candle_blocker`, `rsi_lookback_extreme_blocker`, and `trend_strength_episode_blocker` with BBB-compatible semantics.

#### Scenario: Evaluate a supported blocker

- **WHEN** a strategy configures any supported blocker component ID
- **THEN** the engine SHALL return its BBB-compatible intrinsic allow mask and evidence.

### Requirement: RSI memory semantics

The RSI blocker SHALL mark an extreme when RSI crosses the side-specific threshold and SHALL block while any extreme exists inside the inclusive rolling lookback window with `min_periods=1` semantics.

#### Scenario: Remember an RSI extreme

- **WHEN** RSI crosses the side-specific threshold
- **THEN** the blocker SHALL reject the current bar and every bar whose inclusive lookback still contains that extreme.

### Requirement: Trend-strength episode semantics

The ADX/DMI blocker SHALL search backward for the most recent qualifying bar inside `peak_lookback_bars`, enforce peak age, current ADX, optional DI alignment, and optional opposite-DI flip rules, and SHALL expose BBB-compatible blocked reasons.

#### Scenario: Evaluate a trend-strength episode

- **WHEN** the ADX/DMI blocker evaluates a bar
- **THEN** it SHALL apply the configured recent-peak, age, current-strength, alignment, and flip rules
- **AND** SHALL expose the corresponding BBB-compatible blocked reason.

### Requirement: Context ordering

Any `htf_regime_gate` SHALL be applied after the intrinsic blocker mask. The final blocker mask SHALL be the logical AND of intrinsic and context masks.

#### Scenario: Apply a context gate to a blocker

- **WHEN** a blocker has an HTF regime gate
- **THEN** the engine SHALL evaluate the intrinsic blocker first
- **AND** SHALL combine intrinsic and context masks with logical AND.

### Requirement: Composition boundary

All final blocker masks SHALL be AND-composed per side. This module SHALL expose `pre_setup_allowed = direction AND blockers_ok` as an intermediate artifact for downstream setup, trigger, and entry evaluation.

#### Scenario: Compose direction and blockers

- **WHEN** all blockers for one side have been evaluated
- **THEN** their final masks SHALL be AND-composed into `blockers_ok`
- **AND** `pre_setup_allowed` SHALL equal direction AND `blockers_ok`.

### Requirement: No extra market read

Direction and blocker evaluation SHALL reuse the market and feature artifact from the existing strategy range evaluation. It SHALL NOT perform another Market Data Service request.

#### Scenario: Evaluate direction and blockers in a range pipeline

- **WHEN** direction and blockers consume an existing FeatureFrame
- **THEN** they SHALL reuse its features and market bars
- **AND** SHALL NOT request market data again.

### Requirement: BBB parity

Golden tests SHALL compare the new masks and stateful blocker reason trace directly with the copied BBB implementations.

#### Scenario: Run direction and blocker parity

- **WHEN** representative direction and blocker fixtures are evaluated
- **THEN** masks and stateful blocker reason traces SHALL match copied BBB implementations.
