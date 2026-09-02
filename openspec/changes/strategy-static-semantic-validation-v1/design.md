# Design: Strategy static semantic validation v1

## Where authoritative static semantic validation lives

`ValidateStrategySpec.execute` (`strategies/application/validate_spec.py`)
stays the single call site both authoring-config validation
(`/authoring-config/validate`) and pre-execution preparation
(`EvaluateStrategyRange._prepare`, `/strategies/{id}/validate`,
`/strategies/{id}/feature-plan`) already funnel through. Today it does
exactly one thing after registry/capability checks:
`self._feature_plan_builder.execute(strategy)`.

This change adds a second, parallel step to the same method — a
strategy-dispatched **static semantic check**, mirroring the existing
`BuildStrategyFeaturePlan` dispatch pattern:

```python
class ValidateStrategySpec:
    def __init__(
        self,
        registry: StrategyRegistryPort,
        feature_plan_builder: BuildStrategyFeaturePlan | None = None,
        static_semantics_checker: CheckStrategyStaticSemantics | None = None,
    ) -> None: ...

    def execute(self, strategy: LiveStrategySpec) -> str:
        ...  # existing strategy_id / registry checks unchanged
        self._static_semantics_checker.execute(strategy)   # new
        self._feature_plan_builder.execute(strategy)        # unchanged
        return strategy_config_hash(strategy)
```

`CheckStrategyStaticSemantics` is a thin strategy-id dispatcher, the
same shape as `BuildStrategyFeaturePlan`:

```python
class CheckStrategyStaticSemantics:
    def execute(self, strategy: LiveStrategySpec) -> None:
        if strategy.strategy_id != "ema_pullback":
            raise UnsupportedCapabilityError(f"strategy_static_semantics:{strategy.strategy_id}")
        check_ema_pullback_static_semantics(strategy.raw_spec)
```

Order matters: static semantic checks run *before* feature-plan
construction, so an unsupported `component_id` is reported as its own
clear error rather than surfacing indirectly as a missing-column
KeyError somewhere inside the indicator walk. Both steps still run
inside the same `ValidateStrategySpec.execute` call, so the existing
route behavior (catch the first exception, report
`instances[N]`/`{"path": ..., "message": str(exc)}`) is unchanged —
no new response shape, no aggregation of multiple errors, matching the
existing "Stable invalid-instance path" requirement.

## Avoiding independent copies of the same semantic rules — and the import-cycle constraint

The problem this design must not create: a second, hand-written
allowlist of legal `component_id`s that silently drifts from the one
the evaluator actually dispatches on. Several evaluator modules already
isolate their `component_id`/`instance_id` resolution as **pure
functions of `raw_spec` alone**, with no `FeatureFrame`/market-data
dependency (`risk.py::_risk_component_id`, `triggers.py::_trigger_rule`,
`exits.py::_policy_rules`, and the inline-but-pure `component_id`
resolution at the top of `direction_blockers.py::_direction`/blocker
dispatch and `setups.py::_setup`, ahead of their `frame`-dependent
branches) — the mechanism is to reuse these, not re-derive them.

The naive placement — leave each pure function inside its family
module (`exits.py`, `setups.py`, `direction_blockers.py`) and have
`feature_plan.py` import them directly, as an earlier draft of this
design proposed for `exits.py::_policy_rules` — creates a real import
cycle: `exits.py`, `setups.py`, and `direction_blockers.py` each
already import `EmaPullbackFeaturePlan` from `feature_plan.py` (for
their `plan: EmaPullbackFeaturePlan` parameter type). If
`feature_plan.py` then imports a pure helper back from any of them,
that is `feature_plan.py → exits.py → feature_plan.py` (and the same
shape for `setups.py`/`direction_blockers.py`) — a cycle, rejected.

**Resolution**: the pure `raw_spec`-only resolution functions do not
belong to any family's execution module at all — they belong on a
dependency-neutral boundary with zero knowledge of `EmaPullbackFeaturePlan`,
`FeatureFrame`, or any evaluator. A new module,
`strategies/ema_pullback/raw_spec_identity.py`, holds them:

