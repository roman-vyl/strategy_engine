# Cost verification (Group 6)

Owner constraint: computation cost must not grow, and CPU time of
existing specs must not increase. This report records what was measured
for task 6.3, where, and what was not measured.

## Environment and workload

- Cloud container, x86_64, 4 vCPU, Python 3.12, repo `.venv`. Other
  processes share the host, so CPU times carry a few percent of noise
  between runs.
- Market data: the parity fixture BTCUSDT.P 5m, 12,000 bars, served
  in-process through the fixture MDS transport. No live MDS and no
  full-history range were available here.
- Baseline: `main` at `7b088ae`, the base of this change, in a separate
  worktree. Candidate: branch HEAD `2aa3959` plus the group 6 tests (no
  production change after `2aa3959`).
- Script: `bench_managed.py` (scratch, not committed). Baseline and
  candidate processes alternate, 10 pairs. Each process keeps the
  minimum of 5 runs.

## Existing managed specs: baseline vs change

Workload:
- `/range-batch`: 18 candidates with atomic phase rules only (all four
  atoms, stop, take and runtime rules; `adx_di_threshold` on 1h and
  base × 3 ADX thresholds × 3 `mfe_atr` thresholds), production wiring,
  memo ON.
- `/managed-replay`: 12 calls (6 entries × 2 sides) of one of those
  specs.

| Measure | main `7b088ae` | change | Difference |
|---|---|---|---|
| NDJSON output, sha256 of all lines | `1543f66a…` | `1543f66a…` | identical |
| Memoized compute counts per node family | 22 families | same | identical |
| `/managed-replay` responses, sha256 | `86b26d80…` | `86b26d80…` | identical |
| Python calls per batch (cProfile) | 25,840,426 | 25,845,070 | +4,644 (+0.018%) |
| Python calls per 12 replays (cProfile) | 38,687,676 | 38,696,901 | +9,225 (+0.024%) |
| Batch CPU, median of 10 pairs | 2.616 s | 2.576 s | −1.5% |
| Batch CPU, paired differences | | | −0.27 … +0.18 s, 4 of 10 slower |
| 12 replays CPU, median of 10 pairs | 5.738 s | 5.778 s | +0.7% |
| 12 replays CPU, paired differences | | | −0.79 … +0.45 s, 8 of 10 slower |

Per-family compute counts are equal, for example `indicator.adx` 2,
`indicator.atr_distance` 2, `exit.select_float` 4, `mask.all` 9. The
managed declared-invariant gate
(`tests/test_declared_invariants_managed.py`) pins the same quantities,
plus `plan_hash`, labels, node identities and live open-trade results,
on every `make verify`.

Reading:

- Every added call happens once per spec or per call, not per bar:
  - batch: the composite scan in static validation, planning and the
    memo pre-pass (`phase_rule_composites`, `has_managed_predicates`);
  - replay: `_fold_composite_rules` and `composites_need_context_bundle`,
    13 calls each for 13 requests (12 measured plus warm-up), and the
    `composite_spec` scan in validation and planning.
- In the replay loop, an atomic rule now pays one dict lookup per bar
  (`folds.get(rule_index)`) before the unchanged `_phase_met` call. It
  does not show in the call counts.
- The CPU differences are within noise. Paired differences change sign
  in both workloads. The replay median +0.7% is 40 ms on 5.7 s, and a
  spread of ±0.8 s between identical runs is normal on this host. The
  deterministic call counts (+0.02%) are the reliable signal.

## Composite overhead (change only)

Same fixture, direct calls. Projection build is timed on the native
frame (the batch path) without memo; replay is `/managed-replay` end to
end (feature planning, indicator evaluation and the replay loop).

| Spec | Projection build | Conditions / distances in `phase` rules | Paths | Projection bytes | Replay per call |
|---|---|---|---|---|---|
| atomic: `adx_di_threshold` 1h + `mfe_atr` (two rules) | 3.9 ms | 1 / 1 | – | 393,854 | 415 ms |
| owner case: `(ADX 5m > 35 OR (ADX 1h > 25 AND DI 1h)) AND mfe_atr` | 6.5 ms | 2 / 1 | 2 | 557,277 | 515 ms |
| mixed `at_least`: DI 1h AND 2 of [ADX 5m, `mfe_pct`, `bars_in_trade`] | 6.1 ms | 2 / 2 | 1 | 464,147 | 432 ms |
| trade-only `at_least 2 of [bars_in_trade, mfe_pct, mfe_atr]` | 3.8 ms | 0 / 3 | 1 | 376,494 | 294 ms |

`fold_phase_paths` alone, one side, per call:

| Spec | Native frame (projection) | Boxed frame (`/managed-replay`, live) |
|---|---|---|
| owner case | 3.0 ms | 11.2 ms |
| mixed `at_least` | 2.2 ms | 8.5 ms |
| `state` + `temporal` + atom | 4.1 ms | 12.1 ms |
| trade-only `at_least` | < 0.1 ms | < 0.1 ms |

Reading:

- Per candidate, the composite projection costs a few milliseconds:
  predicate masks plus one vectorized fold per side. In a batch, the
  predicate masks are memoized and shared across candidates and with
  `composite_setup`, so the owner case's masks are computed once per
  batch (test `test_batch_differing_only_in_mfe_computes_each_predicate_once`).
- Per replay call, the fold is about 11 ms of the 515 ms. Most of the
  +100 ms over the atomic spec comes from the extra indicator columns
  the owner case plans (ADX/DI on 5m) and from the per-bar check of two
  paths. Neither is a cost that existing specs pay.
- Projection size grows by one condition series per path (2 × 12,000
  bools, about 160 KB of JSON here: the owner case has one more
  condition series than the atomic pair and is 163 KB larger), plus one per market term of an
  `at_least` with a trade child. A trade child adds one distance series,
  shared by every path that uses it. A trade-only path adds no
  condition series.

## Not measured

- A full-history A/B on the owner's machine with real Research Service
  sweeps. The fixture workload has the same shape; the full-history run
  is still open if wanted.
- Memo ON vs OFF CPU for composite batches. Equality of outputs is
  tested (`test_memo_on_and_off_give_identical_projections`); only the
  compute counts were measured for memo.
