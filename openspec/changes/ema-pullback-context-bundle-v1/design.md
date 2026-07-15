# Design: EMA Pullback Context Bundle v1

## Current seam

The legacy BBB sequence is:

```text
FeaturePlan
→ enriched feature dataframe
→ build_context_bundle_for_spec(spec, dataframe, plan)
→ ContextBundle
→ signal and exit consumers
```

The Strategy Engine already owns the first two steps. This change moves the third step without moving the downstream consumers.

## Module ownership

```text
strategies/ema_pullback/contexts.py
  ContextOutput
  ContextBundle
  build_context_bundle(raw_spec, FeatureFrame, EmaPullbackFeaturePlan)
```

The context module depends only on Strategy Engine contracts. It does not import `legacy_source`, BBB packages, FastAPI, Market Data Service adapters, or execution code.

## Provider semantics

For each canonical `raw_spec.contexts[context_ref]` provider:

1. Require `component_id == "htf_context"`.
2. Resolve the three output columns from `plan.htf_context_columns_by_ref`.
3. Read fast, anchor, and slow EMA values on the base-timeframe FeatureFrame grid.
4. Apply BBB ordering:
   - `up = fast > anchor > slow`;
   - `down = fast < anchor < slow`;
   - otherwise `neutral`.
5. Any missing/invalid value yields neutral.
6. If required columns are absent, the entire provider output is neutral, matching BBB defensive behavior.

## API response

`POST /v1/strategy-evaluations/range` keeps the same request. The response adds:

```json
{
  "contexts": {
    "time_ms": [0, 300000],
    "items": {
      "htf": {
        "context_ref": "htf",
        "provider": {},
        "state": ["neutral", "up"],
        "up": [false, true],
        "down": [false, false],
        "neutral": [true, false]
      }
    }
  },
  "validity": {
    "stage": "contexts_ready",
    "features_ready": true,
    "contexts_ready": true,
    "decisions_ready": false
  }
}
```

`include_contexts=false` suppresses transport output only; the evaluator still constructs contexts so the internal pipeline remains ready for later decision consumers.

## Parity

Golden tests execute the copied BBB `components/context.py` directly and compare:

- raw state series;
- up mask;
- down mask;
- neutral mask;
- missing/warmup behavior.
