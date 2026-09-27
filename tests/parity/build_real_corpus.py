"""One-off: extract the real-batch corpus (task 1.2) from Research Service
request artifacts into `tests/parity/corpus/real_*.json`.

Raw specs and candidate ids are copied verbatim (candidate_id becomes
variant_id, exactly as `run_batch.py` does). The extracted files are
committed so the parity gate never depends on the research_service checkout.

Subsets (the full audited grid is 1560 candidates x ~684k bars, far too
slow to gate every stage on):

- width-only:      lab_baseline_width_only_v2, all 35 candidates.
- untouched-only:  lab_baseline_untouched_only_v2, 22 of 300 lookbacks
                   (dense near the default 50 and at both ends).
- TP/SL-only:      lab_3d_w01_lb_ratio restricted to untouched_lookback=70
                   (width=1 fixed) -> the full 13-point TP/SL ratio axis.
- 3D grid:         widths {1,4,8} (chunks w01/w04/w08) x lookbacks
                   {70,105,140} x TP/SL ratios {2.0,3.5,5.0} = 27.

    PYTHONPATH=src:tests .venv/bin/python -m parity.build_real_corpus \
        --results /Users/mcroma/BBB_project/research_service/results
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from parity.harness import CORPUS_DIR

UNTOUCHED_LOOKBACKS = {
    1,
    2,
    3,
    5,
    10,
    20,
    30,
    40,
    49,
    50,
    51,
    60,
    70,
    80,
    90,
    100,
    120,
    140,
    160,
    200,
    250,
    300,
}
GRID_WIDTH_CHUNKS = ("lab_3d_w01_lb_ratio", "lab_3d_w04_lb_ratio", "lab_3d_w08_lb_ratio")
GRID_LOOKBACKS = {70, 105, 140}
GRID_RATIOS = {2.0, 3.5, 5.0}


def _load(results: Path, experiment: str) -> tuple[dict[str, Any], str, str]:
    path = results / experiment / "request.json"
    raw = path.read_bytes()
    relative = f"research_service/results/{experiment}/request.json"
    return json.loads(raw), relative, hashlib.sha256(raw).hexdigest()


def _variants(
    request: dict[str, Any], keep: Callable[[dict[str, Any]], bool]
) -> list[dict[str, Any]]:
    variants = []
    for candidate in request["candidates"]:
        if not keep(candidate):
            continue
        strategy = candidate["strategy"]
        assert strategy["ticker"] == "BTCUSDT.P" and strategy["base_timeframe"] == "5m"
        variants.append(
            {
                "variant_id": candidate["candidate_id"],
                "strategy": {
                    "strategy_id": strategy["strategy_id"],
                    "raw_spec": strategy["raw_spec"],
                },
            }
        )
    return variants


def _write(name: str, description: str, sources: list[dict[str, Any]], variants: list[Any]) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    document = {
        "case": name,
        "description": description,
        "provenance": {"sources": sources},
        "variants": variants,
    }
    target = CORPUS_DIR / f"{name}.json"
    target.write_text(json.dumps(document, indent=1) + "\n")
    print(target, len(variants), "variants")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()

    request, path, digest = _load(args.results, "lab_baseline_width_only_v2")
    _write(
        "real_width_only_sweep",
        "Width-only sweep: anchor_stack_width_setup min_current_width_atr 1..35 (all).",
        [{"path": path, "sha256": digest, "selection": "all candidates"}],
        _variants(request, lambda candidate: True),
    )

    request, path, digest = _load(args.results, "lab_baseline_untouched_only_v2")
    _write(
        "real_untouched_only_sweep",
        "Untouched-lookback-only sweep: untouched_anchor_setup lookback subset of 1..300.",
        [
            {
                "path": path,
                "sha256": digest,
                "selection": f"metadata.lookback in {sorted(UNTOUCHED_LOOKBACKS)}",
            }
        ],
        _variants(
            request, lambda candidate: candidate["metadata"]["lookback"] in UNTOUCHED_LOOKBACKS
        ),
    )

    request, path, digest = _load(args.results, "lab_3d_w01_lb_ratio")
    _write(
        "real_tpsl_only_sweep",
        "TP/SL-only sweep: TP/SL ratio 2.00..5.00 step 0.25 at width=1, untouched lookback=70 "
        "(one full ratio axis of the real 3D grid).",
        [{"path": path, "sha256": digest, "selection": "metadata.untouched_lookback == 70"}],
        _variants(request, lambda candidate: candidate["metadata"]["untouched_lookback"] == 70),
    )

    sources: list[dict[str, Any]] = []
    variants: list[Any] = []
    for experiment in GRID_WIDTH_CHUNKS:
        request, path, digest = _load(args.results, experiment)
        sources.append(
            {
                "path": path,
                "sha256": digest,
                "selection": f"untouched_lookback in {sorted(GRID_LOOKBACKS)} and "
                f"tp_sl_ratio in {sorted(GRID_RATIOS)}",
            }
        )
        variants += _variants(
            request,
            lambda candidate: (
                candidate["metadata"]["untouched_lookback"] in GRID_LOOKBACKS
                and float(candidate["metadata"]["tp_sl_ratio"]) in GRID_RATIOS
            ),
        )
    _write(
        "real_3d_grid_subset",
        "Combined width x untouched-lookback x TP/SL 3D grid: widths {1,4,8} x lookbacks "
        "{70,105,140} x ratios {2.0,3.5,5.0}.",
        sources,
        variants,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
