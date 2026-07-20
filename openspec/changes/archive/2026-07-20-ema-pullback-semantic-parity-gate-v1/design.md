# Design: EMA Pullback semantic parity gate v1

## Architecture

The gate is repository tooling, not production service code. It consumes:

- immutable BBB source hash manifest;
- explicit stage-to-test manifest;
- pytest golden/API tests.

It produces one JSON report containing manifest hashes, source verification, stage coverage, pytest status and explicit exclusions.

## Invariants

- no stage is inferred from filename discovery;
- every required test is explicitly named;
- duplicate test entries are rejected by tests;
- a missing source file, source hash mismatch, missing parity test or failed test fails the gate;
- the report never claims execution parity;
- production packages do not import parity tooling or `legacy_source`.
