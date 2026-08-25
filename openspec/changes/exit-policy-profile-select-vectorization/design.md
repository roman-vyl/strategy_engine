## Context

See proposal.md for the measured profile and audit. `exits.py::_select`/`_select_bool` currently implement per-bar profile selection as:

```python
for position, name in enumerate(profile):
    output.iloc[position] = values[name].iloc[position]
```

`profile` is a `tuple[str, ...]` (one profile name per bar, always one of `_PROFILE_ORDER = ("aligned", "countertrend", "neutral")` per `context_consumption.py`'s `_VALID_REGIMES`), `values` is a `dict[str, pd.Series]` with exactly those three keys, and `.iloc[position]` on both sides makes this strictly positional (never label/index-aligned). A prior benchmark (representative 48,819-row data, three profile-switching patterns) measured ~0.28-0.31s per call for this loop and confirmed a numpy stacked-matrix + integer-code gather reproduces identical output at ~190-250x the speed.

## Goals / Non-Goals

**Goals:**
- Eliminate the confirmed O(bars) Python-loop cost in `_select`/`_select_bool`.
- Preserve exact positional semantics, dtype, NaN positions, and `pd.Index` identity.
- Preserve fail-closed behavior on an unrecognized profile name.

**Non-Goals:**
- No change to `evaluate_exit_policy`'s architecture, call sites, or any other helper in `exits.py`.
- No change to `ExitPolicyEvaluation`'s fields or `to_wire()` shape.
- No broader vectorization pass over other parts of `evaluate_ema_pullback_frame` (out of scope for this tiny change; a separate audit already identified other candidates, tracked separately).

## Decisions

**1. Numpy stacked-matrix + integer profile codes (not `np.select`).**
```python
_PROFILE_CODE = {name: i for i, name in enumerate(_PROFILE_ORDER)}

def _select(profile, values, index):
    matrix = np.column_stack([values[name].to_numpy(dtype=float) for name in _PROFILE_ORDER])
    codes = np.fromiter((_PROFILE_CODE[name] for name in profile), dtype=np.intp, count=len(profile))
    return pd.Series(matrix[np.arange(len(profile)), codes], index=index, dtype=float)
```
`_select_bool` is identical with `dtype=bool`. Rationale: benchmarked at parity with an `np.select`-based alternative (~190-250x speedup either way), but `np.select` requires a `default=` value for positions matching no condition — which, for an unrecognized profile name, silently returns that default (e.g. `np.nan`) instead of raising. The dict-lookup form (`_PROFILE_CODE[name]`) raises `KeyError` on an unrecognized name, identical to today's `values[name]` `KeyError` — preserving fail-closed behavior without adding a separate validation step. This is the deciding factor between the two equally-fast candidates.

**2. `_PROFILE_CODE` built once from `_PROFILE_ORDER`, module-level.**
Keeps the mapping from profile name to matrix-column-index as a single source of truth alongside the existing `_PROFILE_ORDER` tuple, rather than recomputing it per call.

**3. Positional-not-label-aligned is stated as an explicit spec requirement (not just a code comment).**
`np.column_stack`/`.to_numpy()` inherently discard pandas index alignment (arrays have no labels), so today's positional intent becomes structurally guaranteed by the new implementation rather than only being an artifact of `.iloc` usage. The spec delta makes this an explicit, testable requirement so a future change (e.g. a pandas `.merge`/`.reindex`-based "simplification") cannot silently reintroduce label-alignment semantics without visibly violating a stated contract.

## Risks / Trade-offs

- **[Risk] A future edit reintroduces label-based alignment (e.g. swaps `.to_numpy()` for a `pd.concat`/`.reindex` step) and silently changes semantics if all input series happen to share the same index today.** -> Mitigation: the new spec requirement (positional, not label-aligned) plus an explicit test asserting positional behavior under an artificially mismatched/reset index, so a regression would fail a stated requirement, not just "look different" in review.
- **[Trade-off] `np.column_stack` allocates one `(F, 3)` intermediate array per call (12 calls per `evaluate_exit_policy`).** -> Accepted: still O(F) allocation (same order as the existing per-call `pd.Series` outputs), and the benchmark showed this cost is negligible (~1-2ms) next to the ~280-310ms eliminated.

## Migration Plan

Single-step: internal implementation swap behind two private helpers with unchanged signatures and 12 unchanged call sites. No feature flag, no phased rollout. Rollback: revert the one commit; no persisted state or external contract involved.
