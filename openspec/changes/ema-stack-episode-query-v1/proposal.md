## Why

The EMA stack episode (`ema-stack-episode-v1`) can only be computed today as part of a strategy evaluation:

- the strategy must declare `raw_spec.ema_stack_episode`;
- the episode then appears in `/strategy-evaluations/range/diagnostics`, beside the dense per-bar trace of every feature.

A chart that shows the episode for a market has no strategy. It needs the episode for a market, a time range and a set of episode parameters. Using diagnostics for that couples the chart to a strategy spec and moves about 140 MB per year of 5m bars, almost all of it unrelated dense feature series.

This change makes the episode a standalone read-only capability of the Engine with two consumers of the same computation:

```text
                         ┌─ strategy evaluation   (raw_spec.ema_stack_episode)
candles → EMA → episode ─┤
                         └─ episode query         (market + range + episode params)
```

It is a second transport over the same projection, not a second way to compute the episode.

## What Changes

- New route `POST /v1/ema-stack-episodes/range`, read-only.
  - **Input:** market (`ticker`, `base_timeframe`), display range `[from_ms, to_ms)`, episode parameters (`fast_period`, `anchor_period`, `slow_period`, `window_bars`, `break_bars`, `history_bars`), optional sides.
  - **Parameters** are parsed by the same canonical `EpisodeParams` parser as the strategy section. There is no strategy spec in the request and no `anchor_stack` fallback: the three periods are required.
  - **History:** the Engine loads candles before `from_ms` by the live history policy of the episode (slow-EMA warm-up plus `history_bars`). An episode that started before the display range keeps its real start and touch numbers.
  - **Computation:** the same EMA implementation through the indicator plan, and the same per-side projection (`project_side`). No new math and no second parser or projector.
  - **Output, per side:** the episodes, zones, false breaks and waves that intersect the display range, with `time_ms` of every point and `known_at`; the state as run-length segments `[from_ms, to_ms, phase, touch_number]`; optional dense state or event series by name.
  - **Identity:** the effective parameters, `params_hash`, `market_data_hash` and the computed range, so a caller can cache by them. The same request gives the same response.
- The strategy feature plan (`/strategies/{id}/feature-plan`) also returns the effective episode parameters per `episode_ref`, so a caller that shows the episode of a strategy sends exactly the parameters the strategy uses and never re-implements defaults.
- Strategy evaluation, diagnostics, the episode operand, node identities and specs without `ema_stack_episode` are unchanged.

## Out of scope

- Any change to the episode rules or geometry.
- Proxies, caching and drawing in research_service and the Workbench front; they consume this contract in their own changes.
- Features computed on episode ranges (V2 of the episode).

## Impact

- ADDED capability `ema-stack-episode-query-v1`.
- `ema-stack-episode-v1`: ADDED `Effective episode parameters in the feature plan` and `One episode computation for every consumer`.
- Not modified: `/strategy-evaluations/*` request and response shapes except the additive feature-plan field, the indicator routes, the managed state machine.

## Verification

- Equality of the query's tables with the diagnostics episode tables of a strategy declaring the same parameters, evaluated over the query's computed range, on both sides.
- The display range clip, the segments and the optional series on hand-built bars.
- History: an episode that starts before `from_ms` is not censored and keeps its touch numbers.
- Determinism and identity fields.
- Parity on the owner's Mac through HTTP with the research reference `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m.
- Gate: ruff, mypy, the full suite, `openspec validate ema-stack-episode-query-v1 --strict`.
