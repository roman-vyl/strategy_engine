# Immutable BBB source reference

This directory is a byte-preserving source slice from the audited BBB snapshot.

It is not production code and is not expected to import successfully in this repository.

Rules:

- never edit files here;
- never place this directory on production `PYTHONPATH`;
- use it only for audit, semantic porting and golden-parity provenance;
- implement working code under `src/strategy_engine`.
