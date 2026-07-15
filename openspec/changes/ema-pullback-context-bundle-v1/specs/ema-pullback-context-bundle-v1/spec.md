# EMA Pullback Context Bundle v1 Specification

## Requirement: Strategy-owned context construction

The Strategy Engine SHALL construct declared `ema_pullback` context providers internally after Indicator Engine feature evaluation. External callers SHALL NOT provide precomputed context masks or state series.

## Requirement: BBB-compatible HTF context semantics

For an `htf_context` provider, the engine SHALL classify each base-grid position as:

- `up` when fast EMA is greater than anchor EMA and anchor EMA is greater than slow EMA;
- `down` when fast EMA is less than anchor EMA and anchor EMA is less than slow EMA;
- `neutral` otherwise.

Null, missing, or non-ready values SHALL resolve to neutral. Required feature columns absent from the FeatureFrame SHALL produce an all-neutral provider output.

## Requirement: One bundle per evaluation

The engine SHALL construct one ContextBundle per strategy range evaluation and SHALL reuse that bundle for future signal and exit consumers. Context providers SHALL NOT trigger additional Market Data Service reads or indicator calculations.

## Requirement: Stable API result

The strategy range response SHALL expose an aligned context time axis and, for each context reference, provider metadata, state values, and boolean up/down/neutral masks.

The strategy catalog and evaluation result SHALL advertise `contexts_ready=true` and `decisions_ready=false` until trading components are ported.

## Requirement: Scope boundary

This change SHALL NOT implement context-consumption policy evaluation, trade-side regime resolution, blockers, setups, triggers, entries, exits, managed execution, or runtime incremental processing.

## Requirement: Golden parity

Acceptance SHALL include direct execution of copied BBB context code and exact comparison of state and mask outputs, including warmup and neutral fallback cases.
