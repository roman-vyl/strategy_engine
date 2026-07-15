# Specification: EMA Pullback Feature Plan v1

## Requirement: Caller supplies strategy semantics, not indicator plans

The public strategy boundary SHALL accept a strategy envelope. Feature discovery SHALL occur inside Strategy Engine. A BBB caller SHALL NOT need to construct or submit an IndicatorPlan for strategy evaluation.

## Requirement: Canonical BBB spec compatibility

Version 1 SHALL accept the canonical JSON shape produced by BBB `strategy_spec_to_dict`. Unsupported or malformed structures SHALL fail with a structured 4xx response and SHALL NOT silently omit requested features.

## Requirement: Exact feature discovery parity

The planner SHALL preserve BBB feature IDs, insertion order, deduplication, ATR-distance dependencies, and all lookup mappings for anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI.

## Requirement: Honest capability advertisement

The strategy catalog SHALL advertise `supports_feature_planning=true` and `supports_range_evaluation=false`. Full strategy range evaluation SHALL continue returning `501 unsupported_capability` until decision semantics are ported.

## Requirement: No legacy production imports

Production code SHALL NOT import from `legacy_source` or BBB packages. Golden tests MAY load copied BBB code only as the parity oracle.
