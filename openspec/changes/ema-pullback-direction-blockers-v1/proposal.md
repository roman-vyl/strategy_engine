# Proposal: EMA Pullback Direction and Blockers v1

## Why

The Strategy Engine already owns feature planning, indicators, contexts, and context-consumption evidence, but still stops before local trading components. BBB currently evaluates direction and blockers inside `build_signals_from_spec()`. This change moves that exact semantic slice into the independent engine without moving setups, triggers, risk, or final entries.

## What changes

- Port `ema_anchor_stack_trend` for long and short sides.
- Port all current blocker implementations: `no_blockers`, `counter_candle_blocker`, `rsi_lookback_extreme_blocker`, and `trend_strength_episode_blocker`.
- Preserve intrinsic blocker traces and counters.
- Apply `htf_regime_gate` after intrinsic blocker evaluation, matching BBB ordering.
- Compose all blockers with logical AND per side.
- Expose `pre_setup_allowed = direction AND blockers_ok` as evidence, not as a final entry signal.
- Preserve one MDS range read and reuse the existing FeatureFrame and ContextBundle.

## Out of scope

- setups;
- triggers;
- risk filters;
- final entries;
- exits and managed execution;
- incremental runtime.
