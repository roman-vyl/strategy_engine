# EMA Pullback Context Bundle v1

The Strategy Engine now continues past feature calculation and builds the strategy-level ContextBundle internally.

## Pipeline

```text
strategy spec + ticker/timeframe/range
→ FeaturePlan
→ Indicator Engine
→ FeatureFrame
→ ContextBundle
→ response stage: contexts_ready
```

No additional MDS request is made. Context providers consume the EMA series already present in FeatureFrame.

## Supported provider

`htf_context` with BBB-compatible semantics:

```text
fast > anchor > slow  → up
fast < anchor < slow  → down
otherwise             → neutral
```

Warmup/null/missing values are neutral. The output contains the raw state series plus explicit up/down/neutral masks on the base-timeframe grid.

## Still not ported

Context consumers such as `htf_regime_gate` and `exit_profile_by_htf_state`, as well as entries and exits, remain future changes.
