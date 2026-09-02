# Proposal: Strategy static semantic validation v1

## Why

Strategy Engine's authoring-config validation endpoint
(`POST /v1/strategies/{strategy_id}/authoring-config/validate`) is
documented as the authoritative check of `ema_pullback` strategy
semantics (`ema-pullback-authoring-config-validation-v1`, "Strategy
Engine SHALL own validation of `ema_pullback` instance semantics" /
"Validation SHALL ... reuse the canonical strategy validator"). In
practice, that "canonical strategy validator"
(`ValidateStrategySpec.execute` →
`BuildStrategyFeaturePlan.execute`/`build_feature_plan_from_canonical_spec`,
`strategies/ema_pullback/feature_plan.py`) is an indicator-dependency
walker: it only visits the parts of `raw_spec` needed to enumerate
required indicator features (EMA/ATR/RSI/ADX-DMI columns). It does not
check component_id legitimacy for blockers, triggers, risk, or setups,
and (until a recent targeted fix) did not require exit-rule
`instance_id` to be non-empty.

The result is a confirmed gap (found via cross-repo audit, file:line
verified): a `raw_spec` can pass authoring-config validation
(`valid=true`) and later fail deterministically inside the production
evaluator with a static, market-data-independent config error —
`"unsupported blocker component"` (`direction_blockers.py:319`),
`"unsupported trigger component"` (`triggers.py:193`), `"unsupported
risk component"` (`risk.py:70`), `"unsupported direction component"`
(`direction_blockers.py:133`), `"missing setup feature mapping"`
(`setups.py:424`) — none of these raise during `BuildFeaturePlan`,
only during `evaluate_direction_and_blockers`/`evaluate_setups`/
`evaluate_triggers`/`evaluate_risk_and_entries`, which require a
loaded `FeatureFrame` to even run. A live AutoResearch HOST smoke
already hit exactly this class of bug for exit-rule `instance_id`
(fixed in `feature_plan.py`, not reverted by this change — see Non-
goals).

This means `valid=true` from authoring-config validation is currently
weaker than the spec's own words promise: it verifies "this raw_spec's
indicator dependencies are constructible," not "this raw_spec's
strategy semantics are valid."

A separate, targeted old-BBB parity lookup (pre-decomposition
`research/strategies/ema_pullback/spec.py`, the dataclass-based
`EmaPullbackStrategySpec` construction-time validation that predates
Strategy Engine) confirms this gap is a **regression**, not new scope:
old BBB required `instance_id` to be mandatory, non-empty, and unique
for setups, blockers, and exit rules alike, enforced fail-closed at
spec-construction time —

- `SetupRuleSpec.__post_init__` (`spec.py:313`): non-empty
  `instance_id`; `EmaPullbackStrategySpec.__post_init__` (`spec.py:920`):
  `_validate_unique_instance_ids("setups", self.setups)` — unique
  across all setups in the strategy.
- `BlockerRuleSpec.__post_init__` (`spec.py:171`): non-empty
  `instance_id`; `ComponentStackSpec.__post_init__` (`spec.py:87`):
  `_validate_unique_instance_ids("components.blockers", self.blockers)`
  — unique across all blockers in the strategy.
- `ExitRuleSpec.__post_init__` (`spec.py:435`): non-empty
  `instance_id`; `ExitPolicySpec.__post_init__` (`spec.py:558-566`) and
  `TradeManagementSpec.__post_init__` (`spec.py:880-893`) both enforce:
  unique **globally across `always_on` and all three profiles
  (`aligned`/`countertrend`/`neutral`) combined** — not per-group.

Current Engine code preserves none of the uniqueness half of this:
`setups.py:415` falls back `instance_id` to `component_id` when
absent (silently permitting duplicate/collapsed identities instead of
failing closed), and no module checks uniqueness for setups, blockers,
or exits at all. Only the exit-rule non-empty check was restored by a
prior targeted fix; this change restores the rest of the same
old-BBB-canonical invariant class, not a new one.

## What changes

- Define, precisely, what `valid=true` from authoring-config
  validation SHALL mean going forward: the canonical strategy
  definition (`strategy_id` + `raw_spec`) contains no deterministic,
  market-data-independent config-semantic error that the production
  evaluator would otherwise raise only once evaluation actually runs.
