"""One-off: fetch a real BTCUSDT.P 5m slice from a running Market Data
Service and store the exact response bytes (gzip) as the parity fixture.

The harness later serves these bytes back through the real
`MarketDataServiceClient` via an `httpx.MockTransport`, so candle parsing
(`parse_decimal_text`) and `MarketFrame` construction are production code.

    PYTHONPATH=src:tests .venv/bin/python -m parity.fetch_market_fixture
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import httpx

from parity.harness import FIXTURE_DIR, MARKET_FIXTURE

# 12,000 closed 5m bars (~41.7 days) ending on an aligned boundary. Long
# enough for EMA(500) / width lookbacks / untouched lookback 300 / 4h
# EMA(200) contexts (48 * 200 = 9,600 bars) to warm up; short enough that
# the full corpus runs in well under a minute.
FROM_MS = 1_786_800_000_000
TO_MS = 1_790_400_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mds", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    response = httpx.get(
        f"{args.mds}/v1/candles",
        params={
            "ticker": "BTCUSDT.P",
            "timeframe": "5m",
            "from_ms": FROM_MS,
            "to_ms": TO_MS,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = json.loads(response.content)
    assert payload["from_ms"] == FROM_MS and payload["to_ms"] == TO_MS
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = FIXTURE_DIR / MARKET_FIXTURE
    Path(target).write_bytes(gzip.compress(response.content, mtime=0))
    print(target, len(payload["candles"]), "bars", payload["market_data_hash"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
