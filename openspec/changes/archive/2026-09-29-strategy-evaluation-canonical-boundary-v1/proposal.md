# Proposal: Strategy evaluation canonical boundary v1

## Why

Research Service just adopted a canonical strategy-instance identity —
`{strategy_id, ticker, base_timeframe, raw_spec}`, with `instance_id`
derived outside Engine and never sent as input, and `enabled` kept as
Composer/deployment metadata that never reaches evaluation. Strategy
Engine's historical/range boundary (`/v1/strategy-evaluations/range`,
`/range-batch`, `/managed-replay`, `/strategies/{id}/validate`,
`/strategies/{id}/feature-plan`) still requires the older
`StrategySpecEnvelope` shape: `strategy_id`, `strategy_version`,
caller-supplied `instance_id`, `raw_spec`, `compatibility_profile`.

A cross-repo audit (this session, file:line verified) established:

- `strategy_version` and `instance_id` are never read by calculation —
  only presence-checked (`strategies/application/validate_spec.py:21`)
  and echoed into the response
  (`strategies/ema_pullback/evaluator.py:56-57`,
  `adapters/http/strategy_serialization.py:16-17`). `instance_id` is not
  even part of `config_hash` (`strategies/contracts.py:22-30`).
- `compatibility_profile` gates exactly one thing: an equality check
  against the single literal `"bbb_v1"` in
  `strategies/application/build_feature_plan.py:17-19`. No other
  branch reads it. There is no second value, no differentiated planning
  behavior — a single-value gate is not a real compatibility
  dimension.
- The calculation core (`evaluate_ema_pullback_frame`,
  `strategies/ema_pullback/evaluation.py:47`) already reads only
  `raw_spec`. It is typed to accept either `StrategySpecEnvelope` or
  `LiveStrategySpec` — the live Runtime boundary (`LiveStrategySpec`:
  `strategy_id` + `raw_spec` only, `strategies/contracts.py:33-38`)
  already proves the envelope is not a calculation requirement.
- `POST /v1/strategy-evaluations/range-batch`
  (`strategies/application/evaluate_range_batch.py:26-62`) already
  acquires its shared `market_frame` exactly once before the variant
  loop and reuses it per variant — verified by the actual acquisition
  call site (line 40) sitting outside the loop (lines 42-53). This
  optimization exists today and has never been formalized in an
  OpenSpec capability: no baseline spec currently defines
  `/range-batch` at all.
- Research's `ValidateStrategyConfig.execute()` now sends canonical
  flat `DeployableStrategyInstance` dicts (`{enabled, strategy_id,
  ticker, base_timeframe, raw_spec}`) to
  `/strategies/{id}/authoring-config/validate`. Engine's
  `authoring_instance_to_envelope()`
  (`strategies/ema_pullback/authoring.py:29`) still expects the legacy
  nested Workbench shape (`instance_id`, `market{}`,
  `strategy.anchor_stack{}`, ...) and raises `InvalidRequestError` on
  every field Research no longer sends. **Every `/config/validate` and
  `/config/save` call against a real Engine fails today** — this is an
  active breakage, not a future risk.
- `/strategies/{id}/composer-catalog` still returns `family` as the
  strategy selector field (`strategies/composer/contracts.py:79`,
  `strategies/ema_pullback/composer_catalog.py:62-64`). Research's own
  recent change already confirmed `family` and `strategy_id` are the
  same concept under two names, with `strategy_id` as the retained
  name.

This change cuts Strategy Engine over to the canonical strategy input
cleanly: no caller-supplied `instance_id`, no `strategy_version`, no
`compatibility_profile`, no `family`, on any Research-facing evaluation
or validation boundary — matching what the live Runtime boundary
already does, and formalizing the range-batch shared-acquisition
behavior that already exists but was never specified.

## What changes

- Retire `StrategySpecEnvelope` as the strategy input for `/range`,
  `/range-batch`, `/managed-replay`, `/strategies/{id}/validate`, and
  `/strategies/{id}/feature-plan`. All five accept the same canonical
  strategy input Runtime's live endpoints already use: `strategy_id` +
  `raw_spec`, nothing else.
