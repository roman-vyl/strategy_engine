# ATR Distance Indicator Vertical Slice v1

## Purpose

This slice ports the last derived indicator feature currently emitted by the BBB EMA-pullback FeaturePlan: `atr_distance`.

## BBB source behavior

BBB first calculates an ATR series and then creates the distance series using:

```python
out[distance_feature_id] = out[base_atr_feature_id].astype(float) * multiplier
```

The derived feature does not read OHLCV, resample data, calculate ATR, or create its own warmup.

## New contract

```json
{
  "output_id": "atr_close_base_14_x2",
  "kind": "atr_distance",
  "timeframe": "base",
  "source": null,
  "parameters": {"multiplier": 2.0},
  "dependencies": ["atr_close_base_14"]
}
```

Validation requires the dependency to:

1. exist in the same plan;
2. appear before the derived feature;
3. be an `atr` feature;
4. declare the same timeframe.

## Runtime behavior

The range evaluator reuses the already calculated ATR output. Valid values are multiplied and serialized using the existing Decimal-text policy. Null positions and `Validity` are copied from the ATR dependency.

## Parity coverage

Golden tests execute the preserved BBB calculations module directly for:

- base ATR period 3 × 0.5;
- base ATR period 14 × 2.25;
- completed 1h ATR period 2 × 1.75.

The new engine matches all values and null positions bar by bar.

## Architectural consequence

Indicator Engine now supports every indicator kind currently listed by the copied BBB `features/plan.py`:

- `ema`;
- `atr`;
- `atr_distance`;
- `rsi`;
- `adx`;
- `di_plus`;
- `di_minus`.

The next seam is no longer another formula. It is the semantic port of `StrategySpec → FeaturePlan`, so external callers can submit only the strategy instance/spec plus market range.
