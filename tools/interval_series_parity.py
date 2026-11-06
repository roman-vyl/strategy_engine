"""Frozen-research operand acceptance, not a full Engine strategy backtest.

Run: .venv/bin/python tools/interval_series_parity.py --research-root ../research_service
Uses frozen research S/P endpoints and pandas EMA seeds deliberately to isolate
operand semantics; the unit/pipeline tests separately exercise Engine episodes.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pickle
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from strategy_engine.strategies.ema_pullback.predicates import (
    _values,
    operand_features,
    parse_predicate,
)
from strategy_engine.strategies.ema_pullback.setups import exponent_weight
from strategy_engine.strategies.ema_pullback.stack_episode import SideEpisode
from strategy_engine.strategies.ema_pullback.weighted_vote_spec import Exponent


def ema(n):
    return {"feature": {"kind": "ema", "source": "close", "params": {"period": int(n)}}}


def ratio(a, b, floor=0.02):
    return {"ratio": {"left": a, "right": b, "right_floor": floor, "denominator_mode": "absolute"}}


def signed(a):
    return {"signed": {"operand": a, "center": 0}}


def scale(a, factor=1e4):
    return {"scale": {"operand": a, "factor": factor}}


def measure(series, span, operation):
    if span.startswith("L"):
        interval = {"kind": "fixed", "bars": int(span[1:])}
    else:
        interval = {
            "kind": "episode",
            "ref": "trend",
            "leg": "impulse" if span[0] == "I" else "pullback",
        }
        if len(span) > 1:
            interval["last_n"] = int(span[1:])
    return {"interval_change": {"of": series, "interval": interval, "operation": operation}}


def slope(n, span):
    return signed(scale(measure(ema(n), span, "relative_change_per_bar")))


def formula(raw):
    if raw.startswith("gap"):
        pair, span = raw.split("|")
        f, s = map(int, pair[3:].split("-"))
        gap = scale(
            {"ratio": {"left": {"difference": {"left": ema(f), "right": ema(s)}}, "right": ema(s)}}
        )

        def vel(leg):
            return signed(measure(gap, leg, "change_per_bar"))

        return ratio(vel("R"), vel("I"), 0.01) if span == "dR/dI" else vel(span[1:])
    m = re.fullmatch(r"E(\d+)(?:([-\/])E(\d+))?\|([RIL]\d*)(?:/([RIL]\d*))?", raw)
    if not m:
        return None
    n, op, n2, span, span2 = m.groups()
    a = slope(n, span)
    if span2:
        return ratio(a, slope(n, span2))
    if op:
        b = slope(n2, span)
        return ratio(a, b) if op == "/" else {"difference": {"left": a, "right": b}}
    return a


def hashfile(p):
    return hashlib.file_digest(p.open("rb"), "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/Users/mcroma/BBB_data/tmp"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("openspec/changes/archive/2026-11-06-interval-series-operands-v1/acceptance"),
    )
    args = parser.parse_args()
    r = args.research_root
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    nvs = r / "research/nvs3_shape_v1"
    cfg = json.loads((nvs / "config.json").read_text())
    selection = json.loads((nvs / "selection.json").read_text())
    with gzip.open(nvs / "calibration.json.gz") as stream:
        cal = {a["index"]: a for a in json.load(stream)}
    selected = [(a, formula(a["raw"])) for a in selection if formula(a["raw"]) is not None]
    (out / "formula_mapping.json").write_text(
        json.dumps(
            [
                dict(
                    index=a["index"],
                    raw=a["raw"],
                    operand=op,
                    entry_candle_included=True,
                    eligibility="frozen research elig; identical entries",
                    units="bp/base bar for slopes; dimensionless for ratios",
                    direction="outer signed once per slope",
                    reference="corrected_features or unchanged impulse feat",
                )
                for a, op in selected
            ],
            indent=2,
        )
    )
    configs = {
        "btc": (
            "anchors_btc_20261020/work/a200/entries_a200btc.csv.gz",
            "v3e200_20261020/work/btc.pkl",
        ),
        "eth": ("eth200_20261020/work/eth/entries_e200eth.csv.gz", "v3e200_20261020/work/eth.pkl"),
        "sol": (
            "ema200_calib_20261020/sol/work/sol/entries_e200sol.csv.gz",
            "ema200_calib_20261020/sol/work/sol.pkl",
        ),
    }
    report = {
        "scope": (
            "operand parity with frozen entry/episode endpoints and EMA seeds; "
            "frozen-weight substitution, not a full Engine backtest; SPOT/PERP excluded"
        ),
        "source_hashes": {},
        "coins": {},
    }
    engine_root = Path(__file__).resolve().parents[1]
    for f in [
        Path(__file__),
        engine_root / "src/strategy_engine/strategies/ema_pullback/predicates.py",
        engine_root
        / "src/strategy_engine/strategies/ema_pullback"
        / "live_calculation_requirements.py",
        nvs / "config.json",
        nvs / "selection.json",
        nvs / "calibration.json.gz",
        r / "results/recovered_slope2/feat2.py",
    ]:
        report["source_hashes"][str(f)] = hashfile(f)
    B, h, A, T = cfg["base"], cfg["h"], cfg["anchor"], cfg["threshold"]
    for coin, (entry_path, bundle_path) in configs.items():
        files = [
            args.data_root / entry_path,
            args.data_root / bundle_path,
            r / f"results/recovered_slope2/mds_recalculation/mds_{coin}.npz",
            r
            / "research/stage2_cross_coin_review/timing_replacement_audit"
            / f"corrected_features_{coin}.npz",
            r / f"results/recovered_slope2/mds_recalculation/feat_{coin}.npz",
            nvs / coin / "scores.npz",
        ]
        for f in files:
            report["source_hashes"][str(f)] = hashfile(f)
        df = pd.read_csv(files[0])
        bundle = pickle.load(files[1].open("rb"))
        md = np.load(files[2])
        corrected = np.load(files[3])
        old = np.load(files[4])
        scores = np.load(files[5])
        assert not df.bar.duplicated().any()
        bars = df.bar.to_numpy(int)
        size = len(md["c"])
        elig = np.asarray(bundle["elig"], bool)
        assert np.array_equal(bars, scores["entry_bar"])
        features = {}
        for n in [50, 100, 200, 500, 1000]:
            planned = operand_features(
                parse_predicate(
                    {"kind": "range", "operand": ema(n), "min": None, "max": None}, "p"
                ).long.operand
            )[0]
            features[planned.output_id] = (
                pd.Series(md["c"].astype(float)).ewm(span=n, adjust=False).mean().to_numpy()
            )
        frame = SimpleNamespace(time_ms=md["time_ms"], series=features)
        # One table row per entry; as-of state only on each matching-side entry.
        episodes = {}
        for side in ["long", "short"]:
            active = elig & (df.side.to_numpy() == side)
            number = np.full(size, np.nan)
            number[bars[active]] = 1
            eid = np.zeros(size)
            eid[bars] = np.arange(len(df))
            episodes[side] = SideEpisode(
                side,
                {"touch_number": number, "episode_id": eid},
                {},
                {},
                {},
                {"origin_bar": df.s_bar.to_numpy(), "peak_bar": df.p_bar.to_numpy()},
                np.arange(len(df)),
            )
        ctx = SimpleNamespace(
            episodes=SimpleNamespace(side=lambda ref, side, episodes=episodes: episodes[side])
        )
        records = []
        replaced = np.array(scores["E"], copy=True)
        expectedW = []
        actualW = []
        arrays = {}
        ids = [a["index"] for a in selection]
        for a, op in selected:
            pred = parse_predicate(
                {"kind": "range", "operand": op, "min": None, "max": None},
                "p",
                episode_refs=["trend"],
            )
            vals = np.full(len(df), np.nan)
            for side in ["long", "short"]:
                active = elig & (df.side.to_numpy() == side)
                allvals = _values(pred.long.operand, frame, None, None, side, ctx)
                vals[active] = allvals[bars[active]]
            ref = np.array((corrected if a["raw"] in corrected.files else old)[a["raw"]])
            fm = np.isfinite(vals)
            fr = np.isfinite(ref)
            ok = fm & fr
            delta = np.abs(vals[ok] - ref[ok])
            mismatch = (fm != fr) | (
                ok & ~np.isclose(vals, ref, rtol=1e-9, atol=1e-10, equal_nan=True)
            )
            c = cal[a["index"]]
            cy = np.asarray(c["pava"], float)
            cx = np.asarray(c["X"])
            good = np.isfinite(cy)
            e = np.where(fm, np.interp(vals, cx[good], cy[good]), -np.inf)
            k = cfg["coefficients"][str(a["index"])]
            originalE = scores["E"][ids.index(a["index"])]
            w = exponent_weight(
                np.maximum(np.minimum(e, 100 * (100 / B - 1)) - h, 0) * B / 100,
                Exponent(k, A - B * (1 + h / 100)),
            )
            refw = np.expm1(
                k * np.maximum(np.minimum(originalE, 100 * (100 / B - 1)) - h, 0) * B / 100
            ) / np.expm1(k * (A - B * (1 + h / 100)))
            replaced[ids.index(a["index"])] = e
            expectedW.append(refw)
            actualW.append(w)
            records.append(
                dict(
                    index=a["index"],
                    raw=a["raw"],
                    finite=int(fm.sum()),
                    finite_mask_mismatches=int((fm != fr).sum()),
                    max_absolute_error=float(delta.max(initial=0)),
                    max_relative_error=float(
                        (delta / np.maximum(np.abs(ref[ok]), 1e-12)).max(initial=0)
                    ),
                    offending_entries=np.flatnonzero(mismatch).tolist(),
                    weight_max_absolute_error=float(np.max(np.abs(w - refw))),
                    weight_mismatches=int((~np.isclose(w, refw, rtol=1e-8, atol=1e-9)).sum()),
                )
            )
            arrays[str(a["index"])] = vals
        ks = np.array([cfg["coefficients"][str(i)] for i in ids])[:, None]
        W = np.expm1(
            ks * np.maximum(np.minimum(replaced, 100 * (100 / B - 1)) - h, 0) * B / 100
        ) / np.expm1(ks * (A - B * (1 + h / 100)))
        groups = cfg.get("groups", cfg.get("micro"))
        total = np.array([W[[ids.index(i) for i in g]].max(0) for g in groups]).sum(0)
        result = dict(
            entries=len(df),
            eligible=int(elig.sum()),
            formulas=records,
            hybrid_substitution_score_max_error=float(np.max(np.abs(total - scores["score"]))),
            hybrid_substitution_block_mismatches=int(
                ((total >= T - 1e-9) != scores["blocked"]).sum()
            ),
        )
        report["coins"][coin] = result
        np.savez_compressed(out / f"{coin}_values.npz", entry_bar=bars, **arrays)
        (out / "parity.json").write_text(json.dumps(report, indent=2))
        print(
            coin,
            len(records),
            "formulas",
            sum(len(x["offending_entries"]) for x in records),
            "value mismatches",
            sum(x["weight_mismatches"] for x in records),
            "weight mismatches",
            result["hybrid_substitution_block_mismatches"],
            "block mismatches",
            flush=True,
        )
    assert all(
        not x["offending_entries"] and not x["weight_mismatches"]
        for v in report["coins"].values()
        for x in v["formulas"]
    )
    assert all(v["hybrid_substitution_block_mismatches"] == 0 for v in report["coins"].values())


if __name__ == "__main__":
    main()
