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

## Avoiding independent copies of the same semantic rules

The problem this design must not create: a second, hand-written
allowlist of legal `component_id`s that silently drifts from the one
the evaluator actually dispatches on. Two facts from the existing code
make this avoidable without inventing a new rule format:

1. Several evaluator modules already isolate their `component_id`
   resolution as a **pure function of `raw_spec` alone**, with no
   `FeatureFrame`/market-data dependency:
   - `risk.py::_risk_component_id(raw_spec) -> str` +
     `component_id not in _SUPPORTED` (`_SUPPORTED` is already a
     module-level constant).
   - `triggers.py::_trigger_rule(raw_spec) -> Mapping` +
     `component_id not in _SUPPORTED` (same pattern).
   - `exits.py::_policy_rules(raw_spec) -> dict[str, tuple[Mapping, ...]]`
     — pure, gathers `always_on` + all three profiles' exits exactly
     like `feature_plan.py` does independently today (an existing,
     pre-dating duplication this change also removes for exit rules).
   - `direction_blockers.py`/`setups.py` resolve `component_id` inline
     inside `_direction`/`_setup`, mixed with `frame`-dependent
     branches, but the `component_id` comparison itself needs nothing
     but the raw item.

2. `_SUPPORTED`-style allowlists and inline `if component_id ==
   ...`/`raise InvalidRequestError("unsupported ... component", ...)`
   chains already exist once per family, at the exact point that
   currently only fires at evaluation time.

The mechanism: extract (where not already extracted) each family's
`component_id`-resolution-and-legitimacy-check into one small pure
function per family, colocated in that family's existing module
(`triggers.py`, `risk.py`, `direction_blockers.py`, `setups.py`,
`exits.py`) so the file that owns a family's runtime dispatch also
owns the one authoritative list of legal `component_id`s and identity
requirements for that family. Concretely, per family:

- **risk** (`risk.py`): `_risk_component_id`/`_SUPPORTED` are already
  exactly this — reuse as-is, call from the static-semantics module.
- **triggers** (`triggers.py`): `_trigger_rule`/`_SUPPORTED` — same,
  reuse as-is.
- **direction/blockers** (`direction_blockers.py`): extract the
  existing inline `component_id` comparisons in `_direction` (line
  ~132) and the blocker dispatch (line ~319) into small pure
  functions returning the resolved `component_id` (and, for blockers,
  the per-item `instance_id`) without requiring `frame`; the
  `raise InvalidRequestError("unsupported ... component", ...)` calls
  move with them and are reused verbatim by both the new pure
  functions and the existing evaluator call sites (evaluator calls the
  pure function first, then proceeds with `frame`-dependent branches).
- **setups** (`setups.py`): extract the `component_id`/`instance_id`
  resolution currently inline in `_setup` (before the `frame`-using
  branches) the same way; this is also where the setup-side instance-
  identity requirement (see below) is enforced, generalizing the
  exit-rule pattern.
- **exits** (`exits.py`): `_policy_rules` is already pure and already
  duplicated by `feature_plan.py`'s own `always_on`/profiles walk —
  this change makes `feature_plan.py` call `_policy_rules` instead of
  re-implementing the walk, removing that pre-existing duplication as
  a side effect. The already-shipped non-empty-`instance_id` check
  (currently a private `_required_instance_id` helper local to
  `feature_plan.py`) moves to a small shared static-semantics utility
  (module-level function, no class) used for both exit rules and
  setups, since both are "rule/component identity the evaluator keys
  a mapping by."

A new thin module, `strategies/ema_pullback/static_semantics.py`,
holds only `check_ema_pullback_static_semantics(raw_spec) ->
None` — it imports and calls the small pure functions above from
each existing module and raises the first `InvalidRequestError` it
hits (existing exception type, existing message conventions,
`raw_spec`-relative paths like `exits[N].instance_id`,
`components.blockers[N]`, `components.trigger`, `components.risk`,
`setups[N].instance_id`, matching the path conventions
`feature_plan.py` already uses). It does not reimplement any
allowlist or identity rule; it is pure composition/ordering.

This keeps exactly one place per family that says "these are the
legal `component_id` values and these are the identity requirements"
— the family's own execution module — with the static-semantics
module only sequencing calls into them, and `feature_plan.py` staying
focused on indicator-dependency discovery (calling `_policy_rules` for
its own walk instead of re-deriving the exit list by hand).

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
Those move to (or, for the already-shipped exit-rule instance_id
check, are relocated to) the shared static-semantics utilities
described above. `feature_plan.py`'s exit-rule loop calls
`exits.py::_policy_rules` for the always_on/profiles walk instead of
re-implementing it, and the identity check on each rule becomes a call
into the shared static-semantics utility function rather than an
inline `_required_instance_id` local to `feature_plan.py`.

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