- Extend the invariants authoring-config validation checks to cover
  the categories already proven to exist as a gap: unsupported
  `component_id` for any component family the evaluator dispatches on
  (blocker, trigger, risk, setup, exit); missing/empty rule or
  component `instance_id` where old BBB required identity (setups,
  blockers, exit rules); and duplicate `instance_id` within each of
  old BBB's three uniqueness domains (setups: unique across all
  setups; blockers: unique across all blockers; exits: unique
  globally across `always_on` + all three profiles combined) — see
  "Why" above for the exact old-BBB precedent per domain.
- Introduce a small internal mechanism inside `strategy_engine` so
  these checks are expressed once and reused by both the authoring
  validator and the evaluator that already enforces them at
  execution time — not duplicated by hand into `feature_plan.py`.
  (Design left to `design.md`; this proposal fixes the target
  behavior and boundaries, not the internal code shape.)
- `BuildStrategyFeaturePlan`/`BuildLiveStrategyFeaturePlan` keep their
  existing role — indicator-dependency discovery — and do not grow
  into a general-purpose semantic validator. Whatever new static
  checks this change adds live alongside, not inside, the indicator
  walk, wherever the design in `design.md` places them.
- Modify `ema-pullback-authoring-config-validation-v1`'s "Canonical
  semantic validation" requirement to state the invariant class
  precisely instead of only naming "the canonical strategy validator"
  without defining its scope.

## Scope

- Strategy Engine only: `strategy_engine/strategies/ema_pullback/*`,
  `strategy_engine/strategies/application/validate_spec.py`, and the
  authoring-config validation HTTP path
  (`adapters/http/strategy_routes.py`).
- The `ema_pullback` strategy family, since it is the only strategy
  currently registered and validated.
- The already-merged mandatory non-empty exit-rule `instance_id`
  invariant (`feature_plan.py`) is retained as-is; this change may
  relocate or generalize its implementation per `design.md`, but does
  not weaken or remove the invariant itself.
- Restoring old-BBB identity invariants (mandatory non-empty
  `instance_id`, plus uniqueness within each domain named above) for
  setups and blockers, which never had them in Strategy Engine at all.

## Non-goals

- No change to any HTTP request/response wire shape. The authoring-
  config validation endpoint's request/response contract (`{instances:
  [...]}` in, `{valid, errors, instances}` out) is unchanged —
  invalid instances already report `valid=false` with an
  `instances[N]` path; this change only widens which raw_specs qualify
  as invalid, without changing that shape.
- No new HTTP endpoint, no new external validation contract.
- No change to Research Service production code. Research already
  delegates strategy semantics to Engine and propagates `ok=`
  Engine's `valid` verbatim (`application/research/config_validation.py`)
  — that boundary is correct and untouched. Only Engine-facing mock
  semantics in Research's own regression tests may need updating to
  reflect the now-stricter Engine contract, tracked separately, not as
  part of this change's tasks.
- No change to Runtime (`strategy_runtime`). Runtime's deployment-
  catalog envelope validation and the HTTP shape of its live-entry/
  open-trade calls are unaffected; whether/where Runtime should call
  authoring validation at discovery time is a separate, larger
  lifecycle question explicitly out of scope here. This is distinct
  from Engine's *own* internal live-entry/open-trade validation depth
  (`ValidateLiveStrategySpec`, Engine-side code Runtime calls into) —
  that gate is in scope and covered by this change, since it is the
  same class of static-semantic gap on a second Engine entrypoint, not
  a Runtime change.
- No attempt to validate market-data availability, runtime/position
  state, external service availability, or the numeric result of
  strategy evaluation. Authoring validation stays a static, data-free
  check.
- No exhaustive enumeration of every parameter of every
  `ema_pullback` component. This change defines the authoritative
  invariant class and the mechanism; the existing per-component
  OpenSpec capabilities (`ema-pullback-setups-v1`,
  `ema-pullback-triggers-v1`, `ema-pullback-risk-entries-v1`,
  `ema-pullback-direction-blockers-v1`, `ema-pullback-exit-policy-v1`)
  remain the source of truth for concrete component semantics.
- No refactor of `feature_plan.py`'s indicator-dependency logic itself
  beyond what is needed to host or call into the new shared static
  checks.

## Compatibility

Fully backward compatible for any `raw_spec` that was already
semantically valid — those continue to validate successfully with an
identical response shape. Only `raw_spec`s that were already
deterministically doomed to fail in production (per the invariant
classes above) newly report `valid=false` at authoring time instead of
failing later during evaluation. No caller that only ever submitted
semantically valid strategies observes any behavior change.
