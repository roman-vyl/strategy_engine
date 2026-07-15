# Specification: EMA Pullback Direction and Blockers v1

## Requirement: side-aware direction

The engine SHALL evaluate `ema_anchor_stack_trend` as `fast > anchor > slow` for long and `fast < anchor < slow` for short. Missing feature values SHALL evaluate to false.

## Requirement: blocker parity

The engine SHALL support all blocker component IDs currently consumed by BBB: `no_blockers`, `counter_candle_blocker`, `rsi_lookback_extreme_blocker`, and `trend_strength_episode_blocker`.

## Requirement: RSI memory semantics

The RSI blocker SHALL mark an extreme when RSI crosses the side-specific threshold and SHALL block while any extreme exists inside the inclusive rolling lookback window with `min_periods=1` semantics.

## Requirement: trend-strength episode semantics

The ADX/DMI blocker SHALL search backward for the most recent qualifying bar inside `peak_lookback_bars`, enforce peak age, current ADX, optional DI alignment, and optional opposite-DI flip rules, and SHALL expose BBB-compatible blocked reasons.

## Requirement: context ordering

Any `htf_regime_gate` SHALL be applied after the intrinsic blocker mask. The final blocker mask SHALL be the logical AND of intrinsic and context masks.

## Requirement: composition boundary

All final blocker masks SHALL be AND-composed per side. The engine SHALL expose `pre_setup_allowed = direction AND blockers_ok`, but SHALL NOT expose it as a completed entry signal.

## Requirement: no extra market read

Direction and blocker evaluation SHALL reuse the market and feature artifact from the existing strategy range evaluation. It SHALL NOT perform another Market Data Service request.

## Requirement: BBB parity

Golden tests SHALL compare the new masks and stateful blocker reason trace directly with the copied BBB implementations.
