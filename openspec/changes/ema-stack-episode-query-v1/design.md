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
- Optional `expected_market_data_hash`: the `market_data_hash` of the load the caller started from. A caller that pages through the history sends the hash of the first page in every later request; see D3. A refresh of the current episode starts a new load and sends no hash.

## D2 History and computation

For a request the Engine:

1. reads the market's committed bounds from market data (`earliest_committed_open_time_ms`, `latest_committed_open_time_ms`), a cheap call;
2. looks up the cache entry of `(ticker, base_timeframe, params_hash)` and checks it is valid (D3);
3. on a missing or invalid entry loads the candles of `[earliest, latest]`, takes the `market_data_hash` that market data returns for exactly that range, computes `EMA(fast)`, `EMA(anchor)` and `EMA(slow)` through the indicator range evaluation with the EMA kind the strategy feature plan uses, and runs `project_side` once;
4. stores the entity tables with the entry's version (bounds, `market_data_hash`, load time) and serves the page from them.

```text
request ──► parse_episode_params ──► bounds ──► entry valid? (D3)
                                                   │ yes ────────────────────────────┐
                                                   ▼ no                              │
                     candles [earliest, latest] ─► 3 EMAs ─► project_side ─► entry ──┤
                                                                                     ▼
                                                      page of whole episodes + current episode
```

Censoring stays the rule of `ema-stack-episode-v1`: only an episode that starts inside the slow-EMA warm-up at the start of the market's history is censored. It is returned with `censored: true` and without entities.

## D3 Cache and data version

- In-process, bounded LRU of projection results, configured by entry count (default 16). One entry per `(ticker, base_timeframe, params_hash)` holds both sides, so one candle read and one EMA computation serve both; it keeps the entity tables only (a few megabytes at most), not the per-bar series.
- **The version of an entry is the market data it was computed from**, not only the last candle:
  - the earliest and latest committed candle at load time;
  - the `market_data_hash` that market data returned for the loaded range. The engine treats it as opaque, as in `mds-historical-read-consumer-v1`;
  - the load time.
- **An entry is valid** when the current bounds equal its bounds and it was loaded or revalidated at most `revalidate_seconds` ago (setting `STRATEGY_ENGINE_EPISODE_HISTORY_REVALIDATE_SECONDS`, default 300).
- **Revalidation** reloads the candles of the entry's range and compares the returned `market_data_hash` with the entry's. Equal: the entry stays and its load time is reset, with no recompute. Different: the projection is recomputed and the entry replaced. So a repaired historical candle is picked up within `revalidate_seconds` even when the bounds are unchanged.
- **Pinned version.** When a request carries `expected_market_data_hash`:
  - if it equals the valid entry's hash, the page is served from the entry;
  - if it differs and the entry is valid (current bounds equal its bounds, within `revalidate_seconds`), the engine fails closed at once with `market_data_version_changed` (HTTP 409, details `expected_market_data_hash` and `actual_market_data_hash`) and returns no page, without reading the candles again;
  - if the entry is not valid (expired or bounds changed), it is revalidated first, as for any request, and the pin is compared with the resulting hash: equal serves the page, different gives the 409;
  - a pinned request that misses the cache loads the history; that load is the revalidation, and the same comparison applies to its hash;
  - the pin never selects an older entry: there is one entry per key.
- A caller therefore pages with the hash of its first page, and any change of the history between pages ends the paging with 409; the caller restarts from the first page.
- Concurrent misses or revalidations for the same key run once.
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
- `expected_market_data_hash` that differs from the hash of a valid entry, or of the entry after its due revalidation: `market_data_version_changed`, HTTP 409. The caller restarts from the first page.

## Risks

- **First request cost:** a cache miss computes the whole history. Measured on the full BTCUSDT.P 5m history (687,966 bars): the projection takes 0.62 s (long) and 0.67 s (short), the three EMAs hundredths of a second; the candle load comes on top. The route's own end-to-end time is measured and reported before merge (task 3.5). If it is too slow for the chart, the next step is an incremental continuation of the projection, not a change of this contract.
- **Rewritten history, unchanged bounds:** detected by revalidation within `revalidate_seconds`, and by the pin between pages. It relies on market data changing `market_data_hash` whenever any candle of the returned range changes. This is the contract the engine already assumes for the hash of a loaded range (`live-feature-frame-acquisition-v1`); the market-data side of the contract is checked in task 1.3.
- **Earliest candle changes:** a backfill of older data changes the history; the caller sees a new `earliest_ms` and drops its cache for that `history_id`.
- **Refresh and older episodes:** a refresh starts a new load and carries no pin, so a caller that keeps finished episodes across refreshes does not learn from the pin that older history was rewritten. It is out of scope here; the caller can drop its cache when `earliest_ms` or the `market_data_hash` of a full reload requires it.
- **Memory:** bounded by the LRU size.
- **Revalidation cost:** market data returns the hash of a range only together with a read of that range (measured on the owner's Mac: a full-history read of BTCUSDT.P 5m, 687,801 candles, costs 7.0 to 7.6 s in the market data audit; the bounds call costs 0.07 s and carries no content revision). So a revalidation is a full candle read without a recompute, at most one per key per `revalidate_seconds`. Detecting a correction without any full read would need a content revision counter in market data, which this change does not ask for.
