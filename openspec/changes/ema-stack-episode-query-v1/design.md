## Context

`ema-stack-episode-v1` added a per-side projection of the EMA stack episode (`project_side`), reachable only through a strategy that declares `raw_spec.ema_stack_episode`. Its result is exposed by `/strategy-evaluations/range/diagnostics` together with every dense feature series. A chart needs the episode without a strategy and without the dense trace.

## Goals

- One computation of the episode for every consumer: the same parameter parser, the same EMA implementation and the same projector.
- A compact, cacheable, read-only response for a market, a display range and episode parameters.
- Results inside the display range that do not depend on where the range starts, as long as the history policy covers the episode.

## Non-goals

- Changing any episode rule.
- Serving strategy decisions, trades or diagnostics from this route.
- A front-end specific model with its own math.

## D1 Route and request

`POST /v1/ema-stack-episodes/range`

```json
{
  "market": {"ticker": "BTCUSDT.P", "base_timeframe": "5m", "from_ms": 1704067200000, "to_ms": 1735689600000},
  "episode": {"fast_period": 500, "anchor_period": 1000, "slow_period": 2000, "window_bars": 24, "break_bars": 24, "history_bars": 15000},
  "sides": ["long", "short"],
  "series": []
}
```

- `market` uses the existing `MarketRangeModel`. `[from_ms, to_ms)` is the display range.
- `episode` is validated by the canonical parameter parser shared with `raw_spec.ema_stack_episode` (`parse_episode_params`, extracted from `parse_episode_section`). The three periods are required here because there is no `anchor_stack` to default from. `window_bars` defaults to 24, `break_bars` to `window_bars` and `history_bars` to 15000, exactly as in the section. Unknown keys are rejected.
- `sides` defaults to both. `series` is an optional list of state or event field names (`STATE_FIELDS`, `EVENT_FIELDS`); default empty.
- `expected_market_data_hash` is optional, with the same meaning as in `/strategy-evaluations/range`.

## D2 History

The Engine loads more than the display range:

- `computed_from_ms = from_ms − (ema_warmup_bars(slow_period) + history_bars) × step`, clamped to the earliest committed candle of the market;
- `computed_to_ms = to_ms`.

This is the history the live window plans for an episode (`ema_warmup_bars` for the EMAs, `history_bars` for the episode), so the query sees what live sees at `to_ms`. Censoring stays the rule of `ema-stack-episode-v1`, applied to the computed range: an episode is censored only when it starts inside the slow-EMA warm-up of the computed range. With the default history, an episode that started before `from_ms` keeps its real start bar and its touch numbers.

The response reports `computed_from_ms`, so the caller knows which range the result belongs to.

## D3 One computation path

```text
request ──► parse_episode_params ──► indicator plan: EMA(fast), EMA(anchor), EMA(slow)
                                         │  same EMA implementation and plan hashing
                                         ▼
                              project_side(high, low, close, fast, anchor, slow, params, side)
                                         ▼
                              side_to_wire  ──► clip to [from_ms, to_ms) ──► segments
```

- EMAs come from the indicator range evaluation over the computed range, with the same EMA kind the strategy feature plan uses.
- The projector is `project_side`, unchanged. The strategy path (`build_episode_bundle`) and this route call it with the same inputs for the same parameters and range.
- Clipping and segments are presentation over the projection output; they do not feed back into it.

## D4 Response

```json
{
  "market": {"ticker": "...", "base_timeframe": "5m", "from_ms": 0, "to_ms": 0, "computed_from_ms": 0},
  "episode": {"fast_period": 500, "anchor_period": 1000, "slow_period": 2000, "window_bars": 24, "break_bars": 24, "history_bars": 15000},
  "params_hash": "...",
  "market_data_hash": "...",
  "sides": {
    "long": {
      "episodes": [...], "zones": [...], "false_breaks": [...], "waves": [...],
      "segments": [{"from_ms": 0, "to_ms": 0, "episode_id": 1, "phase": "away", "touch_number": 2}],
      "series": {"time_ms": [...], "touch_number": [...]}
    },
    "short": {...}
  }
}
```

- **Entities** have the shape of `side_to_wire` in `ema-stack-episode-v1` (points as `time_ms`, plus `known_at`). Bar indices refer to the computed range and are omitted; only `time_ms` is returned.
- **Clip:** an episode, zone, false break or wave is returned when its span intersects `[from_ms, to_ms)`. A span runs from its first point to its last point or `known_at`, whichever is later; an open entity runs to the last bar.
- **Segments:** maximal runs of consecutive bars with the same `(episode_id, phase, touch_number)`, clipped to the display range. `phase` is one of `none` (no active episode), `away`, `in_zone`, `in_false_break`, `stack_break` (the break bar). Segments cover the display range without gaps.
- **Series:** only when `series` is non-empty, on the display range's own `time_ms` axis.
- **Identity:** `params_hash` is the hash of the effective parameters and the node version of the episode. With `market_data_hash` it identifies the response.

Size: for a year of BTCUSDT.P 5m both sides carry about 230 zones, 100 false breaks, 230 waves and a few thousand segments, a few hundred kilobytes of JSON.

## D5 Effective parameters of a strategy

`/strategies/{id}/feature-plan` already returns `episode_columns_by_ref` when a spec declares episodes. It also returns `episode_params_by_ref`: the effective `EpisodeParams` of each `episode_ref` after defaults (`anchor_stack` periods, `window_bars`, `break_bars`, `history_bars`). A caller that shows the episode of a strategy sends these parameters to the query. Specs without the section return neither field, so their plans and hashes are unchanged.

## D6 Errors

- Invalid parameters, unknown keys or unordered periods: the same `InvalidRequestError` messages as the strategy section, with paths under `episode`.
- Unknown series names or sides: `InvalidRequestError`.
- Market data mismatch with `expected_market_data_hash`: the same error as `/strategy-evaluations/range`.

## Risks

- **Clamped history:** near the start of a market's data the computed range is shorter; the first episode can then be censored. The response shows it through `censored` and `computed_from_ms`.
- **Two callers, one parser:** the shared `parse_episode_params` is the only parser; the section parser becomes a thin caller that adds the `anchor_stack` defaults.

## Open question

- Default `history_bars` for a chart is the live default, 15,000 bars (about 52 days of 5m). A caller may lower it for speed; values below the episode's real length censor episodes that started earlier.
