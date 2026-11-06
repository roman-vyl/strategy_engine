# Implementation acceptance

Implemented generic rsi_ewm, existing segment level min/max with include_start and empty_policy, history policy, catalog/readiness, identities, docs and executable C6 observation spec. No production voting configuration, reviews or deployment changed.

## Numerical acceptance

Same complete candle prefixes and frozen research episode points, original HIST:c6r reference. Both explicit raw-level long/short expressions AND the shipped side-signed two-sided composition were checked.

| Coin | Finite reference entries | Selected study entries | Maximum absolute error | Missing mismatches |
|---|---:|---:|---:|---:|
| BTC | 1928 | 228 | 8.53e-14 | 0 |
| ETH | 1680 | 208 | 7.82e-14 | 0 |
| SOL | 1461 | 122 | 7.11e-14 | 0 |

All available entries checked, not only selected plateau entries. Input and implementation hashes, seed origin timestamps, actual/reference arrays: acceptance/. Episode points are supplied by frozen research data to isolate operand parity; ordinary Engine pipeline and synthetic episode tests verify integration. This is not a full Engine-vs-research strategy replay.

## Verification

- New recursive/segment/pipeline/HTF tests passed (7 tests); combined with foundation API: 15 passed.
- Full mandatory suite initially: 2317 passed, 2 skipped, 8 failed. Seven failures were expected additive catalog / formerly rejected level-max assertions; these expectations were narrowly updated, keeping every legacy schema/value/identity assertion. Affected regression rerun: 272 passed, 2 skipped.
- Remaining live-entry byte-snapshot failure was reproduced against isolated clean HEAD source without this implementation; its baseline was not rewritten. See saved logs. Full suite is therefore NOT claimed green.
- ruff check src tests scripts: passed.
- mypy src: passed (118 source files).
- release archive verification: passed.
- OpenSpec strict validation: passed.

Use `.venv/bin/python tools/c6_parity.py --research-root ../research_service` to repeat acceptance. Exact recursive equality requires matching input seed prefixes; finite warm-up decay does not guarantee exact output parity. Existing supplied market prefix/time axis and data hash identify the source, recorded explicitly by acceptance.
