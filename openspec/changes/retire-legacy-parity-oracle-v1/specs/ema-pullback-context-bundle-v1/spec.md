## REMOVED Requirements

### Requirement: Golden parity
**Reason**: This requirement mandated direct execution of copied BBB context code as a comparison oracle. The copied BBB source is being removed; native context tests already cover state and mask outputs, including warmup and neutral fallback, independently.
**Migration**: Native tests under `tests/test_ema_pullback_contexts.py` and `tests/test_ema_pullback_context_consumption.py` remain the verification layer. No replacement parity gate is introduced.
