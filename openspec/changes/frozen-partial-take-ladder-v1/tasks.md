Each group ends in a green, verifiable state. The no-regression gate
from group 0 runs again at the end of every group.

## 0. Baseline gate for specs without legs

- [x] 0.1 Before any code change, on `main` 07ff911, confirm that the
      declared-invariant gate (`tests/test_declared_invariants.py`,
      `tests/test_declared_invariants_managed.py`) already records the
      following for specs without partial takes:
      - `plan_hash` and plan labels;
      - node identities and compute counts;
      - the `/range-batch` public line including `entry_opportunities`;
      - `/managed-replay` and open-trade outputs.

      Add recorded `/live-entry` responses for fixed target bars on
      both sides if they are missing.

      Verify: the gate is green on unchanged code.
- [x] 0.2 Name in the gate the requirements it protects:
      - `batch-computation-reuse` "No compute regression for specs
        without partial takes";
      - `strategy-research-execution-contract-v1` "Optional partial
        takes on executable entry opportunities";
      - the `live-entry-projection-v1` scenario "Desired entry without
        partial takes".

      Verify: the gate's test ids or messages cite them.

## 1. Components and static validation

- [x] 1.1 `raw_spec_identity.py`: add `EXIT_PARTIAL_TAKE_SUPPORTED =
      {pct_partial_take, atr_partial_take}`. `static_semantics.py`
      accepts the family and enforces design D3 and D5:
      - fraction in (0, 1);
      - the sum below 1 per profile with `always_on`;
      - a final take in force;
      - `pct > 0`, `multiplier > 0`;
      - kind `partial_take`.

      There is no check of leg levels against the final take.

      Verify: unit tests in `test_ema_pullback_static_semantics.py`,
      one rejection per rule plus acceptance of a leg beyond the final
      take, all without market data.
- [x] 1.2 `exits._exit_rule_head`: add a `partial_take` family. A
      mismatch in either direction raises (`atr_partial_take` with
      `take_profit`, `atr_take_profit` with `partial_take`).

      Verify: unit tests in `test_ema_pullback_exits.py`.
- [x] 1.3 Authoring `/validate` path: a spec with each invalid ladder
      returns `valid=false`, and a valid ladder returns `valid=true`.

      Verify: cases in `test_authoring_config_validation_api.py`.

## 2. Exit policy evaluation and memo

- [x] 2.1 `exits._distance` gains the pct variant, and
      `atr_partial_take` reads its planned ATR column (design D2).
      `_ProfileSelection.partial_take` lists the legs in force. Legs are
      excluded from the take minimum, and `_ready` requires each leg in
      force.

      Verify:
      - leg evidence appears under its `instance_id` with
        `exit_kind` `partial_take`;
      - `take_profit_ratio_*` is unchanged by adding a leg;
      - readiness is false during ATR-leg warm-up.
- [x] 2.2 `feature_plan.py`: skip the kind-level `setdefault` for
      `partial_take` (design D9).

      Verify:
      - an ATR leg sharing (timeframe, period) with SL/TP plans one ATR;
      - a pct leg plans nothing;
      - `plan_hash` is unchanged for specs without legs.
- [x] 2.3 Memo resolve twins: `exit.distance.atr` for
      `atr_partial_take` and a new `exit.distance.pct`. The readiness
      aggregate includes legs only when present.

      Verify:
      - zero `unforeseen_consumptions` on a spec with both leg types;
      - candidates differing only in `fraction_of_initial` compute each
        distance node once per batch;
      - memoized and non-memoized outputs are bit-identical.
- [x] 2.4 Run the group 0 gate. Verify: green with no re-recording.

## 3. Historical contract

- [x] 3.1 `strategies/contracts.py`:
      - add `PartialTakeLeg`;
      - add `ExecutableEntryOpportunity.partial_takes = ()`;
      - widen `ExitAttribution.exit_kind` to include `"partial_take"`.

      Verify: contract unit tests in `test_domain_contracts.py`.
- [x] 3.2 `historical_execution_projection._entry_opportunities`:
      - add the legs of `always_on` plus the locked profile, with
        `ratio` from evidence at `bar_index`;
      - `fraction_of_initial` comes from the parsed rules;
      - attribution is direct;
      - sort by ratio, ties by declared order (design D7).

      Verify: tests in `test_historical_execution_projection.py` cover:
      - a leg of another profile excluded;
      - `initial_take` unchanged by legs;
      - order of mixed pct and ATR legs.
- [x] 3.3 `strategy_serialization._serialize_opportunity` writes
      `partial_takes` only when non-empty (design D6).

      Verify:
      - the spec scenario JSON for `pt_1pct` is reproduced exactly;
      - a spec without legs serializes byte-identically (group 0
        gate);
      - `contract_version` stays `strategy_evaluation_execution.v2`.

## 4. Live entry contract

- [x] 4.1 Keep per-leg absolute distances on the internal exit-policy
      result, not serialized on `/range` (design D8). Compute leg prices
      in the live entry projection:
      - ATR: `entry ± k·ATR`;
      - pct: `entry × (1 ± pct)`.

      Verify: a unit test reproduces the spec scenario (long 101/103,
      short 99/97), and the `/range` response is unchanged.
- [x] 4.2 Add `LivePartialTake` and `partial_takes = ()` on
      `LiveEntryPlan` and `DesiredEntry`. `_plan_for_side` returns `None`
      if any leg in force has a missing, non-positive or non-profit-side
      price. There is no comparison with `initial_take_price`.

      Verify: unit tests for the incomplete leg, the non-profit-side
      leg, and a leg beyond the final take (returned).
- [x] 4.3 HTTP `DesiredEntryResponseModel` omits `partial_takes` when
      empty.

      Verify:
      - an API test shows the `desired_entry` key set is unchanged
        without legs;
      - with legs it carries `{take_id, price, fraction_of_initial}`
        as decimal text.
- [x] 4.4 `live_calculation_requirements.py`: register both components
      as zero-lookback exits (design D10).

      Verify: a planner test with an `atr_partial_take` resolves with an
      explicit zero entry and does not fail closed, and requirements
      without legs are unchanged.

## 5. Untouched surfaces and end-to-end

- [ ] 5.1 Verify that managed and open-trade are untouched (design
      D11):
      - an open-trade projection for a trade whose entry had legs
        returns the same result as without legs;
      - `git diff` shows no change in `managed.py`,
        `historical_managed_projection.py` or
        `live_projections/open_trade.py`.
- [ ] 5.2 End-to-end `/range-batch` test over a fixture spec with one
      pct and one ATR leg in `always_on` and one leg in `aligned`.
      Verify:
      - opportunities carry the expected legs per locked profile;
      - `/live-entry` on the same fixture returns the same `take_id`s
        with prices given by the design D8 formulas on the target bar.
- [ ] 5.3 Full suite, ruff, mypy and `openspec validate
      frozen-partial-take-ladder-v1 --strict`. Verify: all green.
