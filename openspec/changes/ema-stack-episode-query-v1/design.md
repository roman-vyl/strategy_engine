## Context

`ema-stack-episode-v1` added a per-side projection of the EMA stack episode (`project_side`), reachable only through a strategy that declares `raw_spec.ema_stack_episode`. Its result is exposed by `/strategy-evaluations/range/diagnostics` together with every dense feature series.

A chart needs the episodes of a market without a strategy. Finished episodes never change; only the current one keeps forming. So the chart asks for the history once per market and parameter set, caches it, and refreshes only the current episode.

## Goals

- One computation of the episode for every consumer: the same parameter parser, the same EMA implementation and the same projector.
- The whole episode history, as structural entities only, in pages of whole episodes.
- No recomputation of the history per page.
- A cheap way to refresh the current episode after new candles close.

## Non-goals

- Changing any episode rule.
- An arbitrary display-window query.
- Dense per-bar series or candles in the response.
- Incremental continuation of the projection, persistence on disk.

## D1 Route and request

`POST /v1/ema-stack-episodes/history`

```json
{
  "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m"},
  "episode": {"fast_period": 500, "anchor_period": 1000, "slow_period": 2000, "window_bars": 24, "break_bars": 24},
  "side": "long",
  "page": {"before_start_ms": null, "limit": 50}
}
```

- `episode` is validated by the canonical parameter parser shared with `raw_spec.ema_stack_episode` (`parse_episode_params`, extracted from `parse_episode_section`). The three periods are required, since there is no `anchor_stack` to default from. `window_bars` defaults to 24 and `break_bars` to `window_bars`, as in the section. `history_bars` is not accepted: the history is the whole committed history. Unknown keys are rejected.
- `side` is `long` or `short`. A chart asks for each side separately; both reuse one cache entry per side.
- `page.before_start_ms`: return finished episodes that start before this `time_ms`; `null` means the newest. `page.limit`: 1 to 500 episodes, default 50.
- Optional `expected_market_data_hash`: the same meaning as in `/strategy-evaluations/range`.

## D2 History and computation

For a request the Engine:

1. reads the market's committed bounds from market data (`earliest_committed_open_time_ms`, `latest_committed_open_time_ms`);
2. uses the version key `(ticker, base_timeframe, params_hash, side, latest_committed_open_time_ms)`;
3. on a cache miss loads the candles of `[earliest, latest]`, computes `EMA(fast)`, `EMA(anchor)` and `EMA(slow)` through the indicator range evaluation with the EMA kind the strategy feature plan uses, and runs `project_side` once;
4. stores the projection's entity tables in the cache and serves the page from them.

```text
request ──► parse_episode_params ──► cache key (market, params, side, last candle)
                                        │ hit ─────────────────────────────┐
                                        ▼ miss                             │
                     candles [earliest, latest] ─► 3 EMAs ─► project_side ─┤
                                                                           ▼
                                                     page of whole episodes + current episode
```

Censoring stays the rule of `ema-stack-episode-v1`: only an episode that starts inside the slow-EMA warm-up at the start of the market's history is censored. It is returned with `censored: true` and without entities.

## D3 Cache

- In-process, bounded LRU of projection results, configured by entry count (default 16). Each entry holds the entity tables of one side, a few megabytes at most.
- An entry is never mutated. A new closed candle changes `latest_committed_open_time_ms` and so the key; the old entry ages out.
- Concurrent misses for the same key compute once.
- The cache is a memo: losing it only costs a recompute. Nothing is persisted.

## D4 Pages and the current episode

- **Finished episode:** an episode with a stack break. Its entities never change in later versions, as long as the market's earliest committed candle does not change.
- **Page:** up to `limit` finished episodes (a censored one included, without entities), newest first, with `start_ms < before_start_ms`. Each episode carries all its zones, false breaks and waves. `next_before_start_ms` is the start of the oldest returned episode, or `null` when there are no older ones.
- **Current episode:** every response carries `current`, the episode without a stack break as of the last closed candle (or `null` when the stack is not formed). It holds its zones (the open one with `final: false`), false breaks, finished waves, the forming wave, `touch_number` and the phase at the last candle.
- **Refresh:** after new candles close, the caller sends the first page again (`before_start_ms: null`, a small `limit`). Episodes it has already cached are identified by `start_ms` and unchanged; it replaces `current` and adds any episode that broke since.

## D5 Response

```json
{
  "history_id": "...",
  "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m", "earliest_ms": 0, "as_of_ms": 0},
  "episode": {"fast_period": 500, "anchor_period": 1000, "slow_period": 2000, "window_bars": 24, "break_bars": 24},
  "params_hash": "...",
  "market_data_hash": "...",
  "side": "long",
  "current": {"start_ms": 0, "touch_number": 3, "phase": "away", "zones": [...], "false_breaks": [...], "waves": [...]},
  "episodes": [
    {"start_ms": 0, "stack_break_ms": 0, "censored": false, "touches": 5, "false_breaks_count": 2,
     "zones": [...], "false_breaks": [...], "waves": [...]}
  ],
  "next_before_start_ms": 0
}
```

- Entities have the shape of `side_to_wire` in `ema-stack-episode-v1`, with every point as `time_ms` and without bar indices or `episode_id`.
- `history_id` hashes the market and the effective parameters (not the data version), so it names one set of structures for the caller's cache. `params_hash` hashes the effective parameters and the episode node version.
- Size: a page of 50 episodes is about 250 zones and waves, tens of kilobytes. The whole BTCUSDT.P 5m long history is about 210 episodes and 940 zones.

## D6 Effective parameters of a strategy

`/strategies/{id}/feature-plan` already returns `episode_columns_by_ref` when a spec declares episodes. It also returns `episode_params_by_ref`: the effective `EpisodeParams` of each `episode_ref` after defaults. A caller that shows the episode of a strategy sends its `fast_period`, `anchor_period`, `slow_period`, `window_bars` and `break_bars` to the history route. Specs without the section return neither field, so their plans and hashes are unchanged.

## D7 Errors

- Invalid parameters, unknown keys or unordered periods: the same `InvalidRequestError` messages as the strategy section, with paths under `episode`.
- An unknown side, a `limit` outside 1 to 500: `InvalidRequestError`.
- A market without committed candles: the market-data error of the other routes.

## Risks

- **First request cost:** a cache miss computes the whole history. Measured on the full BTCUSDT.P 5m history (687,966 bars): the projection takes 0.62 s (long) and 0.67 s (short), the three EMAs hundredths of a second; the candle load comes on top. The route's own end-to-end time is measured and reported before merge (task 3.5). If it is too slow for the chart, the next step is an incremental continuation of the projection, not a change of this contract.
- **Earliest candle changes:** a backfill of older data changes the history; the caller sees a new `earliest_ms` and drops its cache for that `history_id`.
- **Memory:** bounded by the LRU size.
