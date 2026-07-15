# ADX/DMI Indicator Vertical Slice v1

This slice ports BBB's coupled Average Directional Index and Directional Movement calculations into the independent Indicator Engine.

## Public features

The API preserves the three BBB FeaturePlan kinds:

- `adx`
- `di_plus`
- `di_minus`

Each accepts `source="close"`, one positive integer `period`, and no dependencies. Catalog schemas expose `calculation_group="adx_dmi"` to document that the three series are produced by one shared calculation.

## Exact BBB semantics

The implementation preserves:

- directional movement masks based on `high.diff()` and `-low.diff()`;
- true range from high/low/previous close;
- Wilder RMA bootstrap at the first fully finite `period` window;
- recursive Wilder updates;
- DI formulas and explicit first-`period` DI nulls;
- DX and ADX calculation order;
- the BBB detail that ADX is calculated before the explicit DI warmup mask;
- completed higher-timeframe alignment onto the base grid.

Consequently, DI first becomes visible at index `period`, while ADX can first become visible at index `2*period-2` for a fully finite series.

## Range execution

The range evaluator caches one ADX/DMI group per resolved `(timeframe, period)` pair. Requesting all three series does not repeat the calculation or the Market Data Service read.

## Golden parity

Golden tests execute the immutable copied BBB module and compare ADX, DI+, and DI- for:

- base timeframe, period 3;
- base timeframe, period 14;
- completed 1h timeframe, period 3.

Values and null positions must match bar for bar.
