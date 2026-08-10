## REMOVED Requirements

### Requirement: Golden parity
**Reason**: This requirement mandated executing the copied BBB calculations module as a comparison oracle. The copied BBB source is being removed; native RSI tests already cover base/HTF values and missing-value placement independently.
**Migration**: Native tests under `tests/test_rsi_indicator.py` and `tests/test_rsi_indicator_api.py` remain the verification layer. No replacement parity gate is introduced.