- Remove `strategy_version` from every Research-facing request,
  response, and catalog-metadata seam this boundary touches
  (`StrategyRangeResult`, `serialize_strategy_result`, the
  `_EMA_PULLBACK_SCHEMA` catalog entry). **BREAKING** wire response
  change for `/range` and `/range-batch` — a coordinated Research-side
  follow-up is required (see Cross-repo impact below), not implemented
  here.
- Remove caller-supplied `instance_id` from the same request/response
  seams. `config_hash` (kept, see below) no longer includes it — it
  never did.
- Remove `compatibility_profile` as a concept entirely: the field, the
  equality gate in `BuildStrategyFeaturePlan`, and the catalog-metadata
  echo. Not replaced by an Engine-internal default or constant — the
  single-value gate carried no real semantics to preserve.
- Formalize `POST /v1/strategy-evaluations/range-batch` in a new
  OpenSpec capability (it currently has none): canonical strategy input
  per variant, one shared request-level `market`, and a normative
  shared-acquisition-exactly-once requirement with a scenario that
  regression-tests it.
- Rewrite `/strategies/{id}/authoring-config/validate` to accept the
  canonical flat deployable-instance shape (`enabled`, `strategy_id`,
  `ticker`, `base_timeframe`, `raw_spec`) directly — no translation to
  a legacy envelope, no requirement for `instance_id`, `family`,
  `variant`, `strategy_version`, or `compatibility_profile`. `enabled`
  is accepted (Research sends it) but plays no role in validation.
- Rename `family` to `strategy_id` on the composer-catalog response and
  its internal parameter — the same concept, one name.
- Keep `config_hash` as a provenance/response field, not an identity
  concept, redefined over `{strategy_id, raw_spec}` only (its two
  remaining canonical inputs).
- Clarify `strategy-research-execution-contract-v1`'s generic "strategy
  identity" language to explicitly mean `strategy_id` + `config_hash`
  post-cutover — closing a real ambiguity an adversarial review of this
  proposal found: that requirement's wording could otherwise be read as
  still requiring `strategy_version`/`instance_id` in the response.

## Non-goals

- Changing live-entry (`/v1/strategy-evaluations/live-entry`) or
  open-trade (`/v1/strategy-evaluations/open-trade`) request/response
  shapes. They already use the canonical `LiveStrategySpec` shape this
  change generalizes to the historical boundary — this change makes
  the range/batch/managed-replay/validate/feature-plan boundary match
  them, not the other way around.
- Changing trading semantics, calculation results, or the calculation
  core (`evaluate_ema_pullback_frame` and everything it calls). Every
  seam touched here is envelope/transport, not calculation input.
- Changing indicator-catalog `compatibility_profile` metadata entries
  (`service/registries.py:33,50,67,84,101` — `_EMA_SCHEMA`,
  `_ATR_SCHEMA`, etc.). These are a coincidentally-named, unrelated
  indicator-capability descriptor concept, not the strategy-evaluation
  `compatibility_profile` this change removes. Out of scope.
- Implementing Research's own follow-up change: dropping its
  hardcoded `strategy_version`/`compatibility_profile` constants,
  updating `StrategyEvaluationResult` parsing for the narrower
  response, or building a range-batch HTTP client. Tracked as
  cross-repo impact only.
- Runtime code. Not touched, not affected — `LiveStrategySpec` and the
  live endpoints are unchanged by this proposal.
- Reconciling `market_data_hash`/`config_hash` into a single
  provenance concept, or adding a cache/dedup use for `config_hash`.
  Confirmed unused for caching anywhere in the codebase today; this
  change only narrows its input fields, it does not change its role.

## Compatibility

This is a clean cutover, matching Runtime's own breaking-cleanup
precedent (`live-entry-projection-v1`, `open-trade-projection-v1`).
No deprecated request models, no old/new unions, no aliases for
`strategy_version` or `family`, no synthetic `instance_id`, no default
`"v1"` or hidden `"bbb_v1"`, no legacy authoring adapter, no silent
acceptance of retired fields. Every canonical request boundary this
change touches uses strict (`extra="forbid"`) rejection of legacy
fields, consistent with the existing style on `/live-entry` and
`/open-trade`. A caller still sending the old shape fails closed with a
422, not a silent normalization.
