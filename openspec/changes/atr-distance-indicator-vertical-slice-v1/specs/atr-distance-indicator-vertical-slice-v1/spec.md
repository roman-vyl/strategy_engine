# ATR Distance Indicator Vertical Slice v1 Specification

## Requirement: derived ATR dependency

`atr_distance` SHALL derive from exactly one earlier ATR feature in the same plan. The dependency SHALL use the same timeframe and SHALL be resolved by output ID.

## Requirement: calculation

For every bar with a valid ATR dependency value, the output SHALL equal `ATR × multiplier`. Null ATR values SHALL remain null. The multiplier SHALL be a positive finite numeric value and booleans SHALL be rejected.

## Requirement: no duplicate work

Evaluation SHALL NOT load market data again, calculate ATR again, resample again, or introduce a second warmup. The derived feature SHALL inherit the ATR feature validity metadata.

## Requirement: compatibility

Caller-owned output IDs, dependency IDs, plan hashing, Decimal-text serialization, range API, and completed HTF ATR semantics SHALL remain unchanged.
