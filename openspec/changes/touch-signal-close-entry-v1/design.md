## Context

Engine live-entry chain (`docs/22_live_projections_architecture.md`, owner page
https://claude.ai/artifact/S1krVonVHN8v86GLGvWRKn): HTTP → `EvaluateLiveEntryProjection` → `LoadLiveFeatureFrame` →
registry → `EmaPullbackLiveEntryProjectionAdapter` → `evaluate_ema_pullback_frame` (contexts → consumption →
direction/blockers → setups → triggers → risk/entries → exit policy → potential entries) → `_plan_for_side` at the target
index → `_normalize_desired_entry` → HTTP.

## Decisions

### D1. Engine config file read at start (owner 18:37-18:44, MDS precedent)
`STRATEGY_ENGINE_CONFIG_PATH` (optional env) names a TOML file; in bbb_stack it is
`${BBB_DATA_ROOT}/strategy-engine/engine.toml`, the folder mounted read-only like `BBB_data/mds`. `Settings.from_env()`
reads it once: `live_entry_mode ∈ {ema_anchor, touch_trigger}`. Path unset or file absent → `ema_anchor`. Unknown key,
unknown value or a parse error → the service fails at start (fail closed, no silent fallback). Switching = edit the file
and restart the Engine container; a restart re-reads the file because the folder (not the single file) is mounted.
Not an environment variable: Docker fixes environment values at container creation, so a plain restart would keep the
old value (owner wants restart, not recreate/deploy).

### D2. Only the live-entry adapter changes
The mode is injected at composition: wiring → `build_live_entry_projection_registry(mode)` → the EMA Pullback adapter constructor (the neutral adapter protocol is unchanged). The EMA
Pullback adapter keeps `_plan_for_side` (reads `potential_entries`) for `ema_anchor`, and for `touch_trigger` builds the
plan from the same `EmaPullbackEvaluation`:
- signal: `evaluation.entries[side].entry_allowed[target]` (the mask research enters on; it already contains setups, the
  vote, blockers, the touch trigger and risk);
- entry: `close[target]` from the frame's market bars;
- stop / take: `exit_policy.stop_loss_distance_<side>[target]`, `take_profit_distance_<side>[target]`, same formula as
  `potential_entries` uses with the anchor; the same positivity and geometry checks; the same locked profile and partial
  takes code.
`potential_entries.py` is not touched, so `/range` and research output do not change.

### D3. Trigger other than touch_anchor
`touch_trigger` builds a plan only for a strategy whose trigger is `touch_anchor`; for any other trigger live-entry returns
`null`, the same as today (today `potential_entries` is empty for non-touch triggers).

### D4. Same contract shape
`source_plan_bar_open_time_ms` = the signal bar; fields unchanged. Runtime gets a plan only on the signal bar and `null` on
the next bar (unless it is itself a signal bar); today's reconciliation turns that into Apply / Cancel / Replace.

## Risks / checks
- Open-trade management starts after the bar Runtime records as the entry (the fill bar), while research manages from the
  bar after the signal bar. Not touched here; the possible one-bar shift is measured in the parity task and reported.
- Both sides on one bar (close == anchor, both allowed): unchanged `evaluation_invariant_broken`.
