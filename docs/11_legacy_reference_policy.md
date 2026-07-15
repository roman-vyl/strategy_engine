# Legacy reference policy

`legacy_source/bbb/` is a read-only mirror of selected files from the original BBB repository.

It is allowed only for:

- source and dependency audits;
- understanding historical behavior;
- generation or verification of frozen parity fixtures;
- provenance and hash verification.

It is forbidden for:

- imports from production modules under `src/`;
- runtime dependency injection or service wiring;
- API request handling;
- fallback execution;
- deployment-time coupling to BBB.

The original BBB repository remains independent. Strategy Engine is built as a new standalone service.
