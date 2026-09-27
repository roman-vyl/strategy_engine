"""Registered multi-indicator range evaluator."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import TYPE_CHECKING

import pandas as pd

from strategy_engine.domain.errors import EvaluationInvariantError, InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.domain.validity import Validity
from strategy_engine.indicators.contracts import (
    FeatureFrame,
    IndicatorPlan,
    NativeFeatureFrame,
    PlannedFeature,
)
from strategy_engine.indicators.implementations.adx_dmi import (
    compute_adx_dmi,
    validate_adx_dmi_feature,
)
from strategy_engine.indicators.implementations.atr import (
    atr_rolling_mean,
    validate_atr_feature,
)
from strategy_engine.indicators.implementations.atr_distance import (
    validate_atr_distance_feature,
)
from strategy_engine.indicators.implementations.ema import validate_ema_feature
from strategy_engine.indicators.implementations.frame_ops import (
    align_completed_to_base,
    feature_timeframe,
    resample_ohlcv,
    serialize_value,
)
from strategy_engine.indicators.implementations.rsi import (
    rsi_rolling_mean,
    validate_rsi_feature,
)
from strategy_engine.indicators.market_arrays import MarketArrays

if TYPE_CHECKING:
    from strategy_engine.indicators.evaluation_context import EvaluationContext


def _validate_feature_timeframe(
    feature: PlannedFeature,
    *,
    base_timeframe: str,
) -> str:
    timeframe = feature_timeframe(feature.timeframe, base_timeframe)
    base_step_ms = timeframe_duration_ms(base_timeframe)
    feature_step_ms = timeframe_duration_ms(timeframe)
    if feature_step_ms < base_step_ms or feature_step_ms % base_step_ms:
        raise InvalidRequestError(
            "indicator timeframe must be base or an integral higher timeframe",
            output_id=feature.output_id,
            base_timeframe=base_timeframe,
            feature_timeframe=timeframe,
        )
    return timeframe


def _feature_period(feature: PlannedFeature) -> int:
    """Effective period of an already-validated period-parameterized feature
    (shared by compute and `resolve_feature`)."""

    return int(feature.parameters["period"])


def _atr_distance_multiplier(feature: PlannedFeature) -> float:
    """Effective multiplier of an already-validated atr_distance feature
    (shared by compute and `resolve_feature`)."""

    return float(feature.parameters["multiplier"])


def _ema_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_ema_feature(feature)
    assert feature.source is not None
    return (
        frame[feature.source]
        .astype(float)
        .ewm(
            span=_feature_period(feature),
            adjust=False,
        )
        .mean()
    )


def _rsi_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_rsi_feature(feature)
    return rsi_rolling_mean(
        frame["close"].astype(float),
        period=_feature_period(feature),
    )


def _atr_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_atr_feature(feature)
    return atr_rolling_mean(
        frame["high"].astype(float),
        frame["low"].astype(float),
        frame["close"].astype(float),
        period=_feature_period(feature),
    )


def _atr_distance_values(
    dependency_values: tuple[float | None, ...], multiplier: float
) -> tuple[float | None, ...]:
    return tuple(
        None if value is None else float(value) * multiplier for value in dependency_values
    )


def _compute_feature(
    feature: PlannedFeature,
    *,
    timeframe: str,
    feature_frame: pd.DataFrame,
    base_timeframe: str,
    base_index: pd.Index,
    market_frame: MarketFrame,
    series: Mapping[str, tuple[float | None, ...]],
    validity: Mapping[str, Validity],
    adx_dmi_cache: dict[tuple[str, int], dict[str, pd.Series]],
) -> tuple[tuple[float | None, ...], Validity]:
    """One planned feature's (values, validity) -- the per-feature body of
    `RangeIndicatorEvaluator.evaluate_native`, unchanged, as one callable
    unit so it can be memoized by identity (batch-computation-reuse group
    4). Reads earlier features only through `series`/`validity` (for
    `atr_distance`'s dependency); both results are immutable."""

    if feature.kind == "ema":
        values = _ema_values(feature_frame, feature)
    elif feature.kind == "atr":
        values = _atr_values(feature_frame, feature)
    elif feature.kind == "atr_distance":
        validate_atr_distance_feature(feature)
        dependency_id = feature.dependencies[0]
        dependency_values = series.get(dependency_id)
        if dependency_values is None:
            raise InvalidRequestError(
                "atr_distance dependency has not been evaluated",
                output_id=feature.output_id,
                dependency=dependency_id,
            )
        multiplier = _atr_distance_multiplier(feature)
        output = _atr_distance_values(dependency_values, multiplier)
        dependency_validity = validity[dependency_id]
        return output, Validity(
            valid_from_ms=dependency_validity.valid_from_ms,
            warmup_bars=dependency_validity.warmup_bars,
            complete=dependency_validity.complete,
            reason=dependency_validity.reason,
        )
    elif feature.kind == "rsi":
        values = _rsi_values(feature_frame, feature)
    elif feature.kind in {"adx", "di_plus", "di_minus"}:
        validate_adx_dmi_feature(feature)
        period = _feature_period(feature)
        key = (timeframe, period)
        group = adx_dmi_cache.get(key)
        if group is None:
            adx, di_plus, di_minus = compute_adx_dmi(
                feature_frame["high"].astype(float),
                feature_frame["low"].astype(float),
                feature_frame["close"].astype(float),
                period=period,
            )
            group = {"adx": adx, "di_plus": di_plus, "di_minus": di_minus}
            adx_dmi_cache[key] = group
        values = group[feature.kind]
    else:
        raise InvalidRequestError(
            "range evaluator received unsupported indicator kind",
            output_id=feature.output_id,
            kind=feature.kind,
        )

    if timeframe != base_timeframe:
        values = align_completed_to_base(
            values,
            timeframe=timeframe,
            base_index=base_index,
        )

    output = tuple(None if pd.isna(value) else float(value) for value in values.to_numpy())
    first_valid_index = next(
        (index for index, value in enumerate(output) if value is not None),
        None,
    )
    return output, Validity(
        valid_from_ms=(
            market_frame.bars[first_valid_index].open_time_ms
            if first_valid_index is not None
            else None
        ),
        warmup_bars=first_valid_index or 0,
        complete=first_valid_index is not None,
        reason=(None if first_valid_index is not None else "no_completed_feature_value"),
    )


# -- semantic node identity (batch-computation-reuse group 3) -----------------
#
# `resolve_feature` is the identity twin of one loop iteration of
# `RangeIndicatorEvaluator.evaluate_native`: it runs the same validators and
# the same normalization (`_validate_feature_timeframe` resolves "base" to
# the market base timeframe; `_feature_period`/`_atr_distance_multiplier`)
# and never reads `output_id` except to look up the dependency it names.
# Group 4 consumes them: `evaluate_native` memoizes each feature by this
# identity when given an `EvaluationContext`.

INDICATOR_NODE_VERSION = 1


def resolve_feature(
    feature: PlannedFeature,
    *,
    base_timeframe: str,
    upstream: Mapping[str, NodeSpec],
) -> NodeSpec:
    """Identity of one planned indicator feature.

    `upstream` maps already-resolved plan `output_id`s to identities -- the
    same lookup `evaluate_native` does against its `series` dict -- and is
    only consulted for `atr_distance`'s single dependency. Invalid features
    fail closed with the same validator error `evaluate_native` raises.
    """

    timeframe = _validate_feature_timeframe(feature, base_timeframe=base_timeframe)
    if feature.kind == "ema":
        validate_ema_feature(feature)
    elif feature.kind == "atr":
        validate_atr_feature(feature)
    elif feature.kind == "rsi":
        validate_rsi_feature(feature)
    elif feature.kind in {"adx", "di_plus", "di_minus"}:
        validate_adx_dmi_feature(feature)
    elif feature.kind == "atr_distance":
        validate_atr_distance_feature(feature)
        dependency_id = feature.dependencies[0]
        dependency = upstream.get(dependency_id)
        if dependency is None:
            raise InvalidRequestError(
                "atr_distance dependency has not been evaluated",
                output_id=feature.output_id,
                dependency=dependency_id,
            )
        return node_spec(
            "indicator.atr_distance",
            version=INDICATOR_NODE_VERSION,
            params={
                "timeframe": timeframe,
                "multiplier": _atr_distance_multiplier(feature),
            },
            upstream={"atr": dependency},
        )
    else:
        raise InvalidRequestError(
            "range evaluator received unsupported indicator kind",
            output_id=feature.output_id,
            kind=feature.kind,
        )
    return node_spec(
        f"indicator.{feature.kind}",
        version=INDICATOR_NODE_VERSION,
        params={
            "timeframe": timeframe,
            "source": feature.source,
            "period": _feature_period(feature),
        },
    )


def resolve_indicator_plan(plan: IndicatorPlan, *, base_timeframe: str) -> dict[str, NodeSpec]:
    """`output_id -> identity of the series evaluate_native stores under it`.

    Walks the plan in the same order `evaluate_native` does (so a
    dependency must precede its dependent, exactly as there). The key is the
    plan's column label; the value is the identity of the computation that
    actually fills that column.
    """

    resolved: dict[str, NodeSpec] = {}
    for feature in plan.features:
        resolved[feature.output_id] = resolve_feature(
            feature, base_timeframe=base_timeframe, upstream=resolved
        )
    return resolved


def resolve_indicator_consumptions(
    plan: IndicatorPlan, *, base_timeframe: str
) -> tuple[NodeSpec, ...]:
    """The identities `evaluate_native` will consume for `plan`, in order
    (one entry per plan feature, so a timeframe-aliased duplicate counts
    twice) -- the batch refcount pre-pass (batch-computation-reuse group 4,
    design.md D5). Stops at the first feature whose identity cannot be
    resolved, exactly where `evaluate_native` would raise; never raises."""

    resolved: dict[str, NodeSpec] = {}
    consumed: list[NodeSpec] = []
    for feature in plan.features:
        try:
            identity = resolve_feature(feature, base_timeframe=base_timeframe, upstream=resolved)
        except Exception:
            break
        resolved[feature.output_id] = identity
        consumed.append(identity)
    return tuple(consumed)


class RangeIndicatorEvaluator:
    """Evaluate registered indicator features over one complete market range.

    `evaluate_native` is the single source of indicator computation
    semantics -- `evaluate` (the public, wire-facing contract) is a thin
    boxing wrapper over it, not a second implementation
    (`compact-strategy-evaluation-boundary-v1`, "shared native
    computation, no duplicated formulas"). Internal callers that only
    need numeric values (strategy evaluation) use `evaluate_native`
    directly and never pay the `Decimal`/normalized-text boxing cost;
    the public `/indicator-evaluations/range` contract and its
    `ema-indicator-vertical-slice-v1`-family serialization semantics are
    unchanged.
    """

    def evaluate_native(
        self,
        market_frame: MarketFrame,
        plan: IndicatorPlan,
        *,
        market_arrays: MarketArrays | None = None,
        context: EvaluationContext | None = None,
    ) -> NativeFeatureFrame:
        """`market_arrays`, when given, is the caller's shared float64 view
        of this exact `market_frame` (batch-computation-reuse group 2);
        otherwise it is derived here, once, for this evaluation. Either way
        the returned frame carries it so downstream strategy nodes read
        prices from it instead of re-converting `market_bars`.

        `context`, when given, is the range-batch `EvaluationContext` for
        this exact `market_frame` (group 4): every feature is then resolved
        to its `NodeSpec` identity and computed through the context's memo.
        Absent, every feature is computed directly, as before."""

        if context is not None:
            if not context.is_for(market_frame):
                raise EvaluationInvariantError(
                    "evaluation context was not built for the evaluated market frame"
                )
            if market_arrays is None:
                market_arrays = context.market_arrays
            elif market_arrays is not context.market_arrays:
                raise EvaluationInvariantError(
                    "shared market arrays are not the evaluation context's arrays"
                )
        if market_arrays is None:
            market_arrays = MarketArrays.from_market_frame(market_frame)
        elif not market_arrays.is_derived_from(market_frame):
            raise EvaluationInvariantError(
                "shared market arrays were not derived from the evaluated market frame"
            )
        base_timeframe = market_frame.market.base_timeframe
        frame = market_arrays.dataframe()
        cached_frames: dict[str, pd.DataFrame] = {base_timeframe: frame, "base": frame}
        series: dict[str, tuple[float | None, ...]] = {}
        validity: dict[str, Validity] = {}
        adx_dmi_cache: dict[tuple[str, int], dict[str, pd.Series]] = {}
        # Identity of the series stored under each plan column so far (only
        # tracked when an evaluation context is given; mirrors `series`).
        identities: dict[str, NodeSpec] = {}

        for feature in plan.features:
            timeframe = _validate_feature_timeframe(
                feature,
                base_timeframe=base_timeframe,
            )
            feature_frame = cached_frames.get(timeframe)
            if feature_frame is None:
                feature_frame = resample_ohlcv(frame, timeframe)
                cached_frames[timeframe] = feature_frame

            compute = functools.partial(
                _compute_feature,
                feature,
                timeframe=timeframe,
                feature_frame=feature_frame,
                base_timeframe=base_timeframe,
                base_index=frame.index,
                market_frame=market_frame,
                series=series,
                validity=validity,
                adx_dmi_cache=adx_dmi_cache,
            )

            if context is None:
                output, feature_validity = compute()
            else:
                # batch-computation-reuse group 4 (D1): resolve this
                # feature's identity at the exact point it is computed today
                # (after the same timeframe validation and resample), then
                # compute through the context's memo. `resolve_feature` runs
                # the same validators / dependency check, in the same order,
                # that `_compute_feature` runs before any computation, so a
                # failure is raised at the same point with the same payload.
                identity = resolve_feature(
                    feature, base_timeframe=base_timeframe, upstream=identities
                )
                output, feature_validity = context.memoized(identity, compute)
                identities[feature.output_id] = identity
            series[feature.output_id] = output
            validity[feature.output_id] = feature_validity

        return NativeFeatureFrame(
            market=market_frame.market,
            requested_range=market_frame.requested_range,
            time_ms=market_arrays.time_ms,
            series=series,
            validity=validity,
            plan_hash=plan.plan_hash,
            market_data_hash=market_frame.market_data_hash,
            market_bars=market_frame.bars,
            market_arrays=market_arrays,
        )

    def evaluate(
        self,
        market_frame: MarketFrame,
        plan: IndicatorPlan,
        *,
        market_arrays: MarketArrays | None = None,
        context: EvaluationContext | None = None,
    ) -> FeatureFrame:
        native = self.evaluate_native(
            market_frame, plan, market_arrays=market_arrays, context=context
        )
        return FeatureFrame(
            market=native.market,
            requested_range=native.requested_range,
            time_ms=native.time_ms,
            series={
                output_id: tuple(
                    None if value is None else serialize_value(value) for value in values
                )
                for output_id, values in native.series.items()
            },
            validity=native.validity,
            plan_hash=native.plan_hash,
            market_data_hash=native.market_data_hash,
            market_bars=native.market_bars,
            market_arrays=native.market_arrays,
        )
