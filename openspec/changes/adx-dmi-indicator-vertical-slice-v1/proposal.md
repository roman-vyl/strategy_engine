# Proposal: ADX/DMI Indicator Vertical Slice v1

Port BBB's coupled ADX, DI+, and DI- calculation into the independent Indicator Engine without changing formula, warmup, timeframe completion, or API value semantics.

The three public feature kinds remain `adx`, `di_plus`, and `di_minus` for BBB FeaturePlan compatibility, while the implementation computes and caches them as one `adx_dmi` group per timeframe/period.
