# Proposal: EMA Pullback exit policy v1

## Why

Strategy range evaluation already returns features, contexts, component evidence, and final entry masks, but BBB still owns standard signal exits and initial stop/take policy compilation. This leaves the trading decision contract incomplete and would force BBB and the future runtime to retain duplicate exit semantics.

## What changes

- Port all current standard BBB exit components: no-signal, RSI, EMA-close-loss, EMA-cross-loss, ATR distance, and constant-USD distance.
- Compile always-on and aligned/countertrend/neutral profile groups.
- Select side-relative profiles from existing context-consumption output.
- Return signal-exit masks, relative stop-loss/take-profit distances, readiness masks, per-profile outputs, and per-rule evidence.
- Advance normal range evaluation to `decisions_ready`.
- Keep managed exit lifecycle explicitly outside this change.

## Out of scope

- trade simulation and fills;
- stop/take hit arbitration;
- exit attribution to an executed trade;
- break-even, lock-profit, take-profile switching, phase rules, and runtime exits;
- Abi order creation or modification.
