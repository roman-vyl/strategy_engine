## REMOVED Requirements

### Requirement: Golden parity
**Reason**: This requirement mandated executing the copied BBB EMA calculation as a comparison oracle. The copied BBB source is being removed; native EMA tests already cover base/HTF output positions independently.
**Migration**: Native tests under `tests/test_ema_indicator.py` and `tests/test_ema_indicator_api.py` remain the verification layer. No replacement parity gate is introduced.
