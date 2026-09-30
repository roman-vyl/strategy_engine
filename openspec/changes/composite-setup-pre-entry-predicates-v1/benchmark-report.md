# Cost verification (Group 6)

Owner constraint: computation cost of existing specs must not grow.
This report records what was measured for tasks 6.1–6.4, where, and
what was not measured.

## Environment and workload

- Cloud container, x86_64, 4 vCPU, Python 3.12, repo `.venv`. Other
  processes share the host, so wall and CPU times carry several
  percent of noise between runs.
- Market data: the parity fixture BTCUSDT.P 5m, 12,000 bars, replayed
  in-process through the fixture MDS transport. No live MDS and no
  full-history range were available in this environment.
- Evaluator: production `build_services` wiring, `/range-batch` route
  drained in-process, memo at its production default (ON).
- Baseline: `main` at `058ac90`, the base of this change, in a
  separate worktree. Candidate: branch HEAD `1625d09` plus the group 6
  test (no production change after `1625d09`).
- Timing: per process, the batch is run 5 times and the minimum is
  kept. Baseline and candidate processes alternate, 10 pairs.

The `batch-computation-reuse` benchmark used real Research Service
sweep requests (`lab_3d_w0*_lb_ratio`) over full MDS history on the
owner's machine. That workload is not available here. The grid below
has the same shape (width × untouched lookback × TP multiplier) on
the fixture range. A full-history A/B on the owner's machine is still
open, if wanted.

## 6.1 Owner example end to end

`tests/test_ema_pullback_composite_e2e.py` runs the two-path example
from design D1 through `/range-batch` next to the same width setups as
plain top-level setups:

- `developed`: width8, `held_for 36` of 1h state aligned, ADX 1h ≥ 25,
  RSI 5m < 70 (short: > 30);
- `alternate`: width10 and at least 2 of ADX 1h ≥ 20, ADX 5m ≥ 25,
  RSI 5m in [40, 65].

For both sides it checks every child mask, both path masks, the local
and final masks, `winning_path`, `setups_ok` and
`pre_trigger_allowed` against a naive per-bar reference. The semantic
children are compared to the plain setups from the same batch. Both
paths are True on some bars of the fixture, and
`unforeseen_consumptions` is 0.

## 6.2 Existing specs: baseline vs change

Workload: 27 candidates, 3 widths × 3 untouched lookbacks × 3 TP
multipliers, no `composite_setup`.

| Measure | main `058ac90` | change | Difference |
|---|---|---|---|
| NDJSON output (sha256 of all lines) | `f614cb0f…` | `f614cb0f…` | identical |
| Memoized node computations per family | see below | same | identical |
| Python function calls (cProfile, 1 run, including imports) | 30,550,820 | 30,561,891 | +11,071 (+0.036%) |
| CPU per batch, median of 10 pairs | 2.470 s | 2.502 s | +1.3% |
| CPU per batch, paired differences | | | −0.065 … +0.235 s |

Per-family compute counts are equal on both sides, for example
`indicator.ema` 3, `indicator.atr` 1, `indicator.atr_distance` 4,
`setup.untouched_anchor_setup` 6, `setup.anchor_stack_width_setup` 3,
`mask.all` 57. The declared-invariant gate
(`tests/test_declared_invariants.py`) pins the same for the whole
parity corpus: public output, `plan_hash`, labels, node identities and
compute counts.

Reading:

- Per-bar work is unchanged. Every function whose call count differs
  runs once per spec item, not once per bar:
  - feature-kind contract lookups in labels and `resolve_feature`;
  - the `composite_setup` scan in static validation and planning;
  - the new module's class definitions at import.
- The timing difference is within noise. The paired differences
  change sign, and a spread of ±0.2 s per batch between identical
  runs is normal on this host.
- The deterministic cost the change adds to an existing spec is about
  11 thousand calls out of 30.5 million, all of them spec-level.

## 6.3 Composite overhead

Workload: one candidate. The plain width setup vs the same setup as
the only child of a `composite_setup` with one path.

| Measure | plain | single-child composite |
|---|---|---|
| Feature computations (`indicator.*`) | ema 3, atr 1, atr_distance 2 | identical |
| Setup computations | width prefix 1, width 1 | same, plus `setup.composite_setup` 1 |
| Python function calls | 12,713,275 | 12,723,090 (+9,815, +0.08%) |
| `_composite_core` own time, excluding the child | | ≈ 1 ms |
| `_composite_trace` | | ≈ 1 ms for both sides |
| CPU per batch, median of 10 pairs | 0.245 s | 0.266 s |

- The composite adds no feature or child computation. The child keeps
  its own identity and is shared with any plain use of the same
  setup.
- Its own cost is the vectorized mask arithmetic and the trace
  conversion, about 2 ms per composite for 12,000 bars.
- The side-free composite (a side-free child) is computed once for
  both sides.
- The wall-clock gap between the medians is noise. The paired
  differences again change sign, and functions with identical call
  counts account for the variance.

## 6.4 Checks

- `pytest --ignore=tests/parity`: 617 tests pass. This includes:
  - the declared-invariant gate;
  - the predicate, state/temporal, composite and e2e tests;
  - memo on/off bit-exact checks with zero `unforeseen_consumptions`.
- `ruff check`: clean on every changed file. The only findings in
  `src` are in `historical_managed_projection.py` and existed on `main`
  before this change.
- `mypy src`: 9 errors, all in `historical_managed_projection.py`,
  also pre-existing on `main`.
- Formatting is not enforced by the repo.
- `openspec validate composite-setup-pre-entry-predicates-v1 --strict`
  passes.

## Not measured

- A full-history, real-sweep A/B on the owner's machine (the
  `batch-computation-reuse` 6.2 workload).
- The old `tests/parity` golden suite. It is not run for this change;
  its removal is tracked in strategy_engine issue #18.
