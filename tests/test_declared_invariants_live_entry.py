"""Declared-invariant gate for `/live-entry` (OpenSpec
`frozen-partial-take-ladder-v1`, task 0.2).

For specs without partial takes the HTTP `/live-entry` response must be
byte-identical to the baseline recorded on the pre-change code. Protects:

- `live-entry-projection-v1` scenario "Desired entry without partial takes";
- `batch-computation-reuse` "No compute regression for specs without
  partial takes".

The `/range-batch` side (`entry_opportunities` included in the public line,
`strategy-research-execution-contract-v1` "Optional partial takes on
executable entry opportunities") is protected by
`test_declared_invariants.py`; `/managed-replay` and open-trade by
`test_declared_invariants_managed.py`.
"""

from __future__ import annotations

import json
from typing import Any

from parity.live_entry_invariants import live_entry_invariants
from parity.record_invariants import LIVE_ENTRY_BASELINE_PATH

_BASELINE: dict[str, Any] = json.loads(LIVE_ENTRY_BASELINE_PATH.read_text())


def test_live_entry_responses_unchanged() -> None:
    assert live_entry_invariants() == _BASELINE["cases"], (
        "/live-entry response bytes changed for a spec without partial takes"
    )
