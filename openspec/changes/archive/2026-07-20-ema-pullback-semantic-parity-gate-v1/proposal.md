# Proposal: EMA Pullback semantic parity gate v1

## Why

Individual golden tests exist for every ported semantic slice, but BBB cutover requires one reproducible acceptance gate with immutable source provenance and an explicit boundary of what has and has not been proven.

## What changes

- add a normative parity manifest covering every ported semantic stage;
- add one command that verifies copied BBB hashes and runs all mandatory parity/API tests;
- emit a machine-readable JSON report;
- document that execution, reports, Workbench translation and live runtime remain outside this claim.
