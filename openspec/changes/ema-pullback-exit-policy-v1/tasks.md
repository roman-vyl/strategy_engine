# Tasks: EMA Pullback exit policy v1

- [x] Port all standard signal-exit components.
- [x] Port ATR and constant-USD stop/take distance components.
- [x] Compile always-on and profile-local outputs.
- [x] Apply side-relative exit profile selection.
- [x] Preserve BBB stop readiness semantics.
- [x] Return per-rule and per-profile evidence.
- [x] Integrate exit policy into range evaluation.
- [x] Mark standard range evaluation `decisions_ready`.
- [x] Add direct legacy BBB parity tests.
- [x] Keep managed exit semantics explicitly out of scope.
- [ ] Treat a configured all-null stop or take series as not ready during warmup.
- [ ] Add regression coverage distinguishing configured all-null protection from an absent rule kind.
