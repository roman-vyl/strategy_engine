## REMOVED Requirements

### Requirement: Golden parity
**Reason**: This requirement mandated executing the copied BBB `features/calculations.py` as a comparison oracle. The copied BBB source is being removed; native ATR tests already cover base/HTF output and null/warmup positions independently.
**Migration**: Native tests under `tests/test_atr_indicator.py` and `tests/test_atr_indicator_api.py` remain the verification layer. No replacement parity gate is introduced.
