"""Independent formula checks for the two absent expressions; never production substitutes."""

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_engine.indicators.implementations.atr import atr_wilder
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    resample_ohlcv,
)
from strategy_engine.strategies.ema_pullback.forming_candle import forming_range_values

P = Path("openspec/changes/archive/2026-11-06-forming-candle-range-v1/acceptance")
P.mkdir(exist_ok=True)
R = Path("/Users/mcroma/BBB_project/research_service")

configs = {
    "btc": (
        "btc_ema200_w9-11_lb20-40_v2",
        "anchors_btc_20261020/work/a200/entries_a200btc.csv.gz",
        "v3e200_20261020/work/btc.pkl",
    ),
    "eth": (
        "eth_ema200_four_plateaus_v1",
        "eth200_20261020/work/eth/entries_e200eth.csv.gz",
        "v3e200_20261020/work/eth.pkl",
    ),
    "sol": (
        "sol_ema200_four_plateaus_v1",
        "ema200_calib_20261020/sol/work/sol/entries_e200sol.csv.gz",
        "ema200_calib_20261020/sol/work/sol.pkl",
    ),
}


def compare(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    bad = ok & ~np.isclose(a, b, rtol=1e-7, atol=1e-9)
    return dict(
        mask_mismatches=int((np.isfinite(a) != np.isfinite(b)).sum()),
        value_mismatches=int(bad.sum()),
        max_abs=float(np.abs(a[ok] - b[ok]).max(initial=0)),
    )


report = {}
for coin, (study, entry, bundle) in configs.items():
    md = dict(np.load(R / f"results/recovered_slope2/mds_recalculation/mds_{coin}.npz"))
    df = pd.read_csv(Path("/Users/mcroma/BBB_data/tmp") / entry)
    elig = np.asarray(
        pickle.load((Path("/Users/mcroma/BBB_data/tmp") / bundle).open("rb"))["elig"], bool
    )
    ref = np.load(R / f"research/stage0_plateau_medians/studies/{study}/inputs/feature_values.npz")
    bars = df.bar.to_numpy(int)
    f = pd.DataFrame(
        {
            a: md[b]
            for a, b in [
                ("open", "o"),
                ("high", "h"),
                ("low", "l"),
                ("close", "c"),
                ("volume", "v"),
            ]
        },
        index=pd.to_datetime(md["time_ms"], unit="ms", utc=True),
    )
    f4 = resample_ohlcv(f, "4h")
    a4 = atr_wilder(f4.high, f4.low, f4.close, period=14)
    a = align_completed_to_base(a4, timeframe="4h", base_index=f.index).to_numpy()
    bucket = md["time_ms"] // 14400000
    high = f.high.groupby(bucket).cummax().to_numpy()
    low = f.low.groupby(bucket).cummin().to_numpy()
    d3 = np.where(
        elig,
        forming_range_values(md["time_ms"], md["h"], md["l"], a, 14400000, 300000)[bars],
        np.nan,
    )

    report[coin] = compare(d3, ref["HIST:d3cr_4h"])
    report[coin]["source_sha256"] = hashlib.sha256(
        (R / f"results/recovered_slope2/mds_recalculation/mds_{coin}.npz").read_bytes()
    ).hexdigest()
    np.savez_compressed(P / f"{coin}.npz", actual=d3, expected=ref["HIST:d3cr_4h"])
    print(coin, report[coin], flush=True)
    assert report[coin]["mask_mismatches"] == report[coin]["value_mismatches"] == 0
(P / "parity.json").write_text(json.dumps(report, indent=2))
