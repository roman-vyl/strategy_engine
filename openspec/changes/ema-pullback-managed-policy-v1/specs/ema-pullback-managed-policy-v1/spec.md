# EMA Pullback Managed Policy v1 Specification

## Requirement: Coarse-grained replay

The service SHALL evaluate one already-open trade over a requested aligned market range in one application call and SHALL NOT require one HTTP call per bar.

## Requirement: Required inputs

The request SHALL include canonical strategy spec, canonical market range, trade identity, side, entry timestamp and entry price.

## Requirement: Strategy-owned outputs

The response SHALL expose ordered phase-change, active-stop, active-take and runtime-exit events; per-bar active policy state; and final managed state.

## Requirement: Next-bar effectiveness

Stop, take and runtime-exit policy changes calculated at the end of bar N SHALL identify bar N+1 as their effective boundary.

## Requirement: Execution exclusion

The service SHALL NOT decide actual OHLC stop hits, fill price, fees, PnL or exchange order status.

## Requirement: Determinism

The same spec, market range and trade facts SHALL produce identical events and final state.
