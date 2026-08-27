# Design: Strategy evaluation canonical boundary v1

## 1. Baseline and boundary

Current public evaluation surface and its strategy-input shape:

```http
POST /v1/strategy-evaluations/range          strategy: StrategySpecEnvelope
POST /v1/strategy-evaluations/range-batch    variants[].strategy: StrategySpecEnvelope
POST /v1/strategy-evaluations/managed-replay strategy: StrategySpecEnvelope
POST /strategies/{id}/validate               strategy: StrategySpecEnvelope
POST /strategies/{id}/feature-plan           strategy: StrategySpecEnvelope
POST /strategies/{id}/authoring-config/validate  instances[]: legacy Workbench shape
GET  /strategies/{id}/composer-catalog       response.family
POST /v1/strategy-evaluations/live-entry     strategy_id + raw_spec (flat, already canonical)
POST /v1/strategy-evaluations/open-trade     strategy_id + raw_spec (flat, already canonical)
```

`StrategySpecEnvelope` (`strategies/contracts.py:13-30`):
`{strategy_id, strategy_version, instance_id, raw_spec, compatibility_profile="bbb_v1"}`,
plus a `config_hash` property hashing all four non-`instance_id` fields.

`LiveStrategySpec` (`strategies/contracts.py:33-38`): `{strategy_id,
raw_spec}` — already the canonical shape, already proven sufficient:
`evaluate_ema_pullback_frame` (`strategies/ema_pullback/evaluation.py:47-67`)
is typed `strategy: StrategySpecEnvelope | LiveStrategySpec` specifically
because both shapes already work for calculation.

This design's target: retire `StrategySpecEnvelope` entirely. Every
seam that used it moves to `LiveStrategySpec`.

## 2. Goals / Non-Goals

**Goals:**
- One canonical strategy input (`strategy_id` + `raw_spec`) for every
  Research-facing evaluation and validation boundary, matching what
  live already uses.
- No caller-supplied `instance_id`, `strategy_version`, or
  `compatibility_profile` anywhere on this boundary — not optional,
  not defaulted, not aliased.
- Formalize the already-real range-batch shared-acquisition behavior in
  an OpenSpec capability, with a regression-guarding scenario, since
  none exists today.
- Replace the legacy authoring-to-envelope translator with direct
  canonical-instance validation.
- `family` → `strategy_id` on the composer-catalog response, the same
  rename Research already made on its own side.

**Non-Goals:**
- Live-entry/open-trade contracts (already canonical, unaffected).
- Calculation semantics, indicator math, feature-plan algorithm.
- Research-side code (constants, `StrategyEvaluationResult` parsing,
  range-batch client) — tracked as follow-up, not implemented here.
- Runtime code.
- Indicator-catalog `compatibility_profile` metadata — unrelated
  concept sharing a field name coincidentally.

## 3. Decisions

1. **Reuse `LiveStrategySpec`, don't invent a third canonical type.**
   The live boundary already proved `{strategy_id, raw_spec}` is
   sufficient input for `evaluate_ema_pullback_frame` and everything
   downstream. Introducing a separate `CanonicalStrategyInput` type
   with the same two fields would be a distinction without a
   difference. Rejected: keep `StrategySpecEnvelope` with optional
   fields — rejected per the clean-cutover requirement (no optional
   compatibility fields, no hidden defaults).

