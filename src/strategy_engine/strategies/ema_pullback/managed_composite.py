"""`composite_phase_condition`: the one market fold shared by every managed
execution path (OpenSpec `composite-managed-phase-condition-v1`, design D3,
D4, D5).

Children are separable (design D3): a *market* child (any predicate, the
`adx_di_threshold` atom) depends only on the bar and the trade side; a
*trade* child (`mfe_atr`, `mfe_pct`, `bars_in_trade`) is "trade quantity >=
per-bar threshold". `fold_phase_paths` evaluates every market child once over
the whole frame -- predicates through the predicate layer, the ADX atom
through `adx_di_series`, the formula the atomic projection rule also uses --
and folds per path:

- all market `require` children, and an `at_least` made only of market
  children, into one read-only bool array;
- trade `require` children stay a list, checked per bar by the caller;
- an `at_least` with at least one trade child (trade-only or mixed) stays a
  list of terms.

The single-trade replay reads the fold at the bar index (`composite_met`);
the historical projection emits it. Neither re-implements the other.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.strategies.ema_pullback.composite_spec import (
    COMPOSITE_PHASE_CONDITION,
    CompositeChild,
    CompositePhaseCondition,
    parse_composite_phase_condition,
    phase_rule_composites,
)
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.managed import (
    SeriesCache,
    _cached_series,
    _float,
    _int,
    _mapping,
)
from strategy_engine.strategies.ema_pullback.predicates import (
    PredicateIdentity,
    StatePredicate,
    TemporalPredicate,
    evaluate_predicate,
    parse_predicate,
    resolve_predicate,
)

if TYPE_CHECKING:
    from strategy_engine.strategies.ema_pullback.contexts import ContextBundle

_MARKET_ATOM = "adx_di_threshold"


def adx_di_series(
    params: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    cache: SeriesCache,
) -> tuple[tuple[bool, ...], tuple[bool, ...]]:
    """(long, short) per-bar value of the `adx_di_threshold` atom: the same
    formula as `managed._phase_met` (missing value -> False). Shared by the
    atomic projection rule and by composite market children."""

    key = (
        str(params.get("timeframe", "")),
        _int(params.get("period"), "adx_di_threshold.period"),
    )
    columns = plan.adx_dmi_columns.get(key, {})
    adx_values = _cached_series(cache, frame, columns.get("adx", ""))
    plus_values = _cached_series(cache, frame, columns.get("di_plus", ""))
    minus_values = _cached_series(cache, frame, columns.get("di_minus", ""))
    adx_threshold = _float(
        params.get("adx_threshold"), "adx_di_threshold.adx_threshold", positive=True
    )
    require = params.get("require_di_alignment", True)
    long_series: list[bool] = []
    short_series: list[bool] = []
    for adx, plus, minus in zip(adx_values, plus_values, minus_values, strict=True):
        if adx is None or plus is None or minus is None:
            long_series.append(False)
            short_series.append(False)
            continue
        ok = adx >= adx_threshold
        long_series.append(ok and (not require or plus > minus))
        short_series.append(ok and (not require or minus > plus))
    return tuple(long_series), tuple(short_series)


def is_market_child(child: CompositeChild) -> bool:
    if child.predicate is not None:
        return True
    assert child.condition is not None
    return str(child.condition.get("component_id", "")) == _MARKET_ATOM


@dataclass(frozen=True, slots=True)
class FoldedPath:
    path_id: str
    # AND of the market `require` children (and of an all-market `at_least`);
    # None when the path has no market part.
    market: np.ndarray | None
    # Trade `require` children, in declared order.
    trade_require: tuple[str, ...]
    # Kept only when `at_least` contains a trade child (trade-only or mixed).
    at_least_k: int | None
    at_least_terms: tuple[str, ...]
    # Every child id the path references (attribution).
    referenced: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FoldedComposite:
    spec: CompositePhaseCondition
    paths: tuple[FoldedPath, ...]
    # child_id -> read-only bool array for the folded side (market children).
    market_children: Mapping[str, np.ndarray]


def _market_mask(
    child: CompositeChild,
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    *,
    bundle: ContextBundle | None,
    context: EvaluationContext | None,
    identity: PredicateIdentity | None,
    series_cache: SeriesCache,
) -> np.ndarray:
    if child.predicate is not None:
        return evaluate_predicate(
            parse_predicate(child.predicate, f"composite_phase_condition.{child.child_id}"),
            frame,
            side,
            context=context,
            identity=identity,
            bundle=bundle,
        )
    assert child.condition is not None
    params = _mapping(child.condition.get("params", {}), "phase condition params")
    if not isinstance(params.get("require_di_alignment", True), bool):
        raise InvalidRequestError("require_di_alignment must be boolean")
    long_series, short_series = adx_di_series(params, frame, plan, series_cache)
    mask = np.asarray(long_series if side == "long" else short_series, dtype=bool)
    mask.flags.writeable = False
    return mask


def fold_phase_paths(
    spec: CompositePhaseCondition,
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
    side: str,
    *,
    bundle: ContextBundle | None = None,
    context: EvaluationContext | None = None,
    identities: Mapping[str, PredicateIdentity] | None = None,
    series_cache: SeriesCache | None = None,
) -> FoldedComposite:
    """Evaluate every market child of `spec` once for `side` and fold each
    path (design D4). `identities`: predicate identities for `side` by
    child id (memoized evaluation); None evaluates directly."""

    cache: SeriesCache = {} if series_cache is None else series_cache
    length = len(frame.time_ms)
    market: dict[str, np.ndarray] = {}
    for child in spec.children:
        if is_market_child(child):
            market[child.child_id] = _market_mask(
                child,
                frame,
                plan,
                side,
                bundle=bundle,
                context=context,
                identity=identities.get(child.child_id) if identities is not None else None,
                series_cache=cache,
            )
    paths: list[FoldedPath] = []
    for composite_path in spec.paths:
        folded: np.ndarray | None = None
        for ref in composite_path.require:
            if ref in market:
                folded = market[ref].copy() if folded is None else folded & market[ref]
        at_least_k: int | None = None
        at_least_terms: tuple[str, ...] = ()
        if composite_path.at_least_k is not None:
            of = composite_path.at_least_of
            if all(ref in market for ref in of):
                counts = np.zeros(length, dtype=np.int64)
                for ref in of:
                    counts += market[ref]
                vote = counts >= composite_path.at_least_k
                folded = vote if folded is None else folded & vote
            else:
                at_least_k = composite_path.at_least_k
                at_least_terms = of
        if folded is not None:
            folded.flags.writeable = False
        paths.append(
            FoldedPath(
                path_id=composite_path.path_id,
                market=folded,
                trade_require=tuple(ref for ref in composite_path.require if ref not in market),
                at_least_k=at_least_k,
                at_least_terms=at_least_terms,
                referenced=tuple(
                    dict.fromkeys((*composite_path.require, *composite_path.at_least_of))
                ),
            )
        )
    return FoldedComposite(spec, tuple(paths), market)


TradeMet = Callable[[Mapping[str, Any]], bool]


def composite_met(
    folded: FoldedComposite, index: int, trade_met: TradeMet
) -> tuple[bool, dict[str, object]]:
    """The composite's value on bar `index` for the folded side (design D5):
    the first true path in declared order wins. `trade_met(condition)` is
    the existing atom formula for a trade child on this bar."""

    spec = folded.spec

    def value(child_id: str) -> bool:
        mask = folded.market_children.get(child_id)
        if mask is not None:
            return bool(mask[index])
        condition = spec.child(child_id).condition
        assert condition is not None
        return trade_met(condition)

    for path in folded.paths:
        if path.market is not None and not path.market[index]:
            continue
        if not all(value(ref) for ref in path.trade_require):
            continue
        if path.at_least_k is not None and (
            sum(value(ref) for ref in path.at_least_terms) < path.at_least_k
        ):
            continue
        return True, {
            "path_id": path.path_id,
            "children": {ref: value(ref) for ref in path.referenced},
        }
    return False, {}


def _needs_bundle(predicate: object) -> bool:
    if isinstance(predicate, StatePredicate):
        return True
    if isinstance(predicate, TemporalPredicate):
        return _needs_bundle(predicate.of)
    return False


def composites_need_context_bundle(raw_spec: Mapping[str, Any]) -> bool:
    """True iff some composite phase condition has a `state` predicate,
    directly or inside `temporal` (design D7)."""

    trade_management = raw_spec.get("trade_management")
    if not isinstance(trade_management, Mapping):
        return False
    exit_management = trade_management.get("exit_management")
    if not isinstance(exit_management, Mapping):
        return False
    for index, spec in phase_rule_composites(exit_management):
        for child in spec.children:
            if child.predicate is not None and _needs_bundle(
                parse_predicate(child.predicate, f"phase_rules[{index}].{child.child_id}")
            ):
                return True
    return False


def parse_if_composite(condition: Mapping[str, Any], path: str) -> CompositePhaseCondition | None:
    if str(condition.get("component_id", "")) != COMPOSITE_PHASE_CONDITION:
        return None
    return parse_composite_phase_condition(condition, path)


# -- memo (design D8) ------------------------------------------------------------

# (phase rule index, side, child_id -> predicate identity), in projection
# order: rules in declared order, `long` then `short`, children in order.
ManagedPredicateIdentities = tuple[tuple[int, str, Mapping[str, PredicateIdentity]], ...]


def _predicate_children(
    raw_spec: Mapping[str, Any],
) -> tuple[tuple[int, CompositePhaseCondition], ...]:
    trade_management = raw_spec.get("trade_management")
    if not isinstance(trade_management, Mapping):
        return ()
    exit_management = trade_management.get("exit_management")
    if not isinstance(exit_management, Mapping) or exit_management.get("mode") != "managed":
        return ()
    return tuple(
        (index, spec)
        for index, spec in phase_rule_composites(exit_management)
        if any(child.predicate is not None for child in spec.children)
    )


def has_managed_predicates(raw_spec: Mapping[str, Any]) -> bool:
    """True iff the managed projection evaluates some predicate child."""

    return bool(_predicate_children(raw_spec))


def resolve_managed_predicates(
    raw_spec: Mapping[str, Any],
    feature_ids: Mapping[str, NodeSpec],
    contexts: Mapping[str, NodeSpec] | None,
) -> ManagedPredicateIdentities:
    """The single resolution of the managed stage, used by the batch
    pre-pass and by the projection. Empty unless `mode == "managed"` and
    some composite phase condition has a predicate child."""

    out: list[tuple[int, str, Mapping[str, PredicateIdentity]]] = []
    for index, spec in _predicate_children(raw_spec):
        predicates = [
            (
                child.child_id,
                parse_predicate(child.predicate, f"phase_rules[{index}].{child.child_id}"),
            )
            for child in spec.children
            if child.predicate is not None
        ]
        for side in ("long", "short"):
            out.append(
                (
                    index,
                    side,
                    {
                        child_id: resolve_predicate(predicate, feature_ids, side, contexts)
                        for child_id, predicate in predicates
                    },
                )
            )
    return tuple(out)


def managed_predicate_consumptions(identities: ManagedPredicateIdentities) -> tuple[NodeSpec, ...]:
    """`local` plus `nested` per predicate child per side, in projection
    order."""

    consumed: list[NodeSpec] = []
    for _, _, children in identities:
        for identity in children.values():
            consumed.append(identity.local)
            consumed += identity.nested
    return tuple(consumed)
