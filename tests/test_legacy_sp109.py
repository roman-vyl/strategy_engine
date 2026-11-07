import numpy as np
import pytest

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.strategies.ema_pullback.legacy_sp109 import EM, archive_features
from strategy_engine.strategies.ema_pullback.predicates import parse_predicate


def fixture():
    price = np.arange(400, dtype=float) + 100
    return dict(
        cl=price,
        hi=price + 1,
        lo=price - 1,
        E={n: price.copy() for n in EM},
        g=np.array([1.0]),
        entry_bar=np.array([320]),
        S=np.array([290]),
        P=np.array([300]),
        T=np.array([315]),
        pS=np.array([260]),
        pP=np.array([270]),
        pT=np.array([280]),
        sp=np.array([390.0]),
        pp=np.array([400.0]),
        psp=np.array([360.0]),
        ppp=np.array([370.0]),
        eligible=np.array([True]),
    )


def test_archived_endpoints_and_entry_exclusion():
    args = fixture()
    f = archive_features(**args)
    assert f["E100|R"][0] == pytest.approx((419 - 400) / 400 / 19 * 1e4)
    assert f["lnRpt|dur"][0] == 10
    assert f["lnRe|dur"][0] == 19
    for a in [args["cl"], args["hi"], args["lo"], *args["E"].values()]:
        a[320:] += 10000
    other = archive_features(**args)
    for key in f:
        np.testing.assert_allclose(other[key], f[key], equal_nan=True)


def test_ineligible_entries_produce_no_vote_values():
    args = fixture()
    args["eligible"][:] = False
    assert all(np.isnan(v).all() for v in archive_features(**args).values())


def test_contract_rejects_silent_timing_change():
    op = {
        "episode": "trend",
        "metric": "E100|R",
        "timing": "inclusive_entry",
        "eligibility": "original_w24",
    }
    with pytest.raises(InvalidRequestError):
        parse_predicate(
            {"kind": "range", "operand": {"legacy_sp109_feature": op}, "min": None, "max": None},
            "test",
            episode_refs=["trend"],
        )
