## Why

Real-infra profiling of `EvaluateOpenTradeProjection` (production composition, real MDS HTTP, real DB, ETHUSDT.P 5m) found `exits.py`'s `_select`/`_select_bool` helpers costing ~3.72s per request (~47.5% of a ~7.83s median OpenTrade total) — larger than MDS I/O and larger than all indicator calculation combined. Root cause, confirmed by code audit: both helpers do a Python `for position, name in enumerate(profile): output.iloc[position] = values[name].iloc[position]` loop over the full bounded `FeatureFrame` (~48,819 bars), called 12 times per `evaluate_exit_policy()` invocation. A follow-up micro-benchmark (representative 48,819-row data, three profile-switching patterns, float-with-NaN and bool payloads) confirmed a numpy-vectorized positional-gather replacement produces byte-for-byte identical output (values, NaN positions, dtype, index) at ~190-250x the speed, with no new dependency (numpy is already a direct production dependency).

## What Changes

- Replace `_select`/`_select_bool`'s per-bar Python loop with a numpy stacked-matrix + integer-profile-code positional gather (`_PROFILE_CODE` lookup, `np.column_stack`, `np.arange` row selection). Output values, dtype (`float64`/`bool`), NaN positions, and `pd.Index` are unchanged.
- Preserve the current fail-fast behavior exactly: an unrecognized profile name SHALL still raise `KeyError` (via `_PROFILE_CODE[name]` dict lookup) — no `np.select`-style silent default is introduced.
- No change to `_select`/`_select_bool`'s signatures, their 12 call sites in `evaluate_exit_policy`, or any other function in `exits.py`.
- **BREAKING**: none — purely an internal implementation change behind two private helpers; every observable output of `evaluate_exit_policy`/`ExitPolicyEvaluation` is unchanged.

## Capabilities

### Modified Capabilities
- `ema-pullback-exit-policy-v1`: adds an explicit implementation-invariant requirement that per-bar profile selection within exit-policy evaluation is positional (index-position-based), not pandas label/index-aligned, and fails closed (raises) on an unrecognized profile name rather than silently defaulting. This makes an existing implicit guarantee explicit so a future "improvement" (e.g. a pandas merge/reindex-based rewrite) cannot silently change the semantics without violating a stated requirement.

## Impact

- Affected code: `src/strategy_engine/strategies/ema_pullback/exits.py` only (`_select`, `_select_bool`, plus a new `_PROFILE_CODE` module-level constant and a `numpy` import).
- Affected tests: the existing exit-policy test file, extended in place with parity/regression cases; no new test files.
- Unaffected: `evaluate_exit_policy`'s own logic, exit rule components, contexts, `FeatureFrame`, strategy spec schema, managed replay, MDS, application/public API, bounded-history planning.
- Expected performance: ~3.7s removed from a representative real-infra OpenTrade request (~47% of the measured ~7.83s total), confirmed by before/after real-infra benchmark as part of this change's acceptance.
