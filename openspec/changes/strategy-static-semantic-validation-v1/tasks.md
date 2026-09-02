# Tasks: Strategy static semantic validation v1

## 1. Create the dependency-neutral `raw_spec_identity.py` module

- [x] Add `strategies/ema_pullback/raw_spec_identity.py` with zero
      imports from `feature_plan.py`, `exits.py`, `setups.py`,
      `direction_blockers.py`, `triggers.py`, or `risk.py` (only
      stdlib/`Mapping` typing + `InvalidRequestError`).
- [x] Move `risk.py::_risk_component_id` + `_SUPPORTED` into it
      verbatim as `resolve_risk_component_id`/`RISK_SUPPORTED`;
      `risk.py` imports both back under their original private names.
      No behavior change.
- [x] Move `triggers.py::_trigger_rule` + `_SUPPORTED` into it verbatim
      as `resolve_trigger_rule`/`TRIGGER_SUPPORTED`; `triggers.py`
      imports both back under their original private names. No
      behavior change.
- [x] Move `exits.py::_policy_rules` into it verbatim as
      `resolve_exit_rule_groups` (kept the dict-of-groups return shape
      `evaluate_exit_policy` needs — the task originally said
      `iter_exit_rules`/flat tuple, corrected here since `exits.py`'s
      own dispatch loop keys off the group name); `exits.py` imports
      it back as `_policy_rules`. No behavior change.
- [x] Extract the inline `component_id` resolution in
      `direction_blockers.py::_direction` (line ~132) into
      `resolve_direction_component_id(raw_spec) -> str` in the new
      module; extract the inline `component_id`/`instance_id`
      resolution in the blocker dispatch function (line ~319) into
      `resolve_blocker_identity(item) -> tuple[str, str]`.
      `direction_blockers.py` imports both back and calls them at the
      same call sites, before its `frame`-dependent branches. Also
      moved `_enabled_sides` (pure, `raw_spec.trade_sides` resolution)
      as `resolve_enabled_sides` — needed by the static-semantics
      trade_sides check in Section 3 and was already a pure function
      colocated with the other extractions. No behavior change.
- [x] Extract the inline `component_id`/`instance_id` resolution at
      the top of `setups.py::_setup` into
      `resolve_setup_identity(item) -> tuple[str, str]` in the new
      module. `setups.py` imports it back and calls it before its
      `frame`-dependent branches. No behavior change.
- [x] Add `require_non_empty_instance_id(instance_id, path) -> str`,
      generalizing the private `_required_instance_id` currently local
      to `feature_plan.py`.
- [x] Add `require_unique_instance_ids(scope, pairs) -> None`, modeled
      on old BBB's `spec.py::_validate_unique_instance_ids` (raises on
      first empty or repeated `instance_id` in the given ordered
      `(instance_id, path)` sequence).
- [x] Run full existing test suite; confirm zero behavior change from
      this section alone (pure refactor, no new checks reachable yet).
      428 passed, `uv run python -m pytest -q`.

## 2. Repoint the already-shipped exit-rule identity check

- [x] `feature_plan.py`'s exit-rule loop: replace its local
      `_required_instance_id` call with
      `raw_spec_identity.require_non_empty_instance_id`; replace its
      own `always_on`/profiles gather with
      `raw_spec_identity.resolve_exit_rule_groups` (flattened across
      groups for the indicator walk). Same error message, same
      `exits[N].instance_id` path, same behavior — confirm via
      existing regression tests
      (`test_ema_pullback_feature_plan.py::test_exit_rule_without_instance_id_is_rejected`,
      `test_atr_exit_rule_without_instance_id_is_rejected`, etc.).

## 3. Build the static-semantics module and wire it into `ValidateStrategySpec`

