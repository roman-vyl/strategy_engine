## Context

Engine live-entry chain (`docs/22_live_projections_architecture.md`): HTTP → `EvaluateLiveEntryProjection` →
`LoadLiveFeatureFrame` → registry → `EmaPullbackLiveEntryProjectionAdapter` → `evaluate_ema_pullback_frame`
(contexts → consumption → direction/blockers → setups → triggers → risk/entries → exit policy → potential entries) →
`_plan_for_side` at the target index → `_normalize_desired_entry` → HTTP.
Only the last stage of the pipeline, `project_potential_entries`, changes. Owner's chain page:
https://claude.ai/artifact/S1krVonVHN8v86GLGvWRKn

## Decisions

### D1. The mode lives on the touch trigger, default keeps today
`components.trigger.entry_price ∈ {"anchor", "signal_close"}`, default `"anchor"`. Allowed only with
`component_id: "touch_anchor"`. Any other value, or the key on another trigger, is a typed validation error, never a
silent fallback. Without the key every result is byte-identical to today.

### D2. `signal_close` uses the final entry mask
The plan exists on bar `i` iff `entries[side].entry_allowed[i]` (the same mask research enters on). This already contains
`pre_trigger_allowed` (setups, vote, blockers), the touch trigger (`touch & close_ok`) and the risk mask, so no filter is
re-implemented in the projection.

### D3. Price and protection from the signal bar
`entry = close[i]`. Stop/take use the exit-policy distances of bar `i` (R = k × ATR on the touch bar), exactly the
formula used today with `anchor[i]`. The existing positivity and geometry checks stay
(`stop < entry < take` long, mirrored short); a bar that fails them has no plan.

### D4. Same contract shape
`_plan_for_side` and the HTTP response do not change. `source_plan_bar_open_time_ms` = the signal bar. Runtime sees a plan
only on the signal bar and `null` on the next bar (unless it is itself a signal bar), which today's reconciliation turns
into Apply / Cancel / Replace.

## Risks / checks
- Open-trade management starts after the bar Runtime records as the entry (the fill bar), while research manages from the
  bar after the signal bar. This change does not touch open-trade; the possible one-bar shift is measured in the parity
  task and reported, and handled in the Runtime stage if real.
- Both sides on one bar: possible only when close == anchor and both sides are allowed, the same as today; the existing
  `evaluation_invariant_broken` stays.
