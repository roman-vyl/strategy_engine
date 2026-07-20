# Design: EMA Indicator Vertical Slice v1

## Semantic source

The authoritative legacy behavior is the copied BBB implementation in:

`legacy_source/bbb/research/strategies/ema_pullback/features/calculations.py`

EMA is calculated as:

`close.ewm(span=period, adjust=False).mean()`

No `min_periods` warmup is applied. The first finite source sample produces the first EMA value.

For a feature timeframe different from the base timeframe, BBB:

1. resamples OHLCV with left labels and left-closed buckets;
2. computes EMA on resampled close values;
3. shifts each feature timestamp forward by one feature timeframe;
4. forward-fills only completed HTF values onto the base index.

The new engine SHALL preserve this behavior exactly.

## Module placement

```text
indicators/
  implementations/
    ema.py              # EMA formula and base/HTF alignment
  application/
    validate_plan.py    # schema-aware validation orchestration
service/
  registries.py         # concrete registered indicator definitions
  wiring.py             # composition only
```

The HTTP adapter remains unchanged except for serializing the now-supported result.

## Public plan contract

```json
{
  "output_id": "ema_close_5m_200",
  "kind": "ema",
  "timeframe": "5m",
  "source": "close",
  "parameters": {"period": 200},
  "dependencies": []
}
```

Compatibility rules:

- `source` SHALL be `open`, `high`, `low`, or `close`; BBB currently uses `close` but the semantic formula is source-generic.
- `period` SHALL be a strict integer greater than zero.
- `dependencies` SHALL be empty.
- `timeframe` MAY equal the request base timeframe or be a higher integral timeframe.
- legacy token `base` MAY be accepted as an alias for the request base timeframe by the evaluator, but public API examples use canonical textual timeframes.

## Range behavior

The engine receives a complete base MarketFrame from MDS. This slice does not silently fetch pre-range warmup. Therefore EMA state starts at the first requested bar, matching BBB when given the same bounded DataFrame. Future history-extension/caching semantics require a separate change.

## Numeric output

Internal compatibility calculation uses pandas float64 because BBB uses pandas float64. HTTP output remains normalized decimal text. Golden parity compares finite numeric values with strict tolerance and exact null placement.

## Readiness

`indicator_evaluation` becomes `ready` for the registered EMA capability. Readiness SHALL enumerate supported indicator IDs rather than imply that all indicator kinds are implemented.
