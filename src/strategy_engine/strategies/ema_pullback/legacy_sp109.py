"""Frozen SP109 archive mathematics. Explicit endpoints; no inclusive-entry substitution.
The caller must supply causally evaluated episode endpoints and original eligibility.
"""

import numpy as np

from .stack_episode import SideEpisode


def safe(a: np.ndarray, b: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    return np.where(np.abs(b) > eps, a / np.where(np.abs(b) > eps, b, 1), np.nan)


EM = (50, 100, 200, 500, 1000)
XS = (6, 12, 24, 48)
WIN = (6, 12, 24, 48, 96, 288)
PAIRS = (
    (50, 200),
    (100, 200),
    (100, 500),
    (200, 500),
    (50, 500),
    (200, 1000),
    (100, 1000),
    (500, 1000),
)


def archive_features(
    *,
    cl: np.ndarray,
    hi: np.ndarray,
    lo: np.ndarray,
    E: dict[int, np.ndarray],
    g: np.ndarray,
    entry_bar: np.ndarray,
    S: np.ndarray,
    P: np.ndarray,
    T: np.ndarray,
    pS: np.ndarray,
    pP: np.ndarray,
    pT: np.ndarray,
    sp: np.ndarray,
    pp: np.ndarray,
    psp: np.ndarray,
    ppp: np.ndarray,
    eligible: np.ndarray,
) -> dict[str, np.ndarray]:
    b = np.asarray(entry_bar, dtype=np.int64) - 1
    el = np.asarray(eligible, dtype=bool) & (b >= 0)
    seg = {"I": (S, P), "R": (P, b), "Ip": (pS, pP), "Rp": (pP, pT), "W": (S, b), "Wp": (pS, pT)}
    for x in XS:
        seg[f"I{x}"] = (np.maximum(S, P - x), P)
        seg[f"R{x}"] = (np.maximum(P, b - x), b)
    for w in WIN:
        seg[f"L{w}"] = (b - w, b)

    def ok_(s0: np.ndarray, s1: np.ndarray) -> np.ndarray:
        return el & (s0 >= 0) & (s1 > s0)

    def slope(e: np.ndarray, s0: np.ndarray, s1: np.ndarray) -> np.ndarray:
        s0c, s1c = np.maximum(s0, 0), np.maximum(s1, 1)
        return np.where(
            ok_(s0, s1), g * (e[s1c] - e[s0c]) / e[s0c] / np.maximum(s1c - s0c, 1) * 1e4, np.nan
        )

    F = {}
    SL = {}
    # (1a) EMA slopes, bp per bar
    for n in EM:
        for nm, (s0, s1) in seg.items():
            SL[n, nm] = slope(E[n], s0, s1)
            F[f"E{n}|{nm}"] = SL[n, nm]
        for a_, b_ in (
            (
                ("R", "I"),
                ("I", "Ip"),
                ("R", "Rp"),
                ("W", "Wp"),
                ("L12", "L96"),
                ("L24", "L288"),
                ("L6", "L48"),
            )
            + tuple((f"R{x}", "I") for x in XS)
            + tuple((f"I{x}", "I") for x in XS)
        ):
            F[f"E{n}|{a_}/{b_}"] = safe(SL[n, a_], SL[n, b_], 0.02)
    # (1b) EMA slope vs another EMA on the same segment
    for f_, s_ in PAIRS:
        for nm in ("I", "R", "Ip", "Rp", "R12", "R24", "L24", "L96"):
            F[f"E{f_}-E{s_}|{nm}"] = SL[f_, nm] - SL[s_, nm]
            F[f"E{f_}/E{s_}|{nm}"] = safe(SL[f_, nm], SL[s_, nm], 0.02)
    # EMA gap at wave endpoints, its change per bar, and endpoint ratios.
    for f_, s_ in PAIRS:
        d = (E[f_] - E[s_]) / E[s_] * 1e4

        def lv(i: np.ndarray, gap: np.ndarray = d) -> np.ndarray:
            return np.where(el & (i >= 0), g * gap[np.maximum(i, 0)], np.nan)

        (
            F[f"gap{f_}-{s_}|@S"],
            F[f"gap{f_}-{s_}|@P"],
            F[f"gap{f_}-{s_}|@e"],
            F[f"gap{f_}-{s_}|@pP"],
        ) = lv(S), lv(P), lv(b), lv(pP)
        F[f"gap{f_}-{s_}|e/P"] = safe(lv(b), lv(P), 1)
        F[f"gap{f_}-{s_}|P/pP"] = safe(lv(P), lv(pP), 1)
        F[f"gap{f_}-{s_}|P/S"] = safe(lv(P), lv(S), 1)
        for nm in ("I", "R", "Ip", "Rp", "R12", "R24", "L24", "L96", "L288"):
            s0, s1 = seg[nm]
            s0c, s1c = np.maximum(s0, 0), np.maximum(s1, 1)
            F[f"gap{f_}-{s_}|d{nm}"] = np.where(
                ok_(s0, s1), g * (d[s1c] - d[s0c]) / np.maximum(s1c - s0c, 1), np.nan
            )
        F[f"gap{f_}-{s_}|dR/dI"] = safe(F[f"gap{f_}-{s_}|dR"], F[f"gap{f_}-{s_}|dI"], 0.01)

    # (2) S->P lines
    def line(
        p0: np.ndarray, p1: np.ndarray, s0: np.ndarray, s1: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        okk = el & (s0 >= 0) & (s1 > s0) & np.isfinite(p0) & np.isfinite(p1)
        dur = np.where(okk, s1 - s0, np.nan)
        h = np.where(okk, g * (p1 / p0 - 1) * 1e4, np.nan)
        return dur, h, safe(h, dur)

    pt = np.where(T >= 0, np.where(g > 0, lo[np.maximum(T, 0)], hi[np.maximum(T, 0)]), np.nan)
    pe = cl[b]
    ppt = np.where(pT >= 0, np.where(g > 0, lo[np.maximum(pT, 0)], hi[np.maximum(pT, 0)]), np.nan)
    LN = {
        "I": line(sp, pp, S, P),
        "Rt": line(pp, pt, P, T),
        "Re": line(pp, pe, P, b),
        "Ip": line(psp, ppp, pS, pP),
        "Rpt": line(ppp, ppt, pP, pT),
        "W": line(sp, pe, S, b),
        "Wp": line(psp, ppt, pS, pT),
        "G": line(ppp, sp, pP, S),
    }  # G = gap from previous peak to current S*
    for nm, (dur, h, k) in LN.items():
        F[f"ln{nm}|dur"], F[f"ln{nm}|h"], F[f"ln{nm}|k"] = dur, h, k
    for a_, b_ in (
        ("Re", "I"),
        ("Rt", "I"),
        ("I", "Ip"),
        ("Re", "Rpt"),
        ("Rt", "Rpt"),
        ("Rpt", "Ip"),
        ("W", "Wp"),
        ("I", "G"),
        ("Ip", "Re"),
    ):
        for j, q in enumerate(("dur", "h", "k")):
            F[f"ln{a_}/{b_}|{q}"] = safe(LN[a_][j], LN[b_][j], 1e-6)
    # angle between legs in normalised units (height in % of price vs duration in hours)
    for a_, b_ in (("Re", "I"), ("I", "Ip"), ("Rt", "Rpt")):
        F[f"ln{a_}-{b_}|kdiff"] = (
            LN[a_][2] + LN[b_][2]
            if a_.startswith("R") and not b_.startswith("R")
            else LN[a_][2] - LN[b_][2]
        )
    F["lnRe+I|h"] = LN["Re"][1] + LN["I"][1]
    F["lnRe|h/Ip h"] = safe(-LN["Re"][1], LN["Ip"][1], 1e-6)
    F["lnI|h/Ip+Rp"] = safe(LN["I"][1], LN["Ip"][1] + LN["Rpt"][1], 1e-6)
    # line slope vs EMA slope on the same leg
    for n in EM:
        F[f"lnI/E{n}|I"] = safe(LN["I"][2], SL[n, "I"], 0.02)
        F[f"lnRe/E{n}|R"] = safe(LN["Re"][2], SL[n, "R"], 0.02)
    return F


METRICS = (
    "E100-E1000|R24",
    "E100-E200|L96",
    "E100-E200|R24",
    "E100-E200|Rp",
    "E100-E500|I",
    "E100-E500|R12",
    "E100-E500|Rp",
    "E100/E1000|R12",
    "E100/E200|Ip",
    "E100/E200|Rp",
    "E100/E500|Ip",
    "E100/E500|L24",
    "E100/E500|Rp",
    "E1000|I",
    "E1000|I24/I",
    "E1000|I48/I",
    "E1000|I6/I",
    "E1000|L6/L48",
    "E1000|R24/I",
    "E1000|W",
    "E1000|W/Wp",
    "E100|I48/I",
    "E100|Ip",
    "E100|L6",
    "E100|R12/I",
    "E100|R24",
    "E100|R24/I",
    "E100|R6/I",
    "E200-E500|Ip",
    "E200-E500|R12",
    "E200-E500|R24",
    "E200/E1000|R12",
    "E200/E1000|R24",
    "E200/E500|Ip",
    "E200/E500|R12",
    "E200|I/Ip",
    "E200|I24",
    "E200|Ip",
    "E200|L12/L96",
    "E200|R12/I",
    "E200|R6/I",
    "E200|Rp",
    "E200|W/Wp",
    "E50-E200|R12",
    "E50-E200|R24",
    "E50-E200|Rp",
    "E50/E200|R12",
    "E50/E200|Rp",
    "E50/E500|L24",
    "E50/E500|R24",
    "E500-E1000|R",
    "E500/E1000|R",
    "E500/E1000|R12",
    "E500|I/Ip",
    "E500|I24/I",
    "E500|I48/I",
    "E500|I6/I",
    "E500|L12/L96",
    "E500|R12/I",
    "E500|W/Wp",
    "E500|Wp",
    "E50|I24/I",
    "E50|I48",
    "E50|I48/I",
    "E50|I6",
    "E50|L12",
    "E50|L12/L96",
    "E50|L24/L288",
    "E50|L48",
    "E50|L96",
    "E50|R24/I",
    "E50|R48/I",
    "E50|R6",
    "E50|R6/I",
    "gap100-1000|P/S",
    "gap100-1000|dRp",
    "gap100-500|dR/dI",
    "gap200-1000|P/S",
    "gap200-1000|dL288",
    "gap200-1000|dR/dI",
    "gap200-500|dL288",
    "gap200-500|dR/dI",
    "gap50-200|@pP",
    "gap50-200|P/S",
    "gap50-200|dL96",
    "gap50-200|dR",
    "gap50-500|dL24",
    "gap50-500|dRp",
    "gap500-1000|@pP",
    "gap500-1000|P/pP",
    "gap500-1000|dL24",
    "gap500-1000|dL288",
    "gap500-1000|dL96",
    "gap500-1000|e/P",
    "lnI/E1000|I",
    "lnIp/Re|dur",
    "lnIp/Re|k",
    "lnI|dur",
    "lnRe-I|kdiff",
    "lnRe/E50|R",
    "lnRe/I|dur",
    "lnRe/I|h",
    "lnRe/Rpt|dur",
    "lnRe/Rpt|h",
    "lnRe|h",
    "lnRpt/Ip|h",
    "lnRt/I|h",
    "lnRt|dur",
    "lnRt|k",
)


def runtime_features(
    episode: SideEpisode, close: np.ndarray, high: np.ndarray, low: np.ndarray
) -> dict[str, np.ndarray]:
    """Batch-scoped archive values; endpoints come from the current Engine episode.
    Chunked temporary arrays bound memory. No archived entry lookup is used.
    """
    import pandas as pd

    size = len(close)
    emas = {n: pd.Series(close).ewm(span=n, adjust=False).mean().to_numpy() for n in EM}
    count = episode.state["touch_number"]
    eid = episode.state["episode_id"]
    valid = np.isfinite(count) & np.isfinite(eid) & (count >= 1)
    first = episode.first_row[
        np.clip(np.nan_to_num(eid).astype(int), 0, len(episode.first_row) - 1)
    ]
    rows = first + np.nan_to_num(count).astype(int) - 1
    valid &= (rows >= 0) & (rows < len(episode.touches["origin_bar"]))
    ids = np.flatnonzero(valid & (np.arange(size) > 0))
    result = {k: np.full(size, np.nan) for k in METRICS}
    for off in range(0, len(ids), 4096):
        ix = ids[off : off + 4096]
        rr = rows[ix]
        prev = count[ix] >= 2

        def take(
            key: str,
            previous: bool = False,
            price: bool = False,
            *,
            rows_in_chunk: np.ndarray = rr,
            has_previous: np.ndarray = prev,
        ) -> np.ndarray:
            vv = episode.touches[key][np.maximum(rows_in_chunk - int(previous), 0)]
            vv = np.where(has_previous, vv, np.nan) if previous else vv
            return vv if price else np.where(np.isfinite(vv), vv, -1).astype(int)

        vals = archive_features(
            cl=close,
            hi=high,
            lo=low,
            E=emas,
            g=np.full(len(ix), 1.0 if episode.side == "long" else -1.0),
            entry_bar=ix,
            S=take("origin_bar"),
            P=take("peak_bar"),
            T=take("touch_bar"),
            pS=take("origin_bar", True),
            pP=take("peak_bar", True),
            pT=take("touch_bar", True),
            sp=take("origin_price", price=True),
            pp=take("peak_price", price=True),
            psp=take("origin_price", True, True),
            ppp=take("peak_price", True, True),
            eligible=np.isfinite(take("origin_price", price=True)),
        )
        for k in METRICS:
            result[k][ix] = vals[k]
    return result