- `iter_exit_rules(raw_spec) -> tuple[Mapping[str, Any], ...]` — the
  `always_on` + all three profiles' exits gather, moved out of
  `exits.py::_policy_rules` verbatim (pure already, no `frame`).
- `resolve_risk_component_id(raw_spec) -> str` — moved out of
  `risk.py::_risk_component_id` verbatim, together with the
  `_SUPPORTED` risk allowlist.
- `resolve_trigger_rule(raw_spec) -> Mapping[str, Any]` — moved out of
  `triggers.py::_trigger_rule` verbatim, together with the `_SUPPORTED`
  trigger allowlist.
- `resolve_direction_component_id(raw_spec) -> str` — extracted from
  the inline check in `direction_blockers.py::_direction` (line ~132).
- `resolve_blocker_identity(item) -> tuple[str, str]` (component_id,
  instance_id) — extracted from the inline resolution in the blocker
  dispatch function (line ~319).
- `resolve_setup_identity(item) -> tuple[str, str]` — extracted from
  the inline resolution at the top of `setups.py::_setup`.
- `require_non_empty_instance_id(instance_id, path) -> str` — the
  shared identity-non-emptiness utility (generalizes the already-
  shipped `feature_plan.py::_required_instance_id`).
- `require_unique_instance_ids(scope, pairs) -> None` — the shared
  uniqueness utility, directly modeled on old BBB's
  `spec.py::_validate_unique_instance_ids`: takes the domain's ordered
  `(instance_id, path)` pairs and raises on the first empty or
  repeated `instance_id`.

`raw_spec_identity.py` imports nothing from `feature_plan.py`,
`exits.py`, `setups.py`, `direction_blockers.py`, `triggers.py`, or
`risk.py` — only stdlib/`Mapping` typing and
`strategy_engine.domain.errors.InvalidRequestError`. Every one of
those six modules, plus the new `static_semantics.py`, imports *from*
`raw_spec_identity.py`, never the other way. This is a strict DAG:
`raw_spec_identity.py` sits below everything; `feature_plan.py` and
each family's execution module sit above it and never need to import
each other's pure logic directly. `feature_plan.py`'s existing
`plan: EmaPullbackFeaturePlan`-typed imports in `exits.py`/`setups.py`/
`direction_blockers.py` are unaffected — that edge (family module →
`feature_plan.py`, for the type) still points the same direction it
always has; it is simply never the edge carrying the shared pure
logic.

`exits.py`, `risk.py`, `triggers.py`, `setups.py`, and
`direction_blockers.py` each replace their local pure
function/allowlist with an import from `raw_spec_identity.py` — same
name, same behavior, so their own `InvalidRequestError` raises and
messages are unchanged; only the definition site moves.

A new thin module, `strategies/ema_pullback/static_semantics.py`,
holds only `check_ema_pullback_static_semantics(raw_spec) -> None` —
it imports the resolution and requirement functions from
`raw_spec_identity.py` and calls them in sequence (trade_sides shape →
direction → blockers component+identity+uniqueness → trigger
component → risk component → setups component+identity+uniqueness →
exit rules component+identity+uniqueness), raising the first
`InvalidRequestError` it hits with the existing path conventions
(`components.blockers[N]`, `components.trigger`, `components.risk`,
`setups[N].instance_id`, `exits[N].instance_id`). It reimplements no
allowlist or identity rule; it is pure composition/ordering, and it
too imports only from `raw_spec_identity.py` — no cycle risk there
either, since `ValidateStrategySpec` calls both
`CheckStrategyStaticSemantics` and `BuildStrategyFeaturePlan`
independently and neither needs to import the other.

This keeps exactly one place, system-wide, that says "these are the
legal `component_id` values and these are the identity requirements
per family" — `raw_spec_identity.py` — with every consumer (evaluator
modules, `feature_plan.py`, the new static-semantics module) importing
from it rather than redefining or re-deriving it, and no import cycle
anywhere in the dependency graph.

## Role of `BuildStrategyFeaturePlan`/`BuildLiveStrategyFeaturePlan` after this change

