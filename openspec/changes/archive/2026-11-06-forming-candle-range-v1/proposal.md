## Why

Case 178 requires the observed range of a forming HTF candle divided by the previous HTF candle's Wilder ATR. Existing forming_candle provides signed body only; the missing capability must be reusable rather than a filter-specific branch.

## What Changes

- Add optional field: range to the existing forming_candle operand; omitted field preserves legacy signed body behavior (explicit body is equivalent).
- Range includes the evaluation base candle, uses only observed highs/lows, and is side independent.
- Range denominator is the ATR of the preceding HTF bucket throughout the current bucket, including its final base candle.
- Integrate validation, feature requirements, history planning, cache identity, evidence and manifest documentation.

## Capabilities

### New Capabilities

### Modified Capabilities

- `pre-entry-predicates-v1`: add the forming candle range mode with causal normalization and compatibility guarantees.

## Impact

Engine forming_candle evaluator, operand parsing and identities, calculation history planning and tests. No new market data source, ATR implementation, voting calibration or filter-specific operand. Cases 248 and 280, SPOT/PERP and deployment are excluded.
