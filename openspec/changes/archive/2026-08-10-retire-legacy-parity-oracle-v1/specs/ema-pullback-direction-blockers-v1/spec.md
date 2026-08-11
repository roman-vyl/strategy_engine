## REMOVED Requirements

### Requirement: BBB parity
**Reason**: This requirement mandated golden tests comparing masks and blocker reason traces directly against the copied BBB implementations. The copied BBB source is being removed; native direction/blocker tests already cover the same masks and stateful reason traces independently.
**Migration**: Native tests under `tests/test_ema_pullback_direction_blockers.py` remain the verification layer. No replacement parity gate is introduced.
