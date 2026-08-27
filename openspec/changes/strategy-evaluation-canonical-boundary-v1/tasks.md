# Tasks: Strategy evaluation canonical boundary v1

## Slice 1 — Canonical contracts

- [ ] Retire `StrategySpecEnvelope` (`strategies/contracts.py:13-30`).
      Change `StrategyRangeRequest.strategy`, `StrategyBatchVariant.strategy`,
      `ManagedReplayRequest.strategy` from `StrategySpecEnvelope` to
      `LiveStrategySpec`.
- [ ] Add a standalone `strategy_config_hash(strategy: LiveStrategySpec) -> str`
      function (module-level, not a `LiveStrategySpec` property — design.md
      Decision 2) hashing `{strategy_id, raw_spec}` only.
- [ ] Remove `strategy_version` and `instance_id` fields from
      `StrategyRangeResult` (`strategies/contracts.py:64-80`); keep
      `config_hash` (now sourced from `strategy_config_hash()`).
- [ ] Confirm `LiveStrategySpec`, `LiveEntryProjectionRequest`,
      `OpenTradeProjectionRequest`, and every live-path contract are
      untouched by this slice (no field, type, or docstring change).

## Slice 2 — Application layer

- [ ] `ValidateStrategySpec.execute()` (`strategies/application/validate_spec.py:20-31`):
      drop the `strategy_version`/`instance_id` presence check; keep the
      `strategy_id` non-empty + known-strategy checks; return
      `strategy_config_hash(strategy)` instead of `strategy.config_hash`.
- [ ] `BuildStrategyFeaturePlan.execute()` (`strategies/application/build_feature_plan.py:14-21`):
      remove the `compatibility_profile != "bbb_v1"` branch entirely — no
      replacement gate, no default. Keep the `strategy_id != "ema_pullback"`
      check.
- [ ] `EmaPullbackRangeEvaluator.evaluate()` (`strategies/ema_pullback/evaluator.py:24-60`):
      stop echoing `strategy_version`/`instance_id` into `StrategyRangeResult`;
      source `config_hash` from `strategy_config_hash(request.strategy)`.
- [ ] `EvaluateStrategyRange`/`EvaluateStrategyRangeBatch`/`EvaluateManagedReplay`
      (`evaluate_range.py`, `evaluate_range_batch.py`,
      `evaluate_managed_replay.py`): no structural change expected beyond the
      type of `request.strategy` — confirm no other code in these three files
      reads a field being removed.
- [ ] Confirm `evaluate_range_batch.py:40`'s shared `market_frame` acquisition
      call site and the per-variant loop (lines 42-53) are untouched — this
      slice only changes `StrategyBatchVariant.strategy`'s type, not the
      acquisition/loop structure. Add/keep a regression test proving exactly
      one `MarketDataPort` call for a multi-variant batch (Slice 6).

## Slice 3 — HTTP models and routes

- [ ] Replace `StrategySpecEnvelopeModel` (`adapters/http/models.py:94-110`)
      with a new `LiveStrategySpecModel {strategy_id, raw_spec}`,
      `extra="forbid"`. Update `StrategyRangeRequestModel`,
      `StrategyBatchVariantModel`, `ManagedReplayRequestModel` to reference it.
- [ ] Update `/strategies/{id}/validate` and `/strategies/{id}/feature-plan`
      route handlers (`strategy_routes.py:58-73,100-115`) to accept
      `LiveStrategySpecModel` instead of `StrategySpecEnvelopeModel`.
