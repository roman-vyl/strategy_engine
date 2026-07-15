"""Registered multi-indicator range evaluator."""

from __future__ import annotations

import pandas as pd

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.market import MarketFrame
from strategy_engine.domain.ranges import timeframe_duration_ms
from strategy_engine.domain.validity import Validity
from strategy_engine.indicators.contracts import FeatureFrame, IndicatorPlan, PlannedFeature
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
    market_frame_to_dataframe,
    resample_ohlcv,
    serialize_value,
)
from strategy_engine.indicators.implementations.rsi import (
    rsi_rolling_mean,
    validate_rsi_feature,
)


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


def _ema_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_ema_feature(feature)
    assert feature.source is not None
    return (
        frame[feature.source]
        .astype(float)
        .ewm(
            span=int(feature.parameters["period"]),
            adjust=False,
        )
        .mean()
    )


def _rsi_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_rsi_feature(feature)
    return rsi_rolling_mean(
        frame["close"].astype(float),
        period=int(feature.parameters["period"]),
    )


def _atr_values(frame: pd.DataFrame, feature: PlannedFeature) -> pd.Series:
    validate_atr_feature(feature)
    return atr_rolling_mean(
        frame["high"].astype(float),
        frame["low"].astype(float),
        frame["close"].astype(float),
        period=int(feature.parameters["period"]),
    )


class RangeIndicatorEvaluator:
    """Evaluate registered indicator features over one complete market range."""

    def evaluate(self, market_frame: MarketFrame, plan: IndicatorPlan) -> FeatureFrame:
        base_timeframe = market_frame.market.base_timeframe
        frame = market_frame_to_dataframe(market_frame)
        cached_frames: dict[str, pd.DataFrame] = {base_timeframe: frame, "base": frame}
        series: dict[str, tuple[str | None, ...]] = {}
        validity: dict[str, Validity] = {}
        adx_dmi_cache: dict[tuple[str, int], dict[str, pd.Series]] = {}

        for feature in plan.features:
            timeframe = _validate_feature_timeframe(
                feature,
                base_timeframe=base_timeframe,
            )
            feature_frame = cached_frames.get(timeframe)
            if feature_frame is None:
                feature_frame = resample_ohlcv(frame, timeframe)
                cached_frames[timeframe] = feature_frame

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
                multiplier = float(feature.parameters["multiplier"])
                output = tuple(
                    None if value is None else serialize_value(float(value) * multiplier)
                    for value in dependency_values
                )
                series[feature.output_id] = output
                dependency_validity = validity[dependency_id]
                validity[feature.output_id] = Validity(
                    valid_from_ms=dependency_validity.valid_from_ms,
                    warmup_bars=dependency_validity.warmup_bars,
                    complete=dependency_validity.complete,
                    reason=dependency_validity.reason,
                )
                continue
            elif feature.kind == "rsi":
                values = _rsi_values(feature_frame, feature)
            elif feature.kind in {"adx", "di_plus", "di_minus"}:
                validate_adx_dmi_feature(feature)
                period = int(feature.parameters["period"])
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
                    base_index=frame.index,
                )

            output = tuple(serialize_value(float(value)) for value in values.to_numpy())
            series[feature.output_id] = output
            first_valid_index = next(
                (index for index, value in enumerate(output) if value is not None),
                None,
            )
            validity[feature.output_id] = Validity(
                valid_from_ms=(
                    market_frame.bars[first_valid_index].open_time_ms
                    if first_valid_index is not None
                    else None
                ),
                warmup_bars=first_valid_index or 0,
                complete=first_valid_index is not None,
                reason=(None if first_valid_index is not None else "no_completed_feature_value"),
            )

        return FeatureFrame(
            market=market_frame.market,
            requested_range=market_frame.requested_range,
            time_ms=tuple(bar.open_time_ms for bar in market_frame.bars),
            series=series,
            validity=validity,
            plan_hash=plan.plan_hash,
            market_data_hash=market_frame.market_data_hash,
            market_bars=market_frame.bars,
        )
