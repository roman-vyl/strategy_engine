"""Record the declared-invariant baseline (OpenSpec
`composite-setup-pre-entry-predicates-v1`, task 0.1).

Run once on the pre-change code, from `tests/`:

    python -m parity.record_invariants

Writes `parity/golden/declared_invariants.json`; `python -m
parity.record_invariants managed` writes only
`parity/golden/declared_invariants_managed.json` (OpenSpec
`composite-managed-phase-condition-v1`, task 0.1). Re-record only when a
change *intends* to alter one of the invariants listed in
`parity/invariants.py`, and say so in that change.
"""

from __future__ import annotations

import json
import sys

from parity.corpus import all_cases
from parity.harness import GOLDEN_DIR
from parity.invariants import case_invariants, indicator_contract_invariants
from parity.managed_invariants import managed_case_invariants, managed_cases

BASELINE_PATH = GOLDEN_DIR / "declared_invariants.json"
MANAGED_BASELINE_PATH = GOLDEN_DIR / "declared_invariants_managed.json"


def build() -> dict[str, object]:
    return {
        "cases": {case.name: case_invariants(case) for case in all_cases()},
        "indicator_contract": indicator_contract_invariants(),
    }


def build_managed() -> dict[str, object]:
    return {"cases": {case.name: managed_case_invariants(case) for case in managed_cases()}}


def main() -> None:
    if sys.argv[1:] == ["managed"]:
        MANAGED_BASELINE_PATH.write_text(
            json.dumps(build_managed(), indent=1, sort_keys=True) + "\n"
        )
        return
    BASELINE_PATH.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
