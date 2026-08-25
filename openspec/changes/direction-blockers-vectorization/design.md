## Context

See proposal.md for the measured profile and the completed audit (call-graph, semantic checklist, 29-case parity matrix, synthetic benchmark). Current structure (`src/strategy_engine/strategies/ema_pullback/direction_blockers.py`), all three functions operate on plain `tuple[float, ...]`/`tuple[bool, ...]` (via `_float_series`, which already converts `frame.series` text to floats) -- there is no pandas `Index`/label-alignment concern anywhere in this module today, unlike `exits.py`'s `_select`/`_select_bool` (already vectorized in a prior change).

## Goals / Non-Goals

**Goals:**
- Eliminate the three confirmed Python-loop hotspots without changing any observable output.
- Preserve `ema-pullback-direction-blockers-v1`'s existing documented semantics exactly (RSI `min_periods=1` memory, trend-strength backward-search/reason-priority, AND-composition).

**Non-Goals:**
- No change to `_direction`, `_blocker`'s `no_blockers`/`counter_candle_blocker` branches, `_gate_for`/`_apply_gate`, or any other function in this file.
- No change to `setups.py`, `exits.py`, `serialize_value`, indicator calculation, or `FeatureFrame`.
- No new abstraction/helper module -- vectorized bodies live inline in the same three functions/call site they replace.

## Decisions

**1. `_rsi_blocker`: `np.isfinite` gate + `pandas.Series.rolling(lookback, min_periods=1).max()`.**
```python
arr = np.asarray(values, dtype=float)
finite = np.isfinite(arr)
extreme = finite & (arr > threshold) if side == "long" else finite & (arr < threshold)
seen = pd.Series(extreme).rolling(lookback, min_periods=1).max().to_numpy().astype(bool)
allowed = tuple((~seen).tolist())
```
The explicit `finite &` term is required, not redundant: a naive `arr > threshold` alone would let `+inf` pass as "extreme" for the long side (`inf > threshold` is `True` in numpy), which diverges from today's `isfinite(value)` gate. `rolling(lookback, min_periods=1).max()` reproduces the exact "shortened window at the start" behavior of `extreme[max(0, i-lookback+1):i+1]` -- confirmed identical across 10 parity cases including `lookback=1`, `lookback` larger than the series, and mixed `+inf`/`-inf`/NaN input.

**2. `_trend_strength_blocker`: positional "running last qualifying index" instead of nested backward scan.**
```python
qualifies = finite & (adx >= min_peak) & (aligned | (not require_alignment))
candidate_idx = np.where(qualifies, np.arange(n), -1)
running_last_true = np.maximum.accumulate(candidate_idx)
peak_index = np.where(running_last_true >= idx - peak_lookback + 1, running_last_true, -1)
```
`np.maximum.accumulate` over per-position candidate indices (`-1` where not qualifying) gives, at each `i`, the largest index `<= i` where `qualifies` was `True` anywhere so far -- exactly the "most recent qualifying bar found scanning backward" the original nested loop computes, in one vectorized pass instead of an O(n x peak_lookback_bars) worst-case scan. The window check (`running_last_true >= i - peak_lookback_bars + 1`) reproduces the original's `start = max(0, index - peak_lookback + 1)` bound.

The remaining elif-chain (`no_recent_adx_peak` -> `peak_too_old` -> `current_adx_too_low` -> `opposite_di_flip` -> allowed) is expressed as a sequence of `np.where` applications in the *same priority order* as the original, each one only overriding positions not already decided by an earlier, higher-priority check -- this ordering is the part most at risk of a subtle bug if reimplemented carelessly (e.g. applying `current_adx_too_low` before `peak_too_old` would change which reason wins on a bar where both conditions hold), so it is called out explicitly as the primary implementation risk (see Risks).

The current-bar-not-finite gate (`indicator_not_ready`, forcing `peak_index=-1`/`bars_since=-1` unconditionally, independent of whether a real peak exists) is applied as a final override after computing `peak_index`/`bars_since` from the vectorized path, matching the original's early-`continue` that skips peak search entirely for a not-ready current bar.

**3. Final combine: `np.logical_and.reduce(..., initial=True)` with an explicit empty-blockers branch.**
```python
if not blocker_allowed_tuples:
    return tuple([True] * length)
stacked = np.array(blocker_allowed_tuples, dtype=bool)
reduced = np.logical_and.reduce(stacked, axis=0, initial=True)
```
The explicit `if not blocker_allowed_tuples` branch is not currently reachable via `evaluate_direction_and_blockers` (its caller always supplies at least one blocker, defaulting to a `no_blockers` placeholder), but is kept as an explicit, tested guard rather than relying on `np.logical_and.reduce`'s behavior on a zero-length stacked array to happen to match Python's `all([]) == True` -- fail-safe correctness over relying on incidental numpy behavior for an edge case not exercised by any current caller.

## Risks / Trade-offs

- **[Risk] `_trend_strength_blocker`'s elif-chain priority is silently reordered during vectorization, changing which `blocked_reason` wins when multiple conditions hold on the same bar.** -> Mitigation: each `np.where` step in the vectorized version is applied in the identical order to the original's elif-chain, and the acceptance plan requires exact `reasons`/`peak_indices`/`bars_since` parity (not just `allowed`) across all 13+ trend-strength test cases from the audit, including cases specifically constructed so more than one blocking condition would apply at once.
- **[Risk] The current-bar-not-finite gate and the candidate-bar-finite gate inside the backward search get conflated (e.g. a not-finite bar accidentally treated as a valid candidate, or a finite current bar incorrectly forced to `indicator_not_ready`).** -> Mitigation: `qualifies` only ANDs in the candidate's own `finite`; the current-bar gate is a separate, final override applied after the vectorized peak search, matching the original's structurally separate checks. Explicit test case: candidate bars with NaN inside the lookup window while the current bar itself is finite.
- **[Trade-off] `pandas.Series.rolling(...)` allocates an intermediate `pd.Series`/rolling-window object for `_rsi_blocker`.** -> Accepted: same order of allocation cost as the `pd.Series` outputs already used throughout `exits.py`'s already-shipped vectorization; negligible next to the eliminated per-bar Python loop.

## Migration Plan

Single-step: internal implementation swap behind the same function signatures, same call sites (`_blocker()` for A/B, `evaluate_direction_and_blockers` for C). No feature flag, no phased rollout. Rollback: revert the one commit; no persisted state or external contract involved.
