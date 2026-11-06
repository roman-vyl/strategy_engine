# Forming candle range

Use `forming_candle` with `field: range`, an existing episode reference, timeframe and same-timeframe `atr_wilder` feature. Output is scalar `(observed high - observed low) / previous bucket ATR`; long and short use the same sign. The current closed base candle is included, future highs/lows excluded. Previous-bucket ATR is fixed throughout the current bucket, including its last base candle. Incomplete/gapped current bucket prefixes and invalid ATR produce missing values. Omitted field or `body` preserves legacy signed-body behavior.

Case 178 uses timeframe 4h and ATR period 14. No filter ID is embedded in Engine.
