## MODIFIED Requirements

### Requirement: BBB-compatible strategy envelope

The service SHALL define a `StrategySpecEnvelope` capable of preserving the current BBB strategy identity, instance/variant identity, raw JSON spec, compatibility profile, and deterministic config identity.

This foundational envelope SHALL NOT itself semantically parse `ema_pullback`; semantic parsing is owned by the EMA Pullback feature-planning capability.

#### Scenario: Preserve strategy configuration identity

- **WHEN** a BBB-compatible strategy envelope is accepted
- **THEN** the service SHALL preserve its strategy, instance, raw-spec, and compatibility-profile identity
- **AND** SHALL derive a deterministic config identity.

### Requirement: Coarse-grained Strategy range API

`POST /v1/strategy-evaluations/range` SHALL accept one strategy envelope plus canonical market/range identity and output options.

The service SHALL derive required features, load market data, and calculate indicators, contexts, entries, and exits internally.

The result schema SHALL reserve groups required for BBB compatibility: identity, market, features, contexts, entries, exit policy, component evidence/counters, validity, optional state artifact, and warnings.

The result SHALL exclude fills, fees, slippage, trades, PnL, equity, and Workbench DTOs.

#### Scenario: Submit a strategy range request

- **WHEN** a caller submits one strategy envelope and canonical market range
- **THEN** the endpoint SHALL use the coarse-grained strategy result envelope
- **AND** the result SHALL NOT contain execution fills, fees, PnL, or Workbench DTOs.

### Requirement: Catalog and validation APIs

The service SHALL expose indicator and strategy catalog/schema/validation routes. Unknown IDs SHALL return structured `404` errors. Unimplemented semantic validation SHALL return structured `501` errors rather than placeholder success.

#### Scenario: Request an unknown catalog item

- **WHEN** a caller requests an unknown indicator or strategy identifier
- **THEN** the service SHALL return a structured `404` error
- **AND** unimplemented semantic validation SHALL return `501` rather than placeholder success.

### Requirement: Capability-aware readiness

`GET /health` SHALL report process liveness.

`GET /readiness` SHALL report readiness per capability and dependency. The service MAY be ready for catalog/schema operations while indicator or strategy evaluation remains `not_implemented`.

Readiness SHALL NOT claim semantic capability that is not implemented.

#### Scenario: Only catalog operations are available

- **WHEN** catalog and schema operations are available but semantic evaluation is not implemented
- **THEN** readiness SHALL report those capabilities separately
- **AND** SHALL NOT claim semantic evaluation readiness.
