# Strategy Engine

Independent Indicator Engine and Strategy Engine extracted semantically from BBB.

Current state:

- detailed BBB call-contract and FastAPI replacement audit;
- implemented `strategy-engine-foundation-v1` FastAPI service;
- canonical market/range/decimal/hash contracts;
- separate Indicator and Strategy application boundaries;
- Market Data Service client behind a port;
- operational BBB-compatible EMA, ATR, ATR-distance, RSI, and ADX/DMI Indicator Engine range evaluation;
- one shared range evaluator and one Market Data Service read for mixed indicator plans;
- indicator catalog advertising the ported `ema`, `atr`, `atr_distance`, `rsi`, `adx`, `di_plus`, and `di_minus` capabilities;
- structured `501` for all remaining unported indicators and strategies;
- full EMA Pullback strategy evaluation (contexts, direction, blockers, setups, triggers, entries, exit policy, managed replay) and the live-entry/open-trade projection endpoints described below;
- The original BBB repository remains independent and is not part of this service runtime.

## Dependencies

Runtime dependencies are declared in `pyproject.toml`: FastAPI, HTTPX, NumPy, pandas, Pydantic and Uvicorn. Development dependencies are available through the `dev` extra and include build, pytest, Ruff and mypy.

## Run

```bash
python -m pip install -e '.[dev]'
make verify
make run
```

The default service address is `http://127.0.0.1:8090`.

```bash
curl http://127.0.0.1:8090/health
curl http://127.0.0.1:8090/readiness
```

## Environment

```text
STRATEGY_ENGINE_HTTP_HOST
STRATEGY_ENGINE_HTTP_PORT
STRATEGY_ENGINE_MDS_BASE_URL
STRATEGY_ENGINE_MDS_CONNECT_TIMEOUT_SECONDS
STRATEGY_ENGINE_MDS_READ_TIMEOUT_SECONDS
STRATEGY_ENGINE_MAX_BATCH_VARIANTS
```

## Start here

```text
docs/master-plan.md
docs/08_detailed_bbb_contract_and_fastapi_replacement_audit.md
docs/10_foundation_v1_implementation.md
docs/11_ema_indicator_vertical_slice_v1.md
docs/12_atr_indicator_vertical_slice_v1.md
docs/13_rsi_indicator_vertical_slice_v1.md
docs/14_adx_dmi_indicator_vertical_slice_v1.md
```

## EMA range example

```bash
curl -X POST http://127.0.0.1:8090/v1/indicator-evaluations/range \
  -H 'Content-Type: application/json' \
  -d '{
    "market": {
      "ticker": "BTCUSDT.P",
      "base_timeframe": "5m",
      "from_ms": 1710000000000,
      "to_ms": 1710000300000
    },
    "plan": {
      "plan_version": "1",
      "features": [{
        "output_id": "ema_close_base_200",
        "kind": "ema",
        "timeframe": "base",
        "source": "close",
        "parameters": {"period": 200},
        "dependencies": []
      }]
    }
  }'
```

## ATR range example

```bash
curl -X POST http://127.0.0.1:8090/v1/indicator-evaluations/range \
  -H 'Content-Type: application/json' \
  -d '{
    "market": {
      "ticker": "BTCUSDT.P",
      "base_timeframe": "5m",
      "from_ms": 1710000000000,
      "to_ms": 1710004200000
    },
    "plan": {
      "plan_version": "1",
      "features": [{
        "output_id": "atr_base_14",
        "kind": "atr",
        "timeframe": "base",
        "source": "close",
        "parameters": {"period": 14},
        "dependencies": []
      }]
    }
  }'
```

## RSI range example

```bash
curl -X POST http://127.0.0.1:8090/v1/indicator-evaluations/range \
  -H 'Content-Type: application/json' \
  -d '{
    "market": {
      "ticker": "BTCUSDT.P",
      "base_timeframe": "5m",
      "from_ms": 1710000000000,
      "to_ms": 1710004200000
    },
    "plan": {
      "plan_version": "1",
      "features": [{
        "output_id": "rsi_base_14",
        "kind": "rsi",
        "timeframe": "base",
        "source": "close",
        "parameters": {"period": 14},
        "dependencies": []
      }]
    }
  }'
```

## ADX/DI range example

