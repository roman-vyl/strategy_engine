# Proposal: EMA Pullback Managed Policy v1

Port the strategy-owned managed exit semantics from BBB into Strategy Engine without moving fill simulation or exchange execution.

The change adds a coarse-grained managed replay endpoint for one already-open logical trade. Strategy Engine loads the requested market range, calculates required indicators, replays ordered phase rules and management policies, and returns bar-aligned decisions and events.

BBB remains responsible for OHLC hit arbitration, fills, fees, trade closure, PnL and report construction. Future live runtime remains responsible for order orchestration and delivery to Abi. **Decision under review:** checkpoint/replay and reconciliation ownership were assumptions of an earlier stateful incremental Runtime design and must be re-evaluated against the approved standalone Strategy Runtime architecture before implementation.
