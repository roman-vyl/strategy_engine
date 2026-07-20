# Proposal: EMA Pullback Triggers v1

## Why

The extracted strategy pipeline already owns features, contexts, direction, blockers, and setups, but entry evaluation still stops before the trigger layer. BBB currently owns three trigger components whose exact prior-window semantics must be preserved before risk and final entry masks can move.

## What changes

- port `reclaim_anchor`, `strong_reclaim_anchor`, and `touch_anchor`;
- preserve side-aware wick/close probe semantics;
- preserve prior-window-only reclaim behavior;
- compose trigger output with `pre_trigger_allowed`;
- expose `pre_risk_entry_allowed` and trigger traces through the existing range API;
- advance capability metadata to `triggers_ready` without claiming final decisions readiness.

## Out of scope

Risk components, final entries, exit policy, managed exits, BBB cutover, and incremental runtime remain separate changes.
