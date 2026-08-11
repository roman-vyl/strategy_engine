# Design: ATR Distance Indicator Vertical Slice v1

## Legacy semantics

BBB creates the base ATR feature first and then computes `atr_distance` as:

```python
result[distance_id] = result[atr_id].astype(float) * float(multiplier)
```

The derived series inherits every null/warmup position from the ATR series. No additional resampling, MDS read, or warmup is introduced.

## Public contract

A planned `atr_distance` feature SHALL have:

- `source=null`;
- one positive numeric `multiplier` parameter;
- exactly one dependency;
- a dependency that points to an earlier `atr` feature;
- the same declared timeframe as its ATR dependency.

The dependency output ID and derived output ID remain caller-owned for BBB FeaturePlan compatibility.

## Execution

The range evaluator reads the already serialized ATR dependency, multiplies non-null values, serializes the derived values with the existing Decimal-text policy, and copies the ATR validity metadata. The evaluator SHALL NOT perform an additional market-data read or a second ATR calculation.