- [ ] Add a new `CanonicalStrategyInstanceModel {enabled: StrictBool,
      strategy_id: StrictStr, ticker: StrictStr, base_timeframe: StrictStr,
      raw_spec: dict[str, Any]}`, `extra="forbid"` — every field required
      and strictly typed at the HTTP boundary (adversarial-review finding:
      this must be a real typed model, not `dict[str, Any]` with fields
      read-and-ignored downstream — a malformed/wrong-typed `enabled` or
      missing `ticker` SHALL 422, per
      `ema-pullback-authoring-config-validation-v1`'s "Malformed or missing
      canonical field" scenario). Change
      `StrategyAuthoringValidationRequestModel.instances`
      (`adapters/http/models.py:241-243`) from `list[dict[str, Any]]` to
      `list[CanonicalStrategyInstanceModel]`.
- [ ] Delete `authoring_instance_to_envelope()`
      (`strategies/ema_pullback/authoring.py:29`+) and the now-unused
      `_EXIT_KIND` table and every nested-shape parsing helper in that file
      that existed only to support it. Replace the `/authoring-config/validate`
      route handler (`strategy_routes.py:76-99`) to build
      `LiveStrategySpec(strategy_id=instance.strategy_id,
      raw_spec=instance.raw_spec)` directly per instance and call
      `strategy_config_hash()` for the success entry; drop `instance_id` from
      the response entry.
- [ ] Rename `ComponentCatalog.family` → `ComponentCatalog.strategy_id`
      (`strategies/composer/contracts.py:79`); rename
      `get_component_catalog(*, family=...)` → `get_component_catalog(*,
      strategy_id=...)` (`ema_pullback/composer_catalog.py:62-64`); update the
      call site (`strategy_routes.py:55`).
- [ ] `serialize_strategy_result()` (`adapters/http/strategy_serialization.py:8-36`):
      remove the `"strategy_version"` and `"instance_id"` response keys; keep
      `"config_hash"`.
- [ ] Managed-replay double-check (adversarial-review finding — confirmed no
      code change needed beyond Slice 1's type change, recorded here so the
      confirmation isn't lost): `ManagedReplayResult.to_wire()`
      (`strategies/ema_pullback/managed.py:154`) already contains no
      `strategy_version`/`instance_id`/`compatibility_profile` key —
      verified by inspection during spec review. No response-shape task is
      needed for managed-replay; only its request (Slice 1/2) and its test
      fixtures (Slice 6) change.

## Slice 4 — Registry/catalog metadata cleanup

- [ ] Remove `"strategy_version": "v1"` and `"compatibility_profile": "bbb_v1"`
      from `_EMA_PULLBACK_SCHEMA` (`service/registries.py:170-183`). Do NOT
      touch the unrelated indicator-schema `"compatibility_profile": "bbb_v1"`
      entries (`_EMA_SCHEMA`, `_ATR_SCHEMA`, `_ATR_DISTANCE_SCHEMA`,
      `_RSI_SCHEMA`, `_ADX_SCHEMA` at lines 33, 50, 67, 84, 101) — confirmed
      unrelated concept, out of scope (design.md Non-Goals).

## Slice 5 — Cross-cutting removal confirmation

- [ ] Grep-confirm zero remaining production references to
      `StrategySpecEnvelope`, `StrategySpecEnvelopeModel`, or
      `authoring_instance_to_envelope` anywhere in `src/`.
- [ ] Grep-confirm `strategy_version` and (caller-supplied) `instance_id` do
      not appear in any request/response Pydantic model or dataclass this
      change touches, except where they remain as internal Runtime/Research
      concerns this change does not reach (none expected).

## Slice 6 — Tests

- [ ] Update/replace fixtures in `test_domain_contracts.py`,
      `test_evaluate_strategy_range_batch.py`, `test_live_entry_projection.py`
      (only its `StrategySpecEnvelope`-adjacent parts, not its own
      already-canonical live fixtures) to construct `LiveStrategySpec`
      instead of `StrategySpecEnvelope`.
- [ ] Update every fixture/assertion touching `strategy_version`,
      `instance_id`, or `compatibility_profile` in: `test_atr_indicator.py`,
      `test_authoring_config_validation_api.py`,
      `test_ema_pullback_context_consumption.py`,
      `test_ema_pullback_direction_blockers.py`, `test_ema_pullback_exits.py`,
      `test_ema_pullback_feature_plan_api.py`, `test_ema_pullback_feature_plan.py`,
      `test_ema_pullback_feature_range_api.py`, `test_ema_pullback_managed_api.py`,
      `test_ema_pullback_setups.py`, `test_ema_pullback_triggers.py`,
      `test_foundation_api.py`, `test_rsi_indicator.py`,
      `test_release_contract.py`. For each: remove the retired fields from
      request construction; if the test asserted on `strategy_version`/
      `instance_id` in the *response*, update the assertion to the new
      response shape (no such keys) instead of deleting the test.
- [ ] Add/extend `test_authoring_config_validation_api.py` for: canonical
      flat-instance payload accepted; `enabled=true` and `enabled=false`
      validate identically; legacy `instance_id`/`market`/nested `strategy`
      fields rejected (422) before any instance is processed; successful
      entries contain `index`+`config_hash` and no `instance_id`.
- [ ] Add/extend `test_evaluate_strategy_range_batch.py` for the new
      `strategy-evaluation-range-batch-v1` scenarios: N-variant batch with a
      spy/counting `MarketDataPort` asserting exactly one `load_range` call;
      per-variant `strategy` in the canonical shape; duplicate `variant_id`
      rejected; a mid-batch variant failure does not trigger a second
      acquisition and does not prevent remaining variants from evaluating.
- [ ] Add a test confirming `/strategies/{id}/composer-catalog`'s response
      contains `strategy_id` and not `family`.
- [ ] Add a calculation-parity test: same `raw_spec` + market, evaluated once
      through the pre-change fixture shape (if still constructible in a
      throwaway test-local dataclass) and once through the new canonical
      shape, asserting identical `entries`/`potential_entries`/`exit_policy`
      — or, if reconstructing the old shape is impractical, assert against a
      committed pre-change golden fixture for the same `raw_spec`.
- [ ] Confirm `test_live_entry_projection_api.py` and
      `test_open_trade_projection_api.py` pass unmodified — this change must
      not touch their fixtures at all (design.md, live boundary unaffected).
- [ ] `openspec validate strategy-evaluation-canonical-boundary-v1 --strict`
      passes.
- [ ] Full repository test suite, lint, and type-check gates pass (this
      change's own implementation task, not run in this proposal-only pass).

## Slice 7 — Sequencing artifacts for the Research follow-up

This change is deliberately breaking for Research's current request/
response parsing (design.md §5). Rather than leave Research's follow-up
to infer the exact new wire shape from source, this slice adds explicit,
committed API-level tests that *are* the sequencing artifact — a
concrete reference for exactly what changed, with no separate fixture
file to keep in sync.

- [ ] `test_ema_pullback_feature_range_api.py`: add a test asserting the
      *exact key set* of a successful `/range` response top level (not
      just individual field presence) — this is the concrete "here is
      what Research must now parse" reference.
- [ ] `test_evaluate_strategy_range_batch.py` (or its HTTP-level sibling
      if one exists): same exact-key-set assertion for a successful
      range-batch variant outcome's embedded result.
- [ ] `test_ema_pullback_managed_api.py`: same exact-key-set assertion
      for the request Engine now expects (canonical `strategy` shape) —
      confirms Research's future request-construction target, even
      though the response itself is unchanged (Slice 3 confirmation).
- [ ] `test_authoring_config_validation_api.py`: same exact-key-set
      assertion for a successful authoring-validation response entry
      (`index`+`config_hash`, no `instance_id`).
- [ ] Cross-reference these four tests by name in this change's final
      report to whoever authors the Research-side follow-up change —
      they are the authoritative "what does Engine actually send now"
      answer, not the OpenSpec prose alone.

## Slice 8 — Cross-repo follow-up (tracked here, not implemented here)

- [ ] `research_service`: remove `_ENGINE_STRATEGY_VERSION`/
      `_ENGINE_COMPATIBILITY_PROFILE` constants and the `StrategyEvaluationRequest`
      fields that carried them; stop constructing the legacy envelope when
      calling Engine.
- [ ] `research_service`: relax `StrategyEvaluationResult` to no longer
      require `strategy_version`/`instance_id` from Engine's response (or
      remove the fields entirely if nothing downstream still needs them).
- [ ] `research_service`: implement a `range-batch` HTTP client method and
      switch `RunBatchExperiment` from N sequential single-range calls to one
      `range-batch` call, using `candidate_id` as the value of Engine's
      `variant_id`.
- [ ] `research_service`: update its own `authoring-config/validate` call site
      if the response shape it reads (`instance_id` per entry) changes to
      `index`-only correlation.
- [ ] Not this change's responsibility, tracked only: none of the above are
      implemented in `strategy_engine`.

## Slice 9 — Corrective: authoring path/body strategy_id invariant

Post-implementation audit finding: `/authoring-config/validate` checked
only `path strategy_id == "ema_pullback"`, not
`instances[i].strategy_id == path strategy_id` — unlike the sibling
`/validate` and `/feature-plan` routes, which already enforce that
equality. Closed per `ema-pullback-authoring-config-validation-v1`'s new
"Path/body strategy_id invariant" requirement.

- [x] `strategy_routes.py`: reject the whole authoring-validation request
      (422 `InvalidRequestError`, `instances[N].strategy_id`) before any
      instance reaches semantic validation, when any instance's
      `strategy_id` differs from the path `strategy_id`.
- [x] Regression tests: single mismatch rejected; mismatch among multiple
      instances identifies the offending index; mismatch is caught before
      semantic validation of the offending instance (not surfaced via
      `ValidateStrategySpec`'s unknown-strategy path).

## Slice 10 — Corrective: range-batch shared market-data provenance

Found while reviewing Research's Step 3 batch rebuild (which finally
began calling `/range-batch` for real): the shared L0 acquisition in
`EvaluateStrategyRangeBatch.execute()` never accepted an
`expected_market_data_hash`, unlike single-range evaluation, so it always
called `MarketDataPort.load_range()` unverified — trusting whatever MDS
returned rather than failing closed on a stale/wrong dataset the way
single `/range` already does. Not a new design: this brings batch's
shared-L0 acquisition up to the same fail-closed provenance contract
single-range evaluation already had.

- [x] `StrategyRangeBatchRequest` (`strategies/contracts.py`) and
      `StrategyRangeBatchRequestModel` (`adapters/http/models.py`): add
      optional `expected_market_data_hash`.
- [x] `EvaluateStrategyRangeBatch.execute()`: forward
      `expected_market_data_hash` to the shared `market_data.load_range()`
      call, and to each variant's `StrategyRangeRequest` (for the same
      defense-in-depth check `EvaluateIndicatorRange` already performs
      against a preloaded `market_frame`).
- [x] Regression tests: hash forwarded to the shared acquisition; absent
      hash means no verification requested (unchanged prior behavior);
      mismatched hash fails the whole batch before any variant is
      evaluated.