2. **`config_hash` moves to a standalone function, not a
   `LiveStrategySpec` property.** `LiveStrategySpec` is also the type
   used by `/live-entry` and `/open-trade`, whose own baseline specs
   explicitly forbid exposing `config_hash`/provenance in their
   responses ("SHALL NOT add request metadata, receipt identity,
   configuration-hash, or MDS-hash provenance" —
   `open-trade-projection-v1`, "Delegate through a strategy-family
   open-trade adapter"). A property on the shared type risks a future
   live-path implementer reaching for `strategy.config_hash` by
   habit. A standalone `strategy_config_hash(strategy: LiveStrategySpec)
   -> str` function, called explicitly only from `ValidateStrategySpec`
   and the range evaluator, keeps that boundary honest by construction
   rather than by convention.

3. **`config_hash`'s canonical input becomes `{strategy_id, raw_spec}`
   only.** Both `strategy_version` and `compatibility_profile` drop out
   of the hash along with the fields themselves — there is no
   intermediate state where the hash still depends on a field the
   request no longer carries. `config_hash` remains a
   provenance/response field (confirmed unused for any cache or dedup
   anywhere in the codebase), not a second identity concept — it is
   not renamed to or conflated with `instance_id`, and Engine does not
   attempt to derive Research/Runtime's `instance_id` on its own behalf
   anywhere in this boundary.

4. **`compatibility_profile` is deleted, not defaulted.** Factual check
   (`build_feature_plan.py:17-19`) confirms it gates exactly one
   equality comparison against the single literal value that has ever
   existed. There is no second profile, no differentiated planning
   path an implementer could accidentally collapse. Rejected: keep the
   field with a hardcoded Engine-internal default — rejected because
   the field selects nothing; keeping it would be exactly the "hidden
   `compatibility_profile = 'bbb_v1'`" the requesting instructions
   explicitly forbade. If a second strategy or profile family is ever
   introduced, the resulting selection mechanism should be designed
   against that real second case, not resurrected speculatively now.

5. **`/range-batch` gets its first OpenSpec capability, not a
   retrofit onto `ema-pullback-feature-range-v1`.** That capability's
   own Purpose is singular ("the coarse-grained EMA Pullback
   range-evaluation boundary") and its existing requirements describe
   one request, not a batch envelope with its own shared-market and
   shared-acquisition invariants. A dedicated
   `strategy-evaluation-range-batch-v1` capability gives the
   shared-L0 behavior a normative home it has never had, without
   overloading the singular-range spec's scope.

6. **`variant_id` keeps its name.** Confirmed ephemeral
   correlation-only (`evaluate_range_batch.py:27-29` pre-loop
   uniqueness check, `strategy_routes.py:186` response echo, never read
   by calculation). Renaming it would touch working code for no
   architectural gain — explicitly out of scope per the requesting
   instructions ("не даёт архитектурной пользы").

7. **Authoring validation is rewritten, not adapted.**
   `authoring_instance_to_envelope()` (`ema_pullback/authoring.py:29+`)
   is deleted along with the legacy `StrategyAuthoringValidationRequestModel`
   instance shape. The new typed instance model
   (`enabled`, `strategy_id`, `ticker`, `base_timeframe`, `raw_spec`,
   `extra="forbid"`) is validated directly into a `LiveStrategySpec`
   for the existing `ValidateStrategySpec`/`BuildStrategyFeaturePlan`
   pipeline — `ticker`/`base_timeframe`/`enabled` are accepted
   (Research sends them) but not read by validation; they are not
   silently dropped from the wire model (that would make the model
   permissive again), they are simply not consumed. Response entries
   drop `instance_id` (no longer derivable at this boundary) and keep
   `index`+`config_hash` — the existing `instances[N]`-path error
   convention already correlates by index, so nothing about
   the failure-identification contract regresses.

8. **`family` → `strategy_id` follows the same pattern Research's own
   change used**: rename, not alias. `ComponentCatalog.family`
   (`strategies/composer/contracts.py:79`) and
   `get_component_catalog(*, family=...)`
   (`ema_pullback/composer_catalog.py:62`) both rename; the
   `strategy_routes.py:55` call site updates to match.

## 4. Shared-L0 invariant — explicit protection

`EvaluateStrategyRangeBatch.execute()` (`evaluate_range_batch.py:26-62`)
today: validates variant-id uniqueness and range alignment, then calls
`self._market_data.load_range(...)` **exactly once** (line 40, before
the loop), then loops variants passing the same `market_frame` object
into each `StrategyRangeRequest` (lines 42-53). Changing `variants[].strategy`
from `StrategySpecEnvelope` to `LiveStrategySpec` touches only the
per-variant strategy field — it does not touch the acquisition call
site, the loop structure, or the `market_frame` reuse. The new
`strategy-evaluation-range-batch-v1` capability's "Shared market-data
acquisition" requirement (see spec delta) exists specifically so a
future change to this file cannot regress the one-acquisition-per-batch
property without also breaking a normative scenario, not just
"happening to still work" because nobody touched that code path.

## 5. Response-shape break and cross-repo sequencing

`serialize_strategy_result()` (`adapters/http/strategy_serialization.py:8-36`)
currently emits `strategy_version` and `instance_id` as required top-level
keys. Removing them is a breaking wire-response change for
`/range` and `/range-batch`. Research's `StrategyEvaluationResult`
(`research_service/domain/contracts.py`) currently declares both as
required (non-`Optional`) fields — parsing today's request against
tomorrow's Engine response would fail Research-side pydantic
validation. This change does not touch Research code. The dependent
Research-side follow-up (dropping those two required fields from
`StrategyEvaluationResult`, and no longer sourcing
`_ENGINE_STRATEGY_VERSION`/`_ENGINE_COMPATIBILITY_PROFILE` constants in
`run_backtest.py`) must land as its own coordinated change — sequencing
this Engine change first is intentional: Engine's response narrowing is
additive-safe to *deploy* before Research adapts (Research's current
required-field parsing would then fail closed with a clear
validation error, not silently misbehave), but Research's read path
must be updated before it can be exercised successfully end-to-end
again.

## 6. Risks / Trade-offs

- [Risk] Breaking `/range`/`/range-batch` response shape breaks
  Research's current parsing until its own follow-up lands →
  [Mitigation] Deliberate, sequenced clean cutover (see §5), not an
  oversight; Research's own change is already scoped in this
  proposal's cross-repo impact.
- [Risk] Removing `compatibility_profile` forecloses a future
  multi-profile mechanism without designing one →
  [Mitigation] Accepted: no second profile has ever existed;
  resurrecting a real mechanism later against a real second case is
  cheaper and more correct than keeping a permanently-single-valued
  gate "just in case."
- [Risk] Authoring-validation rewrite touches a wide test surface
  (fixtures across `test_authoring_config_validation_api.py` and
  siblings) → [Mitigation] Explicitly scoped in tasks.md; no test is
  left silently broken, all touched fixtures are enumerated as tasks.
- [Risk] `config_hash` semantics shift (drops two of its four inputs)
  could be mistaken for an identity change → [Mitigation] Explicitly
  stated in Decision 3 and in the spec delta: `config_hash` was never
  identity, remains provenance-only, and Engine still does not derive
  or echo any `instance_id`-equivalent value anywhere on this
  boundary.
