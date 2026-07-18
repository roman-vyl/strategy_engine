# Tasks: EMA Pullback potential entry for touch-anchor v1

## Slice 1 — Internal exit-distance preservation

- [x] Split distance-rule evaluation into raw absolute distance and legacy close-relative ratio without changing current rule semantics.
- [x] Preserve selected raw stop-loss and take-profit distance vectors for long and short inside `ExitPolicyEvaluation`.
- [x] Keep existing exit-policy wire output, ratios, readiness, profile selection, and evidence unchanged.
- [x] Add regression tests proving current exit-policy outputs are unchanged.

## Slice 2 — PotentialEntry domain and projector

- [x] Add the minimal immutable `PotentialEntry` model with `side`, `entry_price`, `stop_price`, and `take_price` vectors.
- [x] Add a transport-neutral touch-anchor potential-entry projector.
- [x] Use existing `SideSetupEvaluation.pre_trigger_allowed` as the internal pre-trigger gate.
- [x] Read the anchor vector from the existing planned feature mapping.
- [x] Calculate long and short absolute entry/stop/take prices from the anchor and selected raw distances.
- [x] Enforce all-present-or-all-absent values at every bar.
- [x] Require anchor, selected raw stop distance, selected raw take distance, and all derived prices to be finite and strictly greater than zero.
- [x] Return an empty `potential_entries` object for unsupported trigger components.
- [x] For `touch_anchor`, include only enabled-side keys and omit disabled sides.
- [x] Keep the complete potential-entry triple present on a touch bar when `pre_trigger_allowed` and all required values remain valid.

## Slice 3 — Range result and HTTP projection

- [x] Add the additive `potential_entries` group to `StrategyRangeResult`.
- [x] Invoke the projector from the existing EMA Pullback range evaluator without repeating feature or strategy calculation.
- [x] Serialize potential prices as normalized decimal text or `null`.
- [x] Keep parent response identity and provenance as the only source of hashes and market/spec metadata.
- [x] Update API contract tests for the additive response group.

## Slice 4 — Semantic verification

- [x] Test long `touch_anchor`: entry equals anchor, stop is anchor minus raw stop distance, and take is anchor plus raw take distance.
- [x] Test short `touch_anchor`: entry equals anchor, stop is anchor plus raw stop distance, and take is anchor minus raw take distance.
- [x] Test that close differing from anchor does not distort ATR-based potential stop/take distances.
- [x] Test bar-to-bar changes when anchor or ATR distance changes.
- [x] Test blocker/direction/setup denial through `pre_trigger_allowed` produces a fully absent triple.
- [x] Test feature warmup or unavailable distance produces a fully absent triple.
- [x] Test non-touch triggers serialize exactly as `potential_entries: {}`.
- [x] Test `touch_anchor` includes only enabled-side keys and omits disabled sides.
- [x] Test a bar where `touch_anchor` fires can contain both final entry `true` and a complete potential-entry triple.
- [x] Test zero and negative anchor, stop distance, take distance, or derived price suppress the complete triple.
- [x] Test multiple/profile-aware exit rules use the same selected minimum raw distance as existing ratio composition.
- [x] Test existing final entries, trigger evidence, exit-policy output, and managed replay remain unchanged.

## Acceptance

- [ ] Existing repository verification passes.
- [x] Every successful range evaluation contains a `potential_entries` object.
- [x] A non-touch trigger returns exactly an empty `potential_entries` object.
- [x] A successful `touch_anchor` range evaluation returns bar-aligned potential entry, stop, and take vectors for enabled sides only.
- [x] Every bar contains either a complete price triple or three null values.
- [x] Potential stop/take prices use raw initial distances and are not derived by applying close-relative ratios to the anchor.
- [x] No separate public `allowed`, `armed`, or `global_entry_allowed` state is added.
- [x] No Runtime, Abi, fill, order-type, or open-position behavior is implemented.
