# Design: EMA Pullback Setups v1

## Pipeline position

```text
FeatureFrame
→ ContextBundle
→ direction + blockers
→ pre_setup_allowed
→ local setup semantics
→ optional setup context gate
→ setup AND composition
→ pre_trigger_allowed
```

## Ownership

Setup formulas and state machines belong to `strategy_engine.strategies.ema_pullback`. BBB remains responsible for research execution, fills, trades, reports, and Workbench translation.

## Components

### Untouched anchor

For each side, determine anchor touches from candle range, require an untouched prior lookback, arm while price remains on the side of the anchor, and preserve the setup for the configured active touch window.

### EMA bounce counter

Preserve the legacy sequential state machine exactly:

- confirmed trend episode start and break;
- episode identity;
- armed state;
- range-cross touch detection;
- pending bounce lookback window;
- completed and effective bounce counts;
- maximum bounce admission;
- state reset on confirmed trend break.

### Anchor stack width

Calculate absolute fast/slow EMA width normalized by ATR, require current width and recent rolling maximum thresholds, preserve warmup and blocked reasons.

## Context seam

A setup first computes its local mask. If the rule declares context consumption, the engine applies the matching side-aware gate after local evaluation:

```text
final_setup_allowed = local_setup_allowed AND context_gate_allowed
```

## Composition

All declared setups are composed through AND. An empty setup list remains an all-true compatibility mask during staged migration.

## API result

The existing `POST /v1/strategy-evaluations/range` response adds `component_evidence.setups`, with per-side setup traces, composed `setups_ok`, and `pre_trigger_allowed`. This change does not claim final decisions readiness.
