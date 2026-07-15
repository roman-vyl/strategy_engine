# Immediate next steps

## Completed in this planning pass

- Validated the attached BBB snapshot.
- Identified the current strategy/indicator call path.
- Located the primary seam inside `run_strategy_spec`.
- Classified every file in `research/strategies/ema_pullback`.
- Defined the non-destructive raw-copy layout.
- Defined Indicator and Strategy API compatibility targets.

## Next step 1 — create immutable raw source slice

Run a deterministic copy from the audited BBB snapshot into:

```text
legacy_source/bbb/research/strategies/ema_pullback/
legacy_source/bbb/tests/
```

Requirements:

- preserve relative paths and contents exactly;
- record SHA-256 for every copied file;
- record the source archive SHA-256;
- do not edit imports;
- do not attempt to run the copied package;
- do not modify BBB.

## Next step 2 — create the first OpenSpec

Create `strategy-engine-source-slice-v1` describing:

- immutable source-slice rules;
- exact copy manifest;
- provenance and hash verification;
- clean-source versus legacy-source separation;
- no semantic changes yet.

This is intentionally a small, mechanical change.

## Next step 3 — foundation contracts

After the source slice is installed, create a second change for independent foundational contracts:

- canonical ticker/timeframe/range;
- `MarketFrame`;
- `IndicatorPlan` / `FeatureFrame`;
- `StrategyEvaluationRequest` / `StrategyEvaluationResult`;
- `StrategyState` and `PositionState`;
- decision and evidence DTOs.

No EMA formula or strategy component should be ported before these boundaries are accepted.

## Next step 4 — first working vertical slice

The first working semantic slice should be Indicator Engine planning plus one simple indicator, most likely EMA:

```text
StrategySpec subset
 -> FeaturePlan parity
 -> EMA batch calculation
 -> Indicator range API
 -> golden parity against BBB
```

Do not begin with managed exits or full `ema_pullback`; they cross the most complex mixed-responsibility seam.

## Recommended work cadence

For each semantic slice:

1. identify exact BBB source functions;
2. copy semantics into clean engine modules;
3. replace BBB/Data Engine dependencies with explicit contracts;
4. add golden fixtures from unchanged BBB;
5. add public API only at an actual repository/process seam;
6. keep BBB authoritative until parity passes;
7. add every new/modified file to the cumulative strategy-engine patch.


## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.