Unchanged in kind, narrowed in practice: it remains the indicator-
dependency walker (`ema-pullback-feature-plan-v1`'s "Caller supplies
strategy semantics, not indicator plans" — Engine still discovers
required indicator features internally). It keeps whatever *local*
shape preconditions it already needs to complete its own walk without
raising an unstructured `TypeError` (object/list shape checks,
positive-int parameter checks on the fields it reads for indicator
discovery) — these were never semantic-legitimacy checks, they are
"can I proceed to discover features" checks, and stay put.

It stops being — and this change does not make it become — the place
where component_id legitimacy or rule identity requirements live.
Those move to `raw_spec_identity.py` (or, for the already-shipped
exit-rule instance_id check, are relocated there from the private
`_required_instance_id` currently local to `feature_plan.py`).
`feature_plan.py`'s exit-rule loop calls
`raw_spec_identity.py::iter_exit_rules` for the always_on/profiles
walk instead of re-implementing it, and the identity check on each
rule becomes a call into `raw_spec_identity.py::require_non_empty_instance_id`
rather than an inline local helper — `feature_plan.py` depends
downward on `raw_spec_identity.py`, never sideways on `exits.py`.

## How this stays consistent with the evaluator (fail-closed execution preserved)

`evaluate_exit_policy`, `evaluate_setups`, `evaluate_direction_and_blockers`,
`evaluate_triggers`, and `evaluate_risk_and_entries` keep every one of
their existing runtime checks exactly as they are today — this change
does not remove or weaken any evaluator-side `InvalidRequestError`.
Static semantic validation becomes a strict superset check that runs
earlier and independently; if the shared pure functions are wired
correctly, the evaluator's own checks become unreachable in practice
for a `raw_spec` that already passed authoring validation, but they
remain in place as the last-resort fail-closed guarantee for any
`raw_spec` that reaches evaluation without having gone through
`ValidateStrategySpec` first (there is precedent for this today: the
exit-rule `instance_id` check already exists in both `feature_plan.py`
and `exits.py`, independently, precisely for this reason). No
evaluator code is deleted by this change.

## Uniqueness domains (old-BBB parity)

`require_unique_instance_ids` is called three times from
`static_semantics.py`, each with the domain old BBB's
`spec.py` enforced at construction time (see `proposal.md`'s "Why" for
exact file:line references):

- **setups**: one flat domain — every setup in `raw_spec.setups`, no
  sub-grouping.
- **blockers**: one flat domain — every blocker in
  `raw_spec.components.blockers`, no sub-grouping.
- **exit rules**: one flat domain spanning **all four exit groups
  combined** — `trade_management.exit_policy.always_on.exits` +
  `.profiles.aligned.exits` + `.profiles.countertrend.exits` +
  `.profiles.neutral.exits` together, not per-group. This matches old
  BBB's `ExitPolicySpec`/`TradeManagementSpec` behavior exactly: an
  `instance_id` reused between, say, `always_on` and `aligned` was
  already rejected pre-decomposition, not just an `instance_id`
  reused twice within the same group.

No uniqueness domain is invented beyond what old BBB already enforced;
`raw_spec_identity.py::iter_exit_rules` already gathers exactly the
four-group flat list `require_unique_instance_ids` needs for the exit
domain, so no separate traversal is needed for the uniqueness check.

## What this design deliberately does not do

- It does not introduce a canonical parsed/normalized strategy model
  (`raw_spec → parsed AST → validated model → feature planning →
  execution`). That was considered and rejected as the wrong size for
  this problem in the prior explore: it would touch every evaluator
  module's input handling for a benefit (a single parsed
  representation) this change does not need — reusing existing pure
  functions gets the "one source of truth" property without a new
  representation.
- It does not create a `GlobalStrategyInstanceValidator` spanning
  Research/Runtime/Engine. Engine remains the sole owner of
  `raw_spec` semantics; this design is entirely internal to Engine.
- It does not change what `enabled`/`ticker`/`base_timeframe` do —
  they still play no role in strategy validation semantics
  (`CanonicalStrategyInstanceModel`'s existing docstring stays true).
