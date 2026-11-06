# Acceptance

Implemented explicit feature availability in Engine and HTTP/operand contracts;
legacy defaults preserved. Corrected B3S operand is examples/b3s-4h-close.json.

Tests passed: feature availability (6 cases), ATR, feature catalog, foundation API,
declared invariants. A boundary ATR shock test confirms the newly closed value
differs from the preceding value and equals the next row's legacy read. Prefix
before/at/after boundary agrees with full history. Ruff checks and mypy on all
118 source files passed (fresh /tmp cache; existing mypy cache caused an internal
mypy error). No full strategy replay or runtime deployment performed.

Independent five-filter audit at research_service/research/htf_close_fix_20261105_v1:
all filters 15/16/142/178/280 match Claude formulas on BTC/ETH/SOL. B3S finite
counts 2815/2534/2226, missing and value mismatches all zero, max error <=2.85e-14.
Inputs/source hashes and prefix results are in audit.json. Episodes S/P are frozen.
