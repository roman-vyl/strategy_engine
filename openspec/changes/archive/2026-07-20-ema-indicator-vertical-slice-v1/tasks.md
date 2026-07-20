# Tasks: EMA Indicator Vertical Slice v1

- [x] Reconfirm BBB EMA formula, feature naming, base/HTF resampling, and completion alignment.
- [x] Add EMA catalog definition and JSON schema.
- [x] Extend plan validation with strict EMA semantic validation.
- [x] Implement base-timeframe EMA evaluation.
- [x] Implement completed higher-timeframe EMA alignment.
- [x] Preserve caller-controlled output IDs and deterministic plan hash.
- [x] Serialize finite values as normalized decimal text and unavailable HTF values as null.
- [x] Update capability-aware readiness.
- [x] Add unit tests for invalid period/source/dependencies/timeframe.
- [x] Add API integration tests using a fake Market Data port.
- [x] Add golden parity tests that execute copied BBB calculation code.
- [x] Prove unsupported indicators and strategies still return structured 501 errors.
- [x] Update README, implementation notes, and master plan.
- [x] Run tests, compile checks, clean install, and cumulative patch verification.
