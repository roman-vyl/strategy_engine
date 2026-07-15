# Tasks: Strategy Engine foundation v1

## Slice 0 — Revalidate audit and scope

- [x] Recheck the foundation contracts against `docs/master-plan.md` and `docs/08_detailed_bbb_contract_and_fastapi_replacement_audit.md`.
- [x] Confirm that no semantic indicator or strategy implementation is included in this change.
- [x] Record any contract deviation before production code begins.

## Slice 1 — Project and quality foundation

- [x] Add `pyproject.toml` with Python version, FastAPI service dependencies, test, lint, and type-check configuration.
- [x] Add package metadata, CLI/service entrypoint, and repository Makefile or equivalent verify commands.
- [x] Add clean source/test package structure without importing `legacy_source`.
- [x] Add environment-driven settings for HTTP host/port, MDS base URL, connect/read timeout, and request limits.

## Slice 2 — Canonical domain contracts

- [x] Implement canonical ticker, timeframe, and aligned half-open `TimeRange` models.
- [x] Implement normalized decimal-text value parsing/serialization.
- [x] Implement transport-neutral `MarketFrame` and validity metadata.
- [x] Implement deterministic canonical JSON hashing helpers for plans/config envelopes.
- [x] Add complete unit tests for validation and deterministic identity.

## Slice 3 — Indicator contracts and application skeleton

- [x] Implement `PlannedFeature`, `IndicatorPlan`, `FeatureFrame`, and output options.
- [x] Implement structural plan validation and deterministic plan hash.
- [x] Implement indicator catalog interface with an empty registry allowed.
- [x] Implement indicator range application service that returns explicit unsupported-capability errors when no evaluator exists.
- [x] Add tests proving no fabricated successful indicator output.

## Slice 4 — Strategy contracts and application skeleton

- [x] Implement BBB-compatible `StrategySpecEnvelope` without semantic parsing.
- [x] Implement range and range-batch request/result envelope models.
- [x] Implement strategy catalog interface with an empty registry allowed.
- [x] Implement validation/evaluation application services that return explicit unknown/unsupported errors for unported strategies.
- [x] Preserve deterministic variant ordering and per-variant error identity in batch contracts.

## Slice 5 — Market Data Service port/client skeleton

- [x] Define `MarketDataPort` independent of HTTP.
- [x] Implement the MDS HTTP adapter for `GET /v1/candles`.
- [x] Parse OHLCV decimal text without float conversion.
- [x] Validate ticker, timeframe, requested range, order, and complete grid in upstream responses.
- [x] Map MDS structured errors to stable Strategy Engine application errors.
- [x] Add fake-server contract tests; do not require a live MDS process.

## Slice 6 — FastAPI adapters

- [x] Implement `/health`, `/readiness`, and `/openapi.json`.
- [x] Implement indicator catalog/schema/plan-validation/range routes.
- [x] Implement strategy catalog/schema/validation/range/range-batch routes.
- [x] Add stable application-error to HTTP mapping and request IDs.
- [x] Ensure unsupported semantic operations return `501`, not placeholder `200` responses.
- [x] Add API contract tests for success of foundation capabilities and failure of unported capabilities.

## Slice 7 — Wiring and architecture guards

- [x] Implement composition-only service wiring.
- [x] Ensure Strategy application invokes Indicator application in-process.
- [x] Add import/dependency tests for domain, application, adapters, and `legacy_source` isolation.
- [x] Add file-responsibility review for central app/wiring/router modules.

## Slice 8 — Documentation and verification

- [x] Add README run, test, and API examples.
- [x] Document capability-level readiness semantics.
- [x] Document that BBB and runtime are not yet connected.
- [x] Update `docs/master-plan.md` phase status and identify the EMA vertical slice as next.
- [ ] Run repository lint/type checks in an environment with `ruff`, `mypy`, and `build`; sandbox pytest/compile/install checks are complete.
- [x] Build a cumulative patch containing every new and modified file.

## Acceptance

- [x] Service starts and exposes valid OpenAPI.
- [x] Foundation tests pass with strict lint/type checks.
- [x] No production import from BBB, `legacy_source`, `research`, `research_api`, or `data_engine`.
- [x] MDS client contract is tested without a real upstream.
- [x] Unimplemented indicator/strategy evaluations cannot return fake success.
- [x] API envelopes match this design and detailed BBB audit.
