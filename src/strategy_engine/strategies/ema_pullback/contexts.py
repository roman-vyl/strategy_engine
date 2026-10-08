"""BBB-compatible strategy-level context construction."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, node_spec
from strategy_engine.indicators.contracts import FeatureFrameLike
from strategy_engine.strategies.ema_pullback.feature_plan import EmaPullbackFeaturePlan
from strategy_engine.strategies.ema_pullback.stack_episode import (
    EpisodeBundle,
    resolve_episode_identities,
)


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
    """All declared strategy contexts evaluated once for one feature frame.

    `episodes` carries the EMA stack episodes evaluated beside the contexts
    (ema-stack-episode-v1), so predicates reach them through the same
    bundle. They are not contexts: `outputs` and `to_wire` never hold them."""

    time_ms: tuple[int, ...]
    outputs: tuple[ContextOutput, ...]
    episodes: EpisodeBundle | None = None

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


def _context_providers(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
) -> Iterator[tuple[str, dict[str, Any], dict[str, str]]]:
    """Validated `(context_ref, provider, plan columns)` per declared context,
    lazily in declaration order -- the single parsing/validation path shared
    by `build_context_bundle` (compute) and `resolve_context_bundle`."""

    contexts_raw = raw_spec.get("contexts", {})
    contexts = _mapping(contexts_raw, "raw_spec.contexts") if contexts_raw is not None else {}
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
        yield context_ref, provider, columns


def build_context_bundle(
    raw_spec: Mapping[str, Any],
    frame: FeatureFrameLike,
    plan: EmaPullbackFeaturePlan,
) -> ContextBundle:
    """Evaluate canonical BBB context providers from the enriched feature frame."""

    outputs: list[ContextOutput] = []
    for context_ref, provider, columns in _context_providers(raw_spec, plan):
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


# -- semantic node identity (batch-computation-reuse group 3) -----------------

CONTEXT_NODE_VERSION = 1


def resolve_context_bundle(
    raw_spec: Mapping[str, Any],
    plan: EmaPullbackFeaturePlan,
    feature_ids: Mapping[str, NodeSpec],
) -> dict[str, NodeSpec]:
    """`context_ref -> identity` of each context's state/up/down/neutral,
    plus `episode_identity_key -> identity` of each declared EMA stack
    episode and side (none for a spec without `ema_stack_episode`).

    The computation reads only the three stack series (by plan label, via
    `frame.series.get`, so an absent series is an absent upstream) -- the
    `context_ref` and provider echo are labels, not inputs. Timeframe and
    source enter through the upstream EMA identities.
    """

    contexts = {
        context_ref: node_spec(
            "context.htf_context",
            version=CONTEXT_NODE_VERSION,
            upstream={role: feature_ids.get(columns[role]) for role in ("fast", "anchor", "slow")},
        )
        for context_ref, _provider, columns in _context_providers(raw_spec, plan)
    }
    contexts.update(
        resolve_episode_identities(raw_spec, plan.episode_columns_by_ref, feature_ids)
    )
    return contexts
