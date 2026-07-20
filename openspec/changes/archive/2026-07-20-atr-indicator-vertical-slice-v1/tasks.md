# Tasks: ATR Indicator Vertical Slice v1

- [x] Re-audit BBB `_true_range`, `_atr_rolling_mean`, resampling, and HTF alignment semantics.
- [x] Extract shared range-indicator frame operations from the EMA implementation.
- [x] Add focused ATR validation and formula module.
- [x] Add a registered multi-indicator range evaluator supporting EMA and ATR.
- [x] Expose ATR in catalog/schema endpoints.
- [x] Support base-timeframe ATR.
- [x] Support completed higher-timeframe ATR alignment.
- [x] Return Decimal text and exact validity/warmup metadata.
- [x] Add BBB golden parity for base and HTF ATR.
- [x] Add mixed EMA+ATR single-request API acceptance.
- [x] Run full local `make verify` with ruff and mypy.
