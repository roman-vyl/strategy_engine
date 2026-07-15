"""BBB-compatible strategy-level context construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.indicators.contracts import FeatureFrame
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan


@dataclass(frozen=True, slots=True)
class ContextOutput:
    """One context provider evaluated on the base-timeframe grid."""

    context_ref: str
    provider: dict[str, Any]
    state: tuple[str, ...]
    up: tuple[bool, ...]
    down: tuple[bool, ...]
    neutral: tuple[bool, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "context_ref": self.context_ref,
            "provider": self.provider,
            "state": list(self.state),
            "up": list(self.up),
            "down": list(self.down),
            "neutral": list(self.neutral),
        }


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """All declared strategy contexts evaluated once for one feature frame."""

    time_ms: tuple[int, ...]
    outputs: tuple[ContextOutput, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "time_ms": list(self.time_ms),
            "items": {output.context_ref: output.to_wire() for output in self.outputs},
        }


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidRequestError(f"{path} must be an object")
    return value


def _evaluate_stack(
    fast: tuple[str | None, ...] | None,
    anchor: tuple[str | None, ...] | None,
    slow: tuple[str | None, ...] | None,
    *,
    size: int,
) -> tuple[tuple[str, ...], tuple[bool, ...], tuple[bool, ...], tuple[bool, ...]]:
    if fast is None or anchor is None or slow is None:
        neutral = tuple(True for _ in range(size))
        false = tuple(False for _ in range(size))
        return tuple("neutral" for _ in range(size)), false, false, neutral

    states: list[str] = []
    up_mask: list[bool] = []
    down_mask: list[bool] = []
    neutral_mask: list[bool] = []
    for fast_raw, anchor_raw, slow_raw in zip(fast, anchor, slow, strict=True):
        if fast_raw is None or anchor_raw is None or slow_raw is None:
            is_up = False
            is_down = False
        else:
            fast_value = float(fast_raw)
            anchor_value = float(anchor_raw)
            slow_value = float(slow_raw)
            is_up = fast_value > anchor_value > slow_value
            is_down = fast_value < anchor_value < slow_value
        is_neutral = not is_up and not is_down
        up_mask.append(is_up)
        down_mask.append(is_down)
        neutral_mask.append(is_neutral)
        states.append("up" if is_up else "down" if is_down else "neutral")
    return tuple(states), tuple(up_mask), tuple(down_mask), tuple(neutral_mask)


def build_context_bundle(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrame,
    plan: EmaPullbackFeaturePlan,
) -> ContextBundle:
    """Evaluate canonical BBB context providers from the enriched feature frame."""

    contexts_raw = raw_spec.get("contexts", {})
    contexts = _mapping(contexts_raw, "raw_spec.contexts") if contexts_raw is not None else {}
    outputs: list[ContextOutput] = []
    for context_ref_raw, provider_raw in contexts.items():
        context_ref = str(context_ref_raw)
        provider = dict(_mapping(provider_raw, f"raw_spec.contexts.{context_ref}"))
        if provider.get("component_id") != "htf_context":
            raise InvalidRequestError(
                "unsupported context provider",
                context_ref=context_ref,
                component_id=provider.get("component_id"),
            )
        columns = plan.htf_context_columns_by_ref.get(context_ref)
        if columns is None:
            raise InvalidRequestError(
                "context provider has no feature-plan mapping",
                context_ref=context_ref,
            )
        state, up, down, neutral = _evaluate_stack(
            frame.series.get(columns["fast"]),
            frame.series.get(columns["anchor"]),
            frame.series.get(columns["slow"]),
            size=len(frame.time_ms),
        )
        outputs.append(
            ContextOutput(
                context_ref=context_ref,
                provider=provider,
                state=state,
                up=up,
                down=down,
                neutral=neutral,
            )
        )
    return ContextBundle(time_ms=frame.time_ms, outputs=tuple(outputs))
