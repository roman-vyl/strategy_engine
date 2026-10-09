## Why

The EMA stack episode (`ema-stack-episode-v1`) can only be computed today as part of a strategy evaluation:

- the strategy must declare `raw_spec.ema_stack_episode`;
- the episode then appears in `/strategy-evaluations/range/diagnostics`, beside the dense per-bar trace of every feature.

A chart that shows episodes has no strategy. Episodes are a historical market structure, not candles or indicators:

- a finished episode never changes;
- only the current episode keeps forming as new candles close.

So the chart does not need the episode for an arbitrary display window. It needs the whole episode history of a market and a parameter set, delivered as structural entities, in pages of whole episodes, plus refreshes of the current episode. Using diagnostics for that couples the chart to a strategy spec and moves about 140 MB per year of 5m bars.

This change makes the episode history a standalone read-only capability of the Engine with two consumers of the same computation:

```text
                         ┌─ strategy evaluation   (raw_spec.ema_stack_episode)
candles → EMA → episode ─┤
                         └─ episode history       (market + episode params)
```

It is a second transport over the same projection, not a second way to compute the episode.

## What Changes

- New route `POST /v1/ema-stack-episodes/history`, read-only.
  - **Input:** market (`ticker`, `base_timeframe`), episode parameters (`fast_period`, `anchor_period`, `slow_period`, `window_bars`, `break_bars`), side, and a page: `before` (an episode start `time_ms` or none) and `limit` (a number of finished episodes).
  - **Parameters** are parsed by the same canonical `EpisodeParams` parser as the strategy section. There is no strategy spec in the request and no `anchor_stack` fallback.
  - **Computation:** the whole committed history of the market, with the same EMA implementation and the same per-side projector (`project_side`). No new math, no second parser or projector.
  - **Pages are whole episodes.** A page holds up to `limit` finished episodes, newest first, older than `before`, each with all its zones, false breaks and waves. Every episode carries its real start, stack break and touch numbers, whatever page it is on.
  - **Current episode:** every response also carries the episode that has not broken yet, with its zones, false breaks, finished waves and the forming wave, as of the last closed candle.
  - **One computation per data version.** The Engine computes the history once per `(market, parameters, last committed candle)` and keeps the result in a bounded in-memory cache. Later pages and repeated requests read the cache; nothing is recomputed per page. A new closed candle changes the version.
  - **Identity:** `history_id` (a hash of market and parameters), `params_hash`, `market_data_hash`, `as_of_ms` (the last closed candle). A finished episode is identified by its start `time_ms`.
- The strategy feature plan (`/strategies/{id}/feature-plan`) also returns the effective episode parameters per `episode_ref`, so a caller that shows the episode of a strategy sends exactly the parameters the strategy uses and never re-implements defaults.
- Strategy evaluation, diagnostics, the episode operand, node identities and specs without `ema_stack_episode` are unchanged.

## Out of scope

- Any change to the episode rules or geometry.
- Incremental continuation of the projection on a new candle without recomputing the history (a later change, if the measured recompute is too slow).
- Persisting episodes on disk.
- The research_service proxy and cache and the Workbench drawing; they consume this contract in their own changes.

## Impact

- ADDED capability `ema-stack-episode-query-v1`.
- `ema-stack-episode-v1`: ADDED `Effective episode parameters in the feature plan` and `One episode computation for every consumer`.
- Not modified: `/strategy-evaluations/*` request and response shapes except the additive feature-plan field, the indicator routes, the managed state machine.

## Verification

- Equality of every finished episode and its entities with the diagnostics episode tables of a strategy declaring the same parameters over the same history, both sides.
- Paging: the union of all pages equals the full history, with no gaps or duplicates, and touch numbers do not depend on the page.
- Cache: a second page and a repeated request do not recompute; a new candle does.
- Determinism and identity fields.
- Time and size of the full BTCUSDT.P 5m history, reported.
- HTTP parity on the owner's Mac with the research reference `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m.
- Gate: ruff, mypy, the full suite without `tests/parity`, `openspec validate ema-stack-episode-query-v1 --strict`.
