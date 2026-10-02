## 1. Initial-R Rule Parsing and Validation

- [ ] 1.1 Add shared parsing for `initial_r_lock_stop` and `initial_r_trailing_stop`, including finite-number checks and trigger/action bounds.
- [ ] 1.2 Add focused validation tests for accepted boundary values, rejected parameter combinations, missing fields, and non-finite inputs.
- [ ] 1.3 Register both components as zero-lookback managed stops and prove feature planning adds no indicator solely for them.

## 2. Single-Trade and Live Managed Evaluation

- [ ] 2.1 Implement the shared initial-R trigger and candidate-price primitive using frozen initial risk, monotonic MFE, and side.
- [ ] 2.2 Integrate both components into the existing managed candidate list without changing tighten-only arbitration, attribution, or event timing.
- [ ] 2.3 Add long/short tests for 6R-to-4R locking, the 6R/7R/8R/11.5R trailing sequence, phase-plus-trigger gating, retracement, competing stops, and unavailable initial risk.
- [ ] 2.4 Add source-bar/next-bar tests proving a newly calculated stop cannot execute against its source bar.
- [ ] 2.5 Extend legacy regression coverage to prove `break_even_stop`, buffered BE, and `lock_profit_stop` outputs remain unchanged.

## 3. Managed Replay HTTP Contract

- [ ] 3.1 Add optional side-validated `initial_stop_price` to the HTTP and domain managed-replay request contracts.
- [ ] 3.2 Thread the field through the application service to the existing internal evaluator parameter while preserving omission and fail-closed behavior.
- [ ] 3.3 Add strict HTTP tests for valid long/short inputs, omitted input, invalid side ordering, equal price, non-positive/non-finite values, and unchanged legacy request shape.

## 4. Historical Projection Contract

- [ ] 4.1 Extend `ManagedStopActionRule` with the closed `stop_formula` semantic and optional opaque trigger-distance reference.
- [ ] 4.2 Project initial-R trigger and action values as opaque constant distance series for lock and trailing rules.
- [ ] 4.3 Update HTTP serialization to emit formula/trigger fields only for new rules and add a byte-stability regression for legacy stop actions.
- [ ] 4.4 Extend projection reference/parity fixtures for the new formulas without exposing component ids or named raw parameters.
- [ ] 4.5 Prove projected stop timelines, update bars, rule attribution, and next-bar boundaries match single-trade evaluation for both sides and multiple entries.

## 5. Verification and Cross-Repository Handoff

- [ ] 5.1 Run focused managed-policy, historical-projection, API, live-window, serialization, and invariant test suites.
- [ ] 5.2 Run the full Engine test and static-quality gates and record any unrelated pre-existing failures separately.
- [ ] 5.3 Verify the serialized new and legacy projection fixtures decode in the coordinated Research change and document Research-first deployment ordering.
- [ ] 5.4 Run `openspec validate initial-r-stop-management-v1 --strict` and reconcile proposal, specs, design, and completed tasks before implementation handoff.
