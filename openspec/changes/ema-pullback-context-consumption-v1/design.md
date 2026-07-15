# Design: EMA Pullback Context Consumption v1

The range evaluator builds ContextBundle once, then resolves raw `up/down/neutral` state against each enabled trade side into `aligned/countertrend/neutral`.

Supported policies:

- `htf_regime_gate` for blocker and setup consumers;
- `exit_profile_by_htf_state` for exit-policy profile selection.

The result is emitted as `component_evidence.context_consumption`. This is policy evidence only. Local blocker/setup masks, final entries, exit signals, and managed execution remain out of scope.