```bash
curl -X POST http://127.0.0.1:8090/v1/indicator-evaluations/range \
  -H 'Content-Type: application/json' \
  -d '{
    "market": {
      "ticker": "BTCUSDT.P",
      "base_timeframe": "5m",
      "from_ms": 1710000000000,
      "to_ms": 1710018000000
    },
    "plan": {
      "plan_version": "1",
      "features": [
        {"output_id":"adx_close_base_14","kind":"adx","timeframe":"base","source":"close","parameters":{"period":14},"dependencies":[]},
        {"output_id":"di_plus_close_base_14","kind":"di_plus","timeframe":"base","source":"close","parameters":{"period":14},"dependencies":[]},
        {"output_id":"di_minus_close_base_14","kind":"di_minus","timeframe":"base","source":"close","parameters":{"period":14},"dependencies":[]}
      ]
    }
  }'
```

## ATR distance capability

Indicator Engine supports BBB-compatible `atr_distance` as a derived feature. It references an earlier ATR output in the same plan and applies a positive multiplier without another market-data read, resample, ATR calculation, or warmup.

## EMA pullback feature planning

Strategy Engine now owns BBB-compatible feature discovery for canonical serialized `ema_pullback` specs. Callers submit the strategy envelope rather than an IndicatorPlan:

```http
POST /v1/strategies/ema_pullback/feature-plan
```

The response contains the ordered/deduplicated indicator plan and BBB-compatible column mappings.

## EMA Pullback feature-stage evaluation

`POST /v1/strategy-evaluations/range` builds the strategy-owned feature plan internally and returns the calculated FeatureFrame. The service reads candles from Market Data Service through `MarketDataPort`.

## EMA Pullback context stage

`POST /v1/strategy-evaluations/range` builds declared `htf_context` providers after feature calculation and returns BBB-compatible `up`, `down`, `neutral`, and state series.

## Context consumption stage

EMA Pullback range evaluation resolves HTF context by trade side and evaluates `htf_regime_gate` and exit-profile context policies. Results are returned as policy evidence.

## Current strategy evaluation stage

`ema_pullback` range evaluation builds features, contexts, context-consumption masks, side-aware direction, and all current blocker masks.

## EMA pullback setups, triggers, and entries

The engine owns indicators, contexts, context policies, direction, blockers, and all three setup families (`untouched_anchor_setup`, `ema_bounce_counter_setup`, `anchor_stack_width_setup`), the `reclaim_anchor`/`strong_reclaim_anchor`/`touch_anchor` triggers, and the `risk` component (`no_risk_filter` in v1). Range evaluation returns bar-aligned setup/trigger evidence, `pre_risk_entry_allowed`, and final side entry masks.

## Standard strategy decisions

`POST /v1/strategy-evaluations/range` returns final entry masks and standard profile-aware exit policy outputs: signal exits, initial relative stop/take distances, readiness masks, and rule evidence. These are policy decisions only; Research Service owns backtest execution and position lifecycle; Runtime owns live execution orchestration through the live-entry/open-trade endpoints below. Managed policy decisions are available through the managed-replay endpoint; fill arbitration remains outside Strategy Engine.

## Managed exit policy

Managed EMA Pullback policy is available through `POST /v1/strategy-evaluations/managed-replay`. The endpoint returns phase, stop, take-profile and runtime-exit decisions for an already-open logical trade. It does not perform OHLC fill arbitration or create exchange orders.

## Live entry and open-trade projections

`POST /v1/strategy-evaluations/live-entry` accepts a flat strategy/market/target-bar request (no Runtime-supplied history) and returns one atomic `desired_entry` (or `null`) for the requested target bar. `POST /v1/strategy-evaluations/open-trade` accepts an immutable `executed_trade_receipt` and returns post-target-bar `desired_protection` and a target-active `close_signal`. Both endpoints share one internal live-history acquisition path and return no execution facts, fills, or PnL; see `docs/22_live_projections_architecture.md`.

## Composer catalog

The authoritative EMA Pullback Workbench catalog is available at `GET /v1/strategies/ema_pullback/composer-catalog`.

## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.

## Strategy → Research execution contract

Range evaluation and managed replay expose versioned, per-bar execution-seam contracts. Research Service owns all fills, arbitration, fees, PnL and trade records. See `docs/13_strategy_research_execution_contract_v1.md`.
