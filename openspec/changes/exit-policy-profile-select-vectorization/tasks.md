## 1. Implement the vectorized selector

- [ ] 1.1 Add `import numpy as np` to `src/strategy_engine/strategies/ema_pullback/exits.py`.
- [ ] 1.2 Add `_PROFILE_CODE = {name: i for i, name in enumerate(_PROFILE_ORDER)}` next to `_PROFILE_ORDER`.
- [ ] 1.3 Replace `_select`'s body with the numpy stacked-matrix + integer-code positional gather (design.md Decision 1): `np.column_stack` of `values[name].to_numpy(dtype=float)` for each `name in _PROFILE_ORDER`, codes via `_PROFILE_CODE[name]` for each `name in profile`, row selection via `matrix[np.arange(len(profile)), codes]`, wrapped in `pd.Series(..., index=index, dtype=float)`. Signature unchanged.
- [ ] 1.4 Replace `_select_bool`'s body with the same gather, `dtype=bool` throughout. Signature unchanged.
- [ ] 1.5 Confirm (by reading) all 12 existing call sites in `evaluate_exit_policy` are untouched — no call site should need to change.

## 2. Parity tests (extend the existing exit-policy test file)

- [ ] 2.1 All-neutral profile: `_select`/`_select_bool` output matches current behavior when every bar has the same profile.
- [ ] 2.2 Mixed profile: a profile tuple using all three names at different bars.
- [ ] 2.3 Switch-every-bar profile: profile alternates every single bar (stresses the positional gather, not just occasional switches).
- [ ] 2.4 Float values with `NaN` present in all three profile Series (not just the selected one) — assert only the selected-position NaN/non-NaN pattern appears in the output, non-selected-profile NaNs at the same position do not leak through.
- [ ] 2.5 Explicit NaN positional-selection check: for a position where the *selected* profile's series is NaN, output is NaN; for a position where the selected profile's series is not NaN but an *unselected* profile's series is NaN at that position, output is not NaN.
- [ ] 2.6 Bool selection: same profile patterns as 2.1-2.3, asserting exact bool values and `dtype=bool`.
- [ ] 2.7 Exact `pd.Index` preservation: output index is identical (`.equals()`) to the `index` argument passed in, including a non-default index (not just `RangeIndex`).
- [ ] 2.8 Exact dtype preservation: `_select` output is `float64`, `_select_bool` output is `bool`, in all above cases.
- [ ] 2.9 Unknown profile name still raises `KeyError` — a profile tuple containing a name not in `_PROFILE_ORDER`/`values` must raise, not silently produce NaN/False. Cover both `_select` and `_select_bool`.

## 3. Broader regression parity

- [ ] 3.1 Full `ExitPolicyEvaluation` parity on the existing exit-policy test fixture(s): every field (not just the 12 `_select`/`_select_bool`-derived ones) identical before/after.
- [ ] 3.2 Representative `evaluate_ema_pullback_frame`/`EmaPullbackEvaluation` regression: run the existing representative-spec test(s) and confirm no change to any field, not only `exit_policy`.

## 4. Repository quality gates

- [ ] 4.1 `pytest`
- [ ] 4.2 `ruff check src tests scripts`
- [ ] 4.3 `mypy src`
- [ ] 4.4 `git diff --check`

## 5. Real performance acceptance

- [ ] 5.1 Reproduce the same real local infrastructure and OpenTrade scenario used in the prior audit (production `build_services(settings)`, real local MDS HTTP, real DB, ETHUSDT.P 5m, the same source_plan/entry/target).
- [ ] 5.2 1 warm-up + 3 measured `EvaluateOpenTradeProjection.execute` calls before this change (pre-change commit, e.g. temporary worktree) and after, recording: isolated `_select`/`_select_bool` cost (or `evaluate_exit_policy` total as a proxy) and full OpenTrade wall-clock, for each run plus median.
- [ ] 5.3 Confirm all before-runs and all after-runs produce an identical business result, and before matches after exactly.
- [ ] 5.4 Record before/after numbers. Expect `evaluate_exit_policy`'s `_select`/`_select_bool` cost to drop from ~3.7s to low milliseconds, and full OpenTrade median to drop by a comparable amount, consistent with the prior audit's estimate (no fixed threshold required — record and compare).

## 6. Closeout

- [ ] 6.1 Confirm the changed-file set matches the proposed scope exactly: `src/strategy_engine/strategies/ema_pullback/exits.py` (production) and the existing exit-policy test file (extended in place) — no other file touched.
- [ ] 6.2 Record final before/after numbers (Group 5) and parity confirmation (Groups 2-3) in this file or the closing report, then archive per the repository's standard OpenSpec archive workflow.
