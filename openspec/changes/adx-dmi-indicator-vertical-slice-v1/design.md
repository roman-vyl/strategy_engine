# Design: ADX/DMI Indicator Vertical Slice v1

## Legacy semantics

The implementation copies `_wilder_rma` and `_compute_adx_dmi` semantics from the preserved BBB calculations module. Directional movement, true range, Wilder bootstrap, recursive updates, explicit DI warmup, DX, and ADX warmup are unchanged.

## Public contract

`IndicatorPlan` accepts `kind=adx|di_plus|di_minus`, `source=close`, and a positive integer `period`. BBB-compatible output IDs remain caller-owned. Catalog entries declare the common `calculation_group=adx_dmi`.

## Execution

A range evaluation groups requests by resolved timeframe and period. One grouped calculation produces ADX, DI+, and DI-. Requested series are selected from that grouped result. HTF values use the existing completed-bucket alignment.