- [x] Add `strategies/ema_pullback/static_semantics.py` with
      `check_ema_pullback_static_semantics(raw_spec) -> None`,
      composing (in order): trade_sides structural check; direction
      component check; blockers component check + identity
      (non-empty) + uniqueness (flat domain: all blockers); trigger
      component check; risk component check; setups component check +
      identity (non-empty) + uniqueness (flat domain: all setups);
      exit-rule component check + identity (non-empty) + uniqueness
      (flat domain: `always_on` + all three profiles combined) —
      using `raw_spec_identity.py`'s functions/allowlists exclusively.
      Also moved `exits.py`'s `_SIGNAL_COMPONENTS`/`_DISTANCE_COMPONENTS`
      into `raw_spec_identity.py` as `EXIT_SIGNAL_SUPPORTED`/
      `EXIT_DISTANCE_SUPPORTED` (same pattern as risk/trigger), and
      named the blocker/setup allowlists implicit in
      `direction_blockers.py`/`setups.py`'s existing elif-chains as
      `BLOCKER_SUPPORTED`/`SETUP_SUPPORTED` (their dispatch shape is
      unchanged; only the static-semantics check reads these sets).
- [x] Add `CheckStrategyStaticSemantics` (strategy-id dispatcher,
      mirrors `BuildStrategyFeaturePlan`'s shape) in
      `strategies/application/check_static_semantics.py`.
- [x] Wire `ValidateStrategySpec.__init__`/`.execute` to call
      `CheckStrategyStaticSemantics` before `feature_plan_builder`
      (guarded `if self._static_semantics_checker is not None`, so
      existing tests constructing `ValidateStrategySpec` without a
      checker are unaffected).
- [x] Update `service/wiring.py` to construct and inject
      `CheckStrategyStaticSemantics`.
- [x] Confirmed via grep: no module in `strategies/ema_pullback/`
      imports `static_semantics.py`; `raw_spec_identity.py` has zero
      `from strategy_engine...` import edges back to any family module
      or `feature_plan.py`/`static_semantics.py` — the DAG `design.md`
      specifies. `mypy src` and full test suite both green.

## 4. Regression coverage

- [x] Authoring-config validation: unsupported `component_id` for
      each family (blocker, trigger, risk, setup) individually
      → `valid=false`, stable `instances[N]` path, does not require a
      loaded `FeatureFrame`/market data to detect.
- [x] Authoring-config validation: missing/empty `instance_id` on a
      setup, a blocker (both new coverage), and an exit rule (existing
      coverage, confirm still passes after relocation) →
      `valid=false`.
- [x] Authoring-config validation: duplicate `instance_id` within each
      uniqueness domain — two setups sharing one `instance_id`; two
      blockers sharing one `instance_id`; two exit rules sharing one
      `instance_id` where at least one pairing spans two different
      exit groups (e.g. one in `always_on`, one in `profiles.aligned`)
      to prove the domain is global across groups, not per-group →
      `valid=false` in every case.
- [x] Authoring-config validation: malformed static structure
      (e.g. `raw_spec.trade_sides` missing/invalid, a blocker/trigger/
      risk entry that is not an object) → `valid=false`.
- [x] Authoring-config validation: a fully correct canonical
      `ema_pullback` raw_spec (covering setups, blockers, triggers,
      risk, exits with valid, unique component_ids/identities) →
      `valid=true`.
- [x] Negative control: confirm a market-data-dependent runtime
      failure (e.g. `"market bars unavailable for setup evaluation"`)
      is NOT reachable from/reproduced by authoring-config validation
      — authoring validation only exercises `raw_spec`, never a
      `FeatureFrame`, so this is structural, not a new check; add one
      test asserting authoring validation does not require/accept
      market data input at all, to guard against future accidental
      coupling.
- [x] Direct unit tests for `check_ema_pullback_static_semantics` and
      for each `raw_spec_identity.py` function (including
      `require_unique_instance_ids`'s three domain call sites),
      without going through HTTP.
- [x] Unit tests confirming the extracted pure functions are still
      called correctly from their original evaluator call sites (no
      evaluator behavior regression) — reuse/extend existing evaluator
      test suites (`test_ema_pullback_direction_blockers.py`,
      `test_ema_pullback_setups.py`, `test_ema_pullback_triggers.py`,
      `test_ema_pullback_exits.py`).
- [x] A static import-graph test (or documented manual check) that
      `raw_spec_identity.py` has no import from any of
      `feature_plan.py`/`exits.py`/`setups.py`/`direction_blockers.py`/
      `triggers.py`/`risk.py`/`static_semantics.py` — guards the
      no-cycle property going forward.

## 5. Verification

- [x] `make verify` (lint, typecheck, full test suite, release-check)
      green.
- [x] `git diff --check` clean.
- [x] `openspec validate strategy-static-semantic-validation-v1
      --strict` clean.
