# Proposal: ATR Distance Indicator Vertical Slice v1

Port BBB's derived `atr_distance` feature into the independent Indicator Engine without changing dependency ordering, multiplier semantics, warmup propagation, timeframe identity, or caller-owned output IDs.

`atr_distance` is not a second market-data calculation. It consumes one earlier ATR feature in the same `IndicatorPlan` and multiplies each valid ATR value by a positive multiplier.
