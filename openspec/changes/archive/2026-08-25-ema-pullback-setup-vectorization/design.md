## Context

`setups.py` has four remaining per-bar Python loops confirmed stateless and
safely vectorizable by audit (0 parity mismatches across edge + 200 random
cases per fragment). See proposal.md for motivation. Existing
`_combine_blocker_masks` (direction_blockers.py) already establishes the
AND-reduce pattern reused here.

## Goals / Non-Goals

**Goals:**
- Replace the four named fragments with exact-parity vectorized equivalents.
- Preserve positional/bar-index semantics identically (no label alignment
  assumptions, no silent shape changes).

**Non-Goals:**
- Vectorizing `_ema_bounce_counter` (stateful FSM, separate future task).
- Any change to `_apply_gate`, `pre_trigger`, or trace field names/shape.
- Restructuring `setups.py` beyond the four fragments.

## Decisions

**Decision 1 — `untouched_prior`:**
```python
arr = np.asarray(touch, dtype=bool)
n = len(arr)
shifted = pd.Series(arr).shift(1, fill_value=False)
seen = shifted.rolling(lookback, min_periods=lookback).max()
result = (~seen.fillna(1).astype(bool)).to_numpy()
idx = np.arange(n)
untouched_prior = np.where(idx < lookback, False, result)
```
`shift(1)` excludes the current bar from the window (matching
`touch[index-lookback:index]`); `min_periods=lookback` reproduces "full
lookback required"; positions `< lookback` are hard-forced to `False`
regardless of rolling output, matching the original's explicit `continue`
branch exactly (not merely "happens to match" — the original never even
inspects the window there).

**Decision 2 — `touch_active`:**
```python
touch_active = (
    pd.Series(np.asarray(first_touch, dtype=bool))
    .rolling(active_bars, min_periods=1)
    .max()
    .to_numpy()
    .astype(bool)
)
```
`min_periods=1` reproduces the original's start-of-series window clipping
(`max(0, index-active_bars+1)`) exactly, same as the already-shipped
`_rsi_blocker` pattern.

**Decision 3 — `recent_max`:**
```python
arr = np.asarray(width_atr, dtype=float)
finite = np.isfinite(arr)
roll_max = pd.Series(arr).rolling(lookback, min_periods=lookback).max()
roll_all_finite = (
    pd.Series(finite.astype(np.int8))
    .rolling(lookback, min_periods=lookback)
    .sum()
    .eq(lookback)
)
recent_max = roll_max.where(roll_all_finite, other=np.nan).to_numpy()
```
Ordinary `rolling().max()` silently skips NaN, which is NOT the original
semantics (`all(isfinite(v) for v in window)` gates the whole window to NaN
if any element is non-finite). The `roll_all_finite` gate is required and is
the one decision in this change that is not a mechanical copy of an existing
pattern. It is computed as a rolling **sum** of a 0/1 finiteness indicator
compared with `.eq(lookback)` — not `rolling(...).min().astype(bool)`: with
`min_periods=lookback`, an incomplete window (index+1 < lookback) produces
`NaN` from `.min()`, and `NaN` casts to `True` under `.astype(bool)`, which
would wrongly pass the gate for a not-yet-full window. `.eq(lookback)`
correctly evaluates a `NaN` sum to `False` (`NaN != lookback`), so the gate
is explicitly `False` — and `recent_max` is `NaN` — until a full window
exists, matching the original `window and all(...)` short-circuit exactly.
`min_periods=lookback` on both rollings reproduces "full lookback required"
(window empty when `index + 1 < lookback`).

**Decision 4 — `setups_ok` combine:**
```python
def _combine_setup_masks(
    mask_allowed: tuple[tuple[bool, ...], ...], length: int
) -> tuple[bool, ...]:
    if not mask_allowed:
        return tuple([True] * length)
    stacked = np.array(mask_allowed, dtype=bool)
    reduced = np.logical_and.reduce(stacked, axis=0, initial=True)
    return tuple(reduced.tolist())
```
Identical in shape to `direction_blockers._combine_blocker_masks`; not
imported/shared across modules to avoid coupling two independent capability
areas over a five-line helper — duplicated intentionally, consistent with
the "no incidental cross-module dependency" preference already applied in
this codebase.

## Risks / Trade-offs

- [Off-by-one in `untouched_prior`'s shift/window boundary silently passes
  fragment-local tests but diverges under rare real data shapes] → Mitigated
  by explicit first/last-bar and lookback-boundary test cases plus full
  `evaluate_setups` before/after parity on representative fixtures, not just
  fragment-level unit tests.
- [`recent_max`'s two-rolling finite-gate approach is more complex than a
  single `rolling().max()` call, harder to read at a glance] → Mitigated by
  a code comment explaining why plain rolling-max is insufficient (mirrors
  the `_rsi_blocker` isfinite-gate comment already in `exits.py`/
  `direction_blockers.py`).
- [`_combine_setup_masks` duplicates `_combine_blocker_masks` logic] →
  Accepted trade-off; five lines, avoids introducing a shared cross-module
  utility for this change's scope.

## Migration Plan

Single-step, no feature flag: replace the four fragments in place, run full
parity + regression suite, apply.
