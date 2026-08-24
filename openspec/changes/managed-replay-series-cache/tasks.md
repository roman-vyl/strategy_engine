## 1. Regression / parity baseline

- [ ] 1.1 Capture a deterministic before-change semantic baseline on current `main`: for a fixed, existing test fixture (or a new small one if none reasonably covers a multi-rule managed replay) that exercises phase transitions, at least one ATR-based stop/phase condition, and at least one runtime exit reading a feature series (e.g. `ema_cross_loss_exit` and/or `rsi_signal_exit`), record: final `ManagedTradeState` (every field), the full ordered `events` tuple, the full ordered `bars` tuple, and (for the OpenTrade entry point specifically) `StartAfterEntryManagedProjection.desired_stop_price`/`desired_take_price`.
- [ ] 1.2 Confirm via a lightweight call-counting instrumentation (test-local monkeypatch of `_series`, not a repository change) how many times `_series()` is actually invoked for the same `output_id` within one replay call on this fixture, to have a concrete before-number to compare the after-number against in Group 4.

## 2. Per-replay lazy series cache

- [ ] 2.1 Inside `_evaluate_managed_replay_core`, create a local cache (`dict[str, tuple[float | None, ...]]`) at the start of the function, scoped to that single call -- no module-level or object-level state, no persistence beyond the function's return.
- [ ] 2.2 Add a small private helper (e.g. `_cached_series(cache, frame, output_id)`) that returns the cached tuple if `output_id` is already present, otherwise calls the existing `_series(frame, output_id)` once, stores it, and returns it. `_series()` itself is unchanged.

## 3. Wire cache through existing managed helpers

- [ ] 3.1 Thread the cache through `_feature_value` (used by `_phase_met`'s `mfe_atr`/`adx_di_threshold` branches and by the `break_even_stop`/`lock_profit_stop` ATR-based stop-management branches) so it calls `_cached_series` instead of `_series` directly.
- [ ] 3.2 Thread the cache through `_runtime_signal`'s `rsi_signal_exit` branch (the direct `_series(frame, output or "")` call) and `ema_cross_loss_exit` branch (the two direct `_series()` calls for fast/slow EMA) so both go through `_cached_series`.
- [ ] 3.3 Confirm (by reading, not by adding new call sites) that no other place in `managed.py` calls `_series()` directly outside of `_cached_series` itself -- the four sites above are the complete set per the design.md audit.

## 4. Semantic parity tests

- [ ] 4.1 Re-run the Group 1 fixture(s) after the Group 2/3 change and assert exact equality against the Group 1.1 baseline: final `ManagedTradeState` fields, every `ManagedPolicyEvent` (all fields, in order), every `ManagedBarDecision` (all fields, in order), `desired_stop_price`/`desired_take_price`. Use the existing comparison semantics already used by current managed-replay tests (exact dataclass/tuple equality) -- do not introduce a new tolerance policy.
- [ ] 4.2 Confirm via the Group 1.2 instrumentation that the number of `_series()` calls for a given `output_id` within one replay call is now at most 1 (i.e. the repeated-materialization pattern is actually eliminated, not just hidden).
- [ ] 4.3 Run the full existing managed-replay/OpenTrade test suite (`tests/test_ema_pullback_managed.py`, `tests/test_ema_pullback_start_after_entry_managed.py`, `tests/test_ema_pullback_managed_api.py`, `tests/test_open_trade_projection_composition.py`) and confirm no behavior change; add assertions to these files in place if a genuine parity gap is found, rather than creating new test files.
- [ ] 4.4 Confirm the public `OpenTradeProjectionResult` (desired_protection, close_signal, diagnostics) is unchanged for a real production-composition run on the same fixture used in Group 5, comparing against a captured before-change result.

## 5. Real performance acceptance

- [ ] 5.1 Reproduce the same real local infrastructure setup used for the original profile: production `build_services(settings)` composition, real local MDS HTTP, real DB, ETHUSDT.P 5m, the same (or an equivalent, explicitly recorded if bounds have moved) ~7-day open-trade scenario (source_plan/entry/target).
- [ ] 5.2 Run 1 warm-up + 3 measured `EvaluateOpenTradeProjection.execute` calls before the change (on the pre-change commit, e.g. via a temporary worktree as used for the `bounded-live-calculation-window` Group 7 acceptance) and record: managed-replay-only wall-clock (same profiling wrapper technique as the original audit) and full OpenTrade wall-clock, for each run plus median.
- [ ] 5.3 Run the same 1 warm-up + 3 measured calls after the change, on the same machine/DB/MDS, same scenario, and record the same measurements.
- [ ] 5.4 Confirm all before-runs produce identical business results to each other, and all after-runs produce identical business results to each other and to the before-runs (sanity check per the same method used in the original profile) -- if results differ, stop and report before drawing any performance conclusion.
- [ ] 5.5 Record before/after managed-replay median and full-OpenTrade median. The change is accepted only if: (a) the confirmed repeated full-series materialization pattern is eliminated (per Group 4.2), (b) managed-replay latency materially decreases (no fixed millisecond target promised in advance; a reduction from ~22s to single-digit seconds on the same scenario is the reasonable expectation set by the O(T×R×F) -> O(S×F+T×R) rationale in design.md, but the actual measured number is what is recorded and judged), and (c) full OpenTrade latency does not regress.

## 6. Closeout

- [ ] 6.1 Run repository quality gates: `pytest`, `ruff check src tests scripts`, `mypy src`, `openspec validate managed-replay-series-cache --strict`, `git diff --check`.
- [ ] 6.2 Confirm the actual changed-file set matches design.md's expected scope (`src/strategy_engine/strategies/ema_pullback/managed.py` plus existing test files only) -- if it does not, explain the deviation before proceeding.
- [ ] 6.3 Record the final before/after numbers (Group 5) and parity confirmation (Group 4) in this file or in the closing report, then archive the change per the repository's standard OpenSpec archive workflow.
