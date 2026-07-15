# EMA Pullback Context Consumption v1

The strategy range pipeline now continues after `ContextBundle` construction:

```text
raw HTF state (up/down/neutral)
+ evaluated side (long/short)
→ resolved regime (aligned/countertrend/neutral)
→ context policy result
```

Supported policies:

- `htf_regime_gate` for blocker and setup consumers;
- `exit_profile_by_htf_state` for exit-policy profile selection.

The strategy API returns this under `component_evidence.context_consumption`. The records contain raw state, side-relative regime, allowed regimes, allow masks, or resolved exit profiles. This is not yet a final blocker/setup or entry/exit decision: local component semantics have not been combined with the context gate.
