# EMA Pullback Context Consumption v1 Specification

## Purpose

Define side-relative EMA Pullback context consumption, HTF regime gates, exit profiles, and the module boundary between policy evidence and downstream decisions.

## Requirements

### Requirement: Side-relative regime

For long, raw `up` SHALL resolve to `aligned` and raw `down` to `countertrend`. For short, the mapping SHALL be reversed. Unknown or neutral state SHALL resolve to `neutral`.

#### Scenario: Resolve raw context for both trade sides

- **WHEN** a raw `up`, `down`, `neutral`, or unknown context state is consumed
- **THEN** it SHALL resolve relative to the requested long or short side
- **AND** neutral or unknown state SHALL resolve to `neutral`.

### Requirement: HTF regime gate

A configured `htf_regime_gate` SHALL require a non-empty `allowed_regimes` list containing only `aligned`, `countertrend`, or `neutral`. The engine SHALL return the resolved regime and allow mask for every evaluated side.

#### Scenario: Apply an HTF regime gate

- **WHEN** a component configures a valid non-empty list of allowed regimes
- **THEN** the engine SHALL return side-relative resolved regimes and an allow mask
- **AND** invalid or empty regime lists SHALL be rejected.

### Requirement: Exit profiles

`exit_profile_by_htf_state` SHALL return long and short profile series. Disabled sides SHALL receive `neutral` for every bar.

#### Scenario: Resolve exit profiles from HTF state

- **WHEN** exit policy consumes an HTF context
- **THEN** it SHALL return long and short side-relative profile series
- **AND** any disabled side SHALL receive an all-`neutral` series.

### Requirement: Context-consumption module boundary

Context consumption SHALL emit transport-neutral policy evidence and SHALL NOT itself evaluate local blocker/setup masks or final trading decisions. Separate downstream layers MAY combine the evidence into those decisions.

#### Scenario: Build context-consumption evidence

- **WHEN** configured context consumers are evaluated
- **THEN** the module SHALL return policy evidence only
- **AND** local component masks and final decisions SHALL remain the responsibility of downstream layers.
