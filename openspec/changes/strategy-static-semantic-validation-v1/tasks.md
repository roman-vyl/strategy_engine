# Tasks: Strategy static semantic validation v1

## 1. Extract pure component-identity checks (no behavior change yet)

- [ ] `risk.py`: confirm `_risk_component_id`/`_SUPPORTED` are
      importable/reusable as-is from a new caller; no code change
      expected here beyond visibility if needed.
- [ ] `triggers.py`: confirm `_trigger_rule`/`_SUPPORTED` are
      importable/reusable as-is; no behavior change.
- [ ] `direction_blockers.py`: extract the `component_id` resolution
      + `"unsupported direction component"` check out of `_direction`
      into a small pure function; extract the per-item `component_id`/
      `instance_id` resolution + `"unsupported blocker component"`
      check out of the blocker dispatch function into a small pure
      function. Evaluator call sites call the extracted functions,
      behavior identical.
- [ ] `setups.py`: extract the `component_id`/`instance_id`
      resolution at the top of `_setup` (before `frame`-dependent
      branches) into a small pure function, including the
      `"unsupported setup component"` check. Evaluator call site
      calls the extracted function, behavior identical.
- [ ] `exits.py`: no extraction needed — `_policy_rules` is already
      pure; confirm it is importable from `feature_plan.py` and from
      the new static-semantics module.
- [ ] Run full existing test suite; confirm zero behavior change from
      this section alone (pure refactor, no new checks yet).

## 2. Add the shared identity-requirement utility

- [ ] Add a small, non-strategy-specific utility (module-level
      function) expressing "this rule/component requires a non-empty
      `instance_id`" with the existing `InvalidRequestError` message/
      path conventions — generalizing the private
      `_required_instance_id` currently local to `feature_plan.py`.
- [ ] Repoint `feature_plan.py`'s existing exit-rule instance_id check
      to the shared utility (no behavior change: same error message,
      same `exits[N].instance_id` path).
- [ ] Add the equivalent check for `setups[N].instance_id` using the
      same shared utility (this is new coverage — setups currently
      fall back to `component_id` instead of failing closed).

## 3. Build the static-semantics module and wire it into `ValidateStrategySpec`

- [ ] Add `strategies/ema_pullback/static_semantics.py` with
      `check_ema_pullback_static_semantics(raw_spec) -> None`,
      composing (in order): trade_sides structural check, direction
      component check, blockers component/identity checks, trigger
      component check, risk component check, setups component/
      identity checks (using the extracted functions from Section 1
      and the shared identity utility from Section 2), exit-rule
      component/identity checks (reusing `exits.py::_policy_rules`).
- [ ] Add `CheckStrategyStaticSemantics` (strategy-id dispatcher,
      mirrors `BuildStrategyFeaturePlan`'s shape) in
      `strategies/application/`.
- [ ] Wire `ValidateStrategySpec.__init__`/`.execute` to call
      `CheckStrategyStaticSemantics` before `feature_plan_builder`,
      per `design.md`'s ordering.
- [ ] Update `service/wiring.py` to construct and inject
      `CheckStrategyStaticSemantics`.
- [ ] Update `feature_plan.py`'s exit-rule walk to call
      `exits.py::_policy_rules` instead of re-implementing the
      always_on/profiles gather (removes the pre-existing
      duplication; behavior identical for valid specs).

## 4. Regression coverage

- [ ] Authoring-config validation: unsupported `component_id` for
      each family (blocker, trigger, risk, setup) individually
      → `valid=false`, stable `instances[N]` path, does not require a
      loaded `FeatureFrame`/market data to detect.
- [ ] Authoring-config validation: missing/empty `instance_id` on a
      setup (new coverage) and on an exit rule (existing coverage,
      confirm still passes after relocation) → `valid=false`.
- [ ] Authoring-config validation: malformed static structure
      (e.g. `raw_spec.trade_sides` missing/invalid, a blocker/trigger/
      risk entry that is not an object) → `valid=false`.
- [ ] Authoring-config validation: a fully correct canonical
      `ema_pullback` raw_spec (covering setups, blockers, triggers,
      risk, exits with valid component_ids and identities) →
      `valid=true`.
- [ ] Negative control: confirm a market-data-dependent runtime
      failure (e.g. `"market bars unavailable for setup evaluation"`)
      is NOT reachable from/reproduced by authoring-config validation
      — authoring validation only exercises `raw_spec`, never a
      `FeatureFrame`, so this is structural, not a new check; add one
      test asserting authoring validation does not require/accept
      market data input at all, to guard against future accidental
      coupling.
- [ ] Direct unit tests for `check_ema_pullback_static_semantics`
      (feature_plan/validate_spec test surface) covering each
      extracted pure function's positive and negative case, without
      going through HTTP.
- [ ] Unit tests confirming the extracted pure functions in
      `direction_blockers.py`/`setups.py` are still called correctly
      from their original evaluator call sites (no evaluator behavior
      regression) — reuse/extend existing evaluator test suites
      (`test_ema_pullback_direction_blockers.py`,
      `test_ema_pullback_setups.py`, `test_ema_pullback_triggers.py`,
      `test_ema_pullback_exits.py`).

## 5. Verification

- [ ] `make verify` (lint, typecheck, full test suite, release-check)
      green.
- [ ] `git diff --check` clean.
- [ ] `openspec validate strategy-static-semantic-validation-v1
      --strict` clean.
