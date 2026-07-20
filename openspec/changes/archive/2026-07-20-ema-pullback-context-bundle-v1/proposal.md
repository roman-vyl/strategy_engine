# Proposal: EMA Pullback Context Bundle v1

## Why

The Strategy Engine can already derive the BBB-compatible IndicatorPlan from a canonical `ema_pullback` spec and calculate its complete FeatureFrame. The next semantic boundary in the legacy BBB call path is construction of strategy-level contexts from the enriched feature frame.

Without this change, context providers remain owned by BBB and the strategy response stops at `features_ready`. Moving context construction now preserves the natural order of the original pipeline and prepares later blocker, setup, and exit-policy consumers without moving those consumers prematurely.

## What changes

- Add a clean Strategy Engine context module for the BBB `htf_context` provider.
- Build one ContextBundle per strategy evaluation after feature calculation.
- Preserve BBB `up`, `down`, `neutral`, and state-series semantics exactly.
- Return context data from `POST /v1/strategy-evaluations/range`.
- Advance the advertised strategy evaluation stage from `features_ready` to `contexts_ready`.
- Keep context-consumption policies and trading decisions out of scope.

## Scope exclusions

This change does not port:

- `htf_regime_gate` consumption;
- side-relative aligned/countertrend resolution;
- exit-profile selection;
- blockers, setups, triggers, entries, or exits;
- incremental/bar-to-bar context state.
