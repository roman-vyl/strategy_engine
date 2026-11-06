"""Original C6 parity on frozen research points, not a new strategy backtest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from strategy_engine.indicators.implementations.rsi import rsi_recursive
from strategy_engine.strategies.ema_pullback.predicates import _values, parse_predicate
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode


def operand(side, previous=False):
    return {
        "segment": {
            "episode": "trend",
            "of": {
                "by_side": {
                    s: {"kind": "rsi_ewm", "params": {"period": 168}} for s in ["long", "short"]
                }
            },
            "from": "peak",
            "to": "next_origin" if previous else "current",
            "touch": "previous" if previous else "current",
            "value": "level",
            "aggregate": "min" if side == "long" else "max",
            "include_start": False,
            "empty_policy": "missing" if previous else "end",
        }
    }


def formula(side):
    current, previous = operand(side), operand(side, True)
    left, right = (current, previous) if side == "long" else (previous, current)
    return {"difference": {"left": left, "right": right}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, default=Path("../research_service"))
    parser.add_argument("--data-root", type=Path, default=Path("/Users/mcroma/BBB_data/tmp"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openspec/changes/recursive-rsi-episode-extrema-v1/acceptance"),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    configs = {
        "btc": (
            "btc_ema200_w9-11_lb20-40_v2",
            "anchors_btc_20261020/work/a200/entries_a200btc.csv.gz",
        ),
        "eth": ("eth_ema200_four_plateaus_v1", "eth200_20261020/work/eth/entries_e200eth.csv.gz"),
        "sol": (
            "sol_ema200_four_plateaus_v1",
            "ema200_calib_20261020/sol/work/sol/entries_e200sol.csv.gz",
        ),
    }
    report = {
        "scope": (
            "Full-prefix indicator and composed operands, frozen research episode points; "
            "synthetic/pipeline tests cover Engine episode integration"
        ),
        "coins": {},
        "hashes": {},
    }
    for coin, (study, entry) in configs.items():
        root = args.research_root / "research/stage0_plateau_medians/studies" / study
        paths = [
            args.data_root / entry,
            args.research_root / f"results/recovered_slope2/mds_recalculation/mds_{coin}.npz",
            root / "inputs/feature_values.npz",
            root / "inputs/entry_labels.npz",
        ]
        for p in paths:
            report["hashes"][str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        df = pd.read_csv(paths[0])
        md = np.load(paths[1])
        ref = np.load(paths[2])["HIST:c6r"]
        lab = np.load(paths[3])
        bars = df.bar.to_numpy(int)
        assert np.array_equal(bars, lab["entry_bar"]) and not df.bar.duplicated().any()
        size = len(md["c"])
        rsi = rsi_recursive(pd.Series(md["c"]), period=168).to_numpy()
        values = np.full(len(df), np.nan)
        for side in ["long", "short"]:
            active = df.s_bar.notna().to_numpy() & (df.side.to_numpy() == side)
            previous = df.prev_p_bar.notna().to_numpy() & df.prev_s_price.notna().to_numpy()
            number = np.full(size, np.nan)
            number[bars[active]] = np.where(previous[active], 2, 1)
            eid = np.zeros(size)
            eid[bars] = np.arange(len(df))
            touches = {
                name: np.column_stack([df[a], df[b]]).ravel()
                for name, a, b in [
                    ("origin_bar", "prev_s_bar", "s_bar"),
                    ("peak_bar", "prev_p_bar", "p_bar"),
                    ("touch_bar", "prev_t_bar", "bar"),
                ]
            }
            # First-touch row must be the current row if no previous one exists.
            first = 2 * np.arange(len(df)) + (~previous).astype(int)
            ep = SideEpisode(
                side, {"touch_number": number, "episode_id": eid}, {}, {}, {}, touches, first
            )
            ctx = SimpleNamespace(episodes=SimpleNamespace(side=lambda ref, s, ep=ep: ep))
            pred = parse_predicate(
                {"kind": "range", "operand": formula(side), "min": None, "max": None},
                "c6",
                episode_refs=["trend"],
            )
            feat = pred.features()[0]
            frame = SimpleNamespace(
                market=SimpleNamespace(base_timeframe="5m"),
                time_ms=md["time_ms"],
                series={feat.output_id: rsi},
            )
            result = _values(pred.long.operand, frame, None, None, side, ctx)
            # The shipped single two-sided manifest uses side-signed min/min.
            unified = formula("long")
            for role in ("left", "right"):
                series = unified["difference"][role]["segment"]["of"]["by_side"]["long"]
                unified["difference"][role]["segment"]["of"] = series
            up = parse_predicate(
                {"kind": "range", "operand": unified, "min": None, "max": None},
                "unified",
                episode_refs=["trend"],
            )
            actual_unified = _values(up.long.operand, frame, None, None, side, ctx)
            np.testing.assert_allclose(actual_unified, result, rtol=0, atol=1e-12)
            values[active] = result[bars[active]]
        finite = np.isfinite(values) & np.isfinite(ref)
        mismatches = np.flatnonzero(np.isfinite(values) != np.isfinite(ref))
        K = lab["K"]
        selected = K.sum(tuple(range(K.ndim - 1))) > 0
        rec = dict(
            entries=len(df),
            finite=int(finite.sum()),
            missing_mismatches=mismatches.tolist(),
            max_error=float(np.max(abs(values[finite] - ref[finite]))),
            seed_open_time_ms=int(md["time_ms"][0]),
            selected_finite=int((selected & finite).sum()),
            directions={
                s: int((finite & (df.side.to_numpy() == s)).sum()) for s in ["long", "short"]
            },
        )
        report["coins"][coin] = rec
        print(coin, rec, flush=True)
        np.savez_compressed(
            args.output / f"{coin}.npz",
            actual=values,
            expected=ref,
            entry_bar=bars,
            selected=selected,
        )
    (args.output / "parity.json").write_text(json.dumps(report, indent=2))
    assert all(
        not c["missing_mismatches"] and c["max_error"] <= 1e-9 for c in report["coins"].values()
    )


if __name__ == "__main__":
    main()
