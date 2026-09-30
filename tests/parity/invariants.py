"""Declared-invariant regression artifact (OpenSpec
`composite-setup-pre-entry-predicates-v1`, tasks 0.1/0.2).

Extracts, for specs without `composite_setup`, exactly the quantities that
change promises to keep invariant -- nothing else:

- `public`: the public `/range-batch` NDJSON line of every candidate (the
  result Research Service consumes) -- design D6/D13, `batch-computation-reuse`
  "Bit-exact parity" + "No compute regression for existing specs";
- `plan`: `plan_hash` and the ordered plan feature labels -- design D6
  ("plan unchanged without composite"), D13 (labels unchanged);
- `nodes`: the multiset of memoized node identities with their compute
  counts, and the per-family totals -- `batch-computation-reuse`
  "No compute regression for existing specs", design D10;
- `indicator_contract`: `IndicatorRegistry` responses and the
  `resolve_feature` identity of one representative feature per existing
  kind -- design D13 ("existing kinds unchanged by the contract").

Deliberately NOT captured: trace dictionaries, key orders, reprs of
internal dataclasses, debug-only fields, timings, memo hit/eviction
statistics. A change that does not touch these invariants must not break
this artifact.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from typing import Any

import strategy_engine.strategies.application.evaluate_range_batch as batch_module
from parity.harness import Case, Recorder, _drain_route, recording_services
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.contracts import PlannedFeature
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.indicators.implementations.range_evaluator import resolve_feature
from strategy_engine.service.registries import IndicatorRegistry


def _digest(value: object) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def _canonical_node(identity: NodeSpec | None) -> object:
    """Hash-seed-independent canonical form of one identity: frozenset
    upstream slots (commutative combinators) are serialized sorted, since a
    frozenset's own iteration order depends on string hash randomization."""

    if identity is None:
        return None
    upstream: list[tuple[str, object]] = []
    for role, dependency in identity.upstream:
        if isinstance(dependency, frozenset):
            upstream.append((role, sorted(repr(_canonical_node(item)) for item in dependency)))
        else:
            upstream.append((role, _canonical_node(dependency)))
    return (identity.kind, identity.version, identity.params, tuple(upstream), identity.side)


def node_key(identity: NodeSpec) -> str:
    """Stable textual key of one identity (its full canonical content)."""

    return _digest(_canonical_node(identity))


def node_family(identity: NodeSpec) -> str:
    return identity.kind


@contextlib.contextmanager
def _capturing_contexts() -> Iterator[list[EvaluationContext]]:
    contexts: list[EvaluationContext] = []
    original = batch_module.EvaluationContext

    class CapturingContext(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            contexts.append(self)

    batch_module.EvaluationContext = CapturingContext  # type: ignore[misc]
    try:
        yield contexts
    finally:
        batch_module.EvaluationContext = original  # type: ignore[misc]


def case_invariants(case: Case) -> dict[str, Any]:
    recorder = Recorder()
    with _capturing_contexts() as contexts, recording_services(
        recorder, memo_enabled=True
    ) as services:
        ndjson = _drain_route(services, case.payload())
    assert len(contexts) <= 1, len(contexts)
    compute_calls: Counter[NodeSpec] = (
        contexts[0].stats.compute_calls if contexts else Counter()
    )
    candidates = []
    for capture in recorder.captures:
        plan = capture.plan
        candidates.append(
            {
                "variant_index": capture.index,
                "plan_hash": plan.indicator_plan.plan_hash if plan is not None else None,
                "plan_labels": (
                    [feature.output_id for feature in plan.indicator_plan.features]
                    if plan is not None
                    else None
                ),
            }
        )
    families: Counter[str] = Counter()
    for identity, count in compute_calls.items():
        families[node_family(identity)] += count
    return {
        "public": {
            "termination": ndjson["termination"].get("kind"),
            "lines": [_digest(line) for line in ndjson["lines"]],
        },
        "plan": candidates,
        "nodes": {
            "per_family": dict(sorted(families.items())),
            "identities": dict(
                sorted(
                    (node_key(identity), count) for identity, count in compute_calls.items()
                )
            ),
        },
    }


# One representative request per existing kind (parameters exactly as the
# planner emits them today).
_REPRESENTATIVE_FEATURES: tuple[PlannedFeature, ...] = (
    PlannedFeature("ema_close_base_50", "ema", "base", "close", {"period": 50}),
    PlannedFeature("ema_close_1h_200", "ema", "1h", "open", {"period": 200}),
    PlannedFeature("atr_close_base_14", "atr", "base", "close", {"period": 14}),
    PlannedFeature("rsi_close_15m_14", "rsi", "15m", "close", {"period": 14}),
    PlannedFeature("adx_close_1h_14", "adx", "1h", "close", {"period": 14}),
    PlannedFeature("di_plus_close_1h_14", "di_plus", "1h", "close", {"period": 14}),
    PlannedFeature("di_minus_close_1h_14", "di_minus", "1h", "close", {"period": 14}),
)


def indicator_contract_invariants(*, base_timeframe: str = "5m") -> dict[str, Any]:
    registry = IndicatorRegistry()
    definitions = registry.list_definitions()
    identities = {}
    resolved: dict[str, NodeSpec] = {}
    for feature in _REPRESENTATIVE_FEATURES:
        identity = resolve_feature(feature, base_timeframe=base_timeframe, upstream=resolved)
        resolved[feature.output_id] = identity
        identities[feature.output_id] = node_key(identity)
    distance = PlannedFeature(
        "atr_close_base_14_x2_0",
        "atr_distance",
        "base",
        None,
        {"multiplier": 2.0},
        ("atr_close_base_14",),
    )
    identities[distance.output_id] = node_key(
        resolve_feature(distance, base_timeframe=base_timeframe, upstream=resolved)
    )
    return {
        "definitions": json.loads(json.dumps(definitions, sort_keys=True)),
        "schemas": {
            item["indicator_id"]: json.loads(
                json.dumps(registry.get_schema(item["indicator_id"]), sort_keys=True)
            )
            for item in definitions
        },
        "feature_identities": identities,
    }
