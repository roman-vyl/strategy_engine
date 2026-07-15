# Specification: EMA Pullback semantic parity gate v1

## Requirement: Complete explicit semantic coverage

The repository SHALL maintain an explicit manifest covering feature planning, indicators, contexts, context consumption, direction/blockers, setups, triggers, standard exit policy, managed policy and public API contracts.

## Requirement: Immutable source provenance

The gate SHALL verify every available copied BBB source entry against its recorded SHA-256 before executing parity tests.

## Requirement: Reproducible acceptance command

One documented command SHALL execute all required parity tests and return a non-zero status on missing tests, source mismatch or semantic/API mismatch.

## Requirement: Machine-readable report

The gate SHALL emit a JSON report containing manifest hashes, source verification status, covered stages, pytest result, final pass/fail and explicit exclusions.

## Requirement: Honest parity boundary

The report SHALL NOT claim parity for fill arbitration, same-bar execution order, fees, slippage, trade records, PnL, BBB presentation translation or live runtime checkpointing.

## Requirement: Consumer acceptance gate

A new consumer SHALL not accept Strategy Engine semantics unless the semantic parity report is green for the immutable source snapshot used by the port.
