# Design: MDS historical read consumer v1

`StrategyRangeRequest` carries an optional `expected_market_data_hash`. When present, the MDS adapter calls `POST /v1/historical-candles`; otherwise existing runtime/indicator calls may continue to use `GET /v1/candles`. The adapter validates the strict MDS DTO and propagates `market_data_hash` unchanged. It never independently calculates a substitute hash. Both `long` and `short` entry arrays are serialized on the stable strategy response grid; a disabled side is represented by all `false`.
