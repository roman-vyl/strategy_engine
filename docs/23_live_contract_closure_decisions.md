# Live contract closure decisions

## Status

These decisions close local Strategy Engine contract gaps before Runtime integration.
They do not close the cross-repository system-integration and production-performance gates.

## Live open-trade management mode

`exit_management.mode` is a research/backtest compatibility field, not a live capability
flag and not a Runtime command.

The Runtime request does not add or transmit a separate management-mode field. The
complete immutable strategy specification remains the source of strategy configuration.
For live open-trade projection, missing `mode`, `diagnostic_only`, and `managed` all use
the same post-entry projection path and evaluate the management rules actually present in
the specification. When no rule changes protection, receipt-seeded stop and take are
preserved. Locked-profile standard signal exits remain active.

The public historical `/managed-replay` endpoint keeps its existing `mode="managed"`
compatibility requirement.

## Decimal and exchange normalization boundary

Receipt and public protection prices use canonical normalized decimal text on the wire
and `Decimal` at the contract boundary. Receipt values must not make a
`Decimal -> float -> Decimal` round trip merely to be returned unchanged.

The existing strategy calculation core may continue to use float-based Pandas/NumPy
values in v1. A calculated float candidate crosses into the contract layer once through
`Decimal(str(candidate))`. No-op protection retains the exact receipt Decimal value.

Strategy Engine does not quantize prices to exchange tick size, quantity step, minimum
order size, or order-side rounding rules. ABI owns instrument-aware exchange
normalization immediately before creating or modifying an exchange order.

## MDS unknown stream vocabulary

An MDS bounds `404` maps to `market_stream_not_found` with HTTP `404`. Both live-entry
and open-trade OpenAPI operations publish this response. Generic `unknown_resource`
remains available for non-market resources.

## Inverted bounds

`earliest_committed_open_time_ms > latest_committed_open_time_ms` is already an upstream
contract violation and maps to `upstream_contract_error`. A regression test protects this
behavior; no production logic change is required.

## Temporary cross-repository integration gate

A permanent integration/system-test service is deferred for separate design. Until then,
Engine and MDS may be exercised with an explicit opt-in local harness using sibling
repositories and real HTTP processes. Such a harness must not run in normal `make verify`
and must use isolated ports, temporary storage, readiness waits, process cleanup, and log
capture.

The permanent gate remains open until a dedicated multi-repository test service defines:

- service commit pinning;
- Docker Compose topology;
- fixture seeding and cleanup;
- CI multi-repository checkout;
- compatibility ownership;
- required Engine -> MDS and Runtime -> Engine -> MDS scenarios.

## Runtime concurrency boundary

Strategy Engine supports independent API requests for different deployed strategies. It
does not define Runtime deployment uniqueness or multi-replica coordination.

Runtime must later specify and test:

- support for multiple different active strategies;
- rejection of duplicate deployment of the same logical strategy identity;
- isolation of receipts and lifecycle state;
- the single-writer or active-active model for multiple Runtime process replicas.

The multi-replica gate cannot be closed until Runtime persistence, locking, idempotency,
and lifecycle transition ownership are designed.
