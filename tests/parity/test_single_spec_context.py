"""Single-spec `/range` as an `EvaluationContext` of one root (OpenSpec
`batch-computation-reuse`, tasks 2.4, 5.2, 5.3).

The spec's "Single evaluation path" requirement: a single-spec evaluation is
a context with exactly one root, a range-batch is a context with N roots, and
a batch holding exactly one candidate produces the same Strategy Engine
output as `/range` for that candidate. This module proves, for every
candidate of every golden-corpus case (real + synthetic + alias probes):

1. `/range` (real route function, production wiring, fixture MDS) builds
   exactly one context, plans exactly one root through `plan_roots()`, and
   leaves the context fully settled (no live entry, empty refcounts, every
   predicted consumption released, zero unforeseen consumptions on success).
2. Its intermediates (plan, native frame, every evaluation stage, projection)
   are bit-exact with both the Group 1 golden candidate (pre-change
   evaluator) and a current `/range-batch` run holding only that candidate.
3. Wire output: the `.v2` result object `/range` returns, placed in the batch
   line envelope, is byte-identical to the golden NDJSON line and to the
   batch-of-one line; a failing candidate raises the same category / code /
   message / payload at the same evaluation-sequence position, and its
   batch error envelope is byte-identical too.

Plus: the HTTP-level `/range` body equals the batch line's `result`, and the
diagnostics entrypoint (same context-of-one mechanism) equals a direct,
context-free evaluation of the same request.
"""

from __future__ import annotations

import contextlib
import json
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

import parity.harness as harness
import strategy_engine.service.wiring as wiring
import strategy_engine.strategies.application.evaluate_range as evaluate_range_module
from parity.compare import compare_encoded, format_report
from parity.harness import (
    GOLDEN_DIR,
    Recorder,
    _exception_record,
    _frame_view,
    record_payload,
    recording_services,
)
from parity.snapshot import ArrayStore, encode
from parity.test_indicator_memo import _PINNED
from parity.test_parity_golden import CASE_NAMES, load_golden_case
from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.app import create_app
from strategy_engine.adapters.http.models import StrategyRangeRequestModel
from strategy_engine.adapters.http.strategy_serialization import (
    serialize_strategy_diagnostic_evaluation,
)
from strategy_engine.domain.errors import StrategyEngineError
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.evaluation_context import EvaluationContext
from strategy_engine.service.settings import Settings
from strategy_engine.service.wiring import ApplicationServices

_SECTIONS = ("plan", "frame", "evaluation", "projection")
_OUTCOME_FIELDS = ("category", "code", "message", "details", "stage")


@pytest.fixture(scope="module")
def golden_store() -> ArrayStore:
    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=True)


# -- instrumentation: the single-spec entrypoint's own contexts ---------------------------


@dataclass
class SingleProbe:
    contexts: list[EvaluationContext] = field(default_factory=list)
    planned: list[list[Counter[NodeSpec]]] = field(default_factory=list)


@contextlib.contextmanager
def single_contexts() -> Iterator[SingleProbe]:
    """Capture every `EvaluationContext` the single-spec entrypoint builds
    (patched in `evaluate_range`'s namespace only -- a batch's context is
    built in `evaluate_range_batch` and is not captured here)."""

    probe = SingleProbe()
    original = evaluate_range_module.EvaluationContext

    class CapturingContext(original):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            probe.contexts.append(self)

        def plan_roots(self, roots: Any) -> None:
            materialized = [tuple(identities) for identities in roots]
            probe.planned.append([Counter(identities) for identities in materialized])
            super().plan_roots(materialized)

    evaluate_range_module.EvaluationContext = CapturingContext  # type: ignore[misc]
    try:
        yield probe
    finally:
        evaluate_range_module.EvaluationContext = original  # type: ignore[misc]


# -- single-spec recording -------------------------------------------------------------------


def _single_payload(batch_payload: Mapping[str, Any], variant: Mapping[str, Any]) -> dict[str, Any]:
    """The `/range` body for one batch candidate: same market range, same
    expected hash, same strategy."""

    return json.loads(
        json.dumps(
            {
                "market": batch_payload["market"],
                "strategy": variant["strategy"],
                "expected_market_data_hash": batch_payload["expected_market_data_hash"],
            }
        )
    )


@dataclass
class SingleRecord:
    variant_id: str
    line: str  # the batch NDJSON line this /range outcome corresponds to
    outcome: dict[str, Any] | None  # None when the evaluation succeeded
    sections: dict[str, Any]
    store: ArrayStore
    probe: SingleProbe


def record_single(batch_payload: Mapping[str, Any], variant: Mapping[str, Any]) -> SingleRecord:
    model = StrategyRangeRequestModel.model_validate(_single_payload(batch_payload, variant))
    recorder = Recorder()
    store = ArrayStore()
    result: Any = None
    error: StrategyEngineError | None = None
    with single_contexts() as probe, recording_services(recorder) as services:
        try:
            result = strategy_routes.evaluate_strategy_range(model, services)
        except StrategyEngineError as exc:
            error = exc
    assert len(recorder.captures) == 1
    capture = recorder.captures[0]
    assert capture.exception is error
    if error is None:
        element = {"variant_id": variant["variant_id"], "result": result, "error": None}
        outcome = None
    else:
        # The exact per-variant error envelope `_stream_variants` builds.
        element = {
            "variant_id": variant["variant_id"],
            "result": None,
            "error": {"error": error.code, "message": error.message, "details": error.details},
        }
        outcome = {**_exception_record(error), "stage": list(capture.failure_stage or ())}
    sections = {
        "plan": encode(capture.plan, store),
        "frame": encode(_frame_view(capture.frame), store),
        "evaluation": encode(capture.evaluation, store),
        "projection": encode(capture.projection, store),
    }
    return SingleRecord(
        variant_id=variant["variant_id"],
        line=json.dumps(element) + "\n",
        outcome=outcome,
        sections=sections,
        store=store,
        probe=probe,
    )


def assert_context_of_one(single: SingleRecord) -> None:
    """Requirement 1: exactly one context with exactly one root, settled."""

    probe = single.probe
    if single.outcome is not None and single.outcome["stage"][:2] == [
        "execute_projection",
        "prepare",
    ]:
        # Rejected by request validation, before any market acquisition --
        # exactly as before: no context is ever built.
        assert probe.contexts == [], single.variant_id
        return
    assert len(probe.contexts) == 1, (single.variant_id, len(probe.contexts))
    assert len(probe.planned) == 1 and len(probe.planned[0]) == 1, single.variant_id
    context = probe.contexts[0]
    stats = context.stats
    assert context.memo_enabled
    assert context.live_entries == 0, single.variant_id
    assert context._refcounts == {}, single.variant_id  # noqa: SLF001
    assert context._pending is not None  # noqa: SLF001
    assert all(not counts for counts in context._pending), single.variant_id  # noqa: SLF001
    if single.outcome is None:
        assert stats.unforeseen_consumptions == 0, single.variant_id
        predicted = probe.planned[0][0]
        consumed = stats.compute_calls + stats.hit_calls
        assert set(consumed) <= set(predicted), single.variant_id
        assert set(stats.compute_calls), single.variant_id  # it really went through the memo
        assert all(count == 1 for count in stats.compute_calls.values()), single.variant_id


def _candidate(record_: Mapping[str, Any], variant_id: str) -> tuple[dict[str, Any], str]:
    for candidate in record_["candidates"]:
        if candidate["variant_id"] == variant_id:
            return candidate, record_["ndjson"]["lines"][candidate["variant_index"]]
    raise KeyError(variant_id)


def assert_single_equals_candidate(
    label: str,
    single: SingleRecord,
    reference: Mapping[str, Any],
    reference_store: ArrayStore,
) -> None:
    """Requirements 2 + 3 against one recorded batch candidate."""

    candidate, line = _candidate(reference, single.variant_id)
    assert single.line.encode("utf-8") == line.encode("utf-8"), (label, single.variant_id)
    outcome = candidate["outcome"]
    if single.outcome is None:
        assert outcome["disposition"] == "ok", (label, single.variant_id, outcome)
    else:
        assert outcome["disposition"] == "caught", (label, single.variant_id, outcome)
        for name in _OUTCOME_FIELDS:
            assert single.outcome[name] == outcome[name], (label, single.variant_id, name)
    for section in _SECTIONS:
        mismatches = compare_encoded(
            f"{label}.{single.variant_id}.{section}",
            candidate[section],
            single.sections[section],
            reference_store,
            single.store,
        )
        assert not mismatches, format_report(mismatches)


# -- 5.3: every golden-corpus candidate, /range vs golden vs /range-batch of one --------------


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_single_spec_range_equals_batch_of_one_and_golden_for_every_candidate(
    case_name: str, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    payload = golden["request_payload"]
    counts: Counter[str] = Counter()
    for variant in payload["variants"]:
        single = record_single(payload, variant)
        assert_context_of_one(single)
        batch_of_one, batch_store = record_payload(
            f"{case_name}.{variant['variant_id']}", {**payload, "variants": [variant]}
        )
        assert batch_of_one["ndjson"]["termination"] == {"kind": "complete"}
        assert len(batch_of_one["ndjson"]["lines"]) == 1
        assert_single_equals_candidate("batch-of-one", single, batch_of_one, batch_store)
        counts["compared_vs_batch_of_one"] += 1
        if golden["candidates"]:
            assert_single_equals_candidate("golden", single, golden, golden_store)
            counts["compared_vs_golden"] += 1
        counts["ok" if single.outcome is None else "caught"] += 1
    if golden["ndjson"]["termination"]["kind"] == "request_failed":
        # Whole-request batch failure (duplicate variant ids): no golden
        # candidate exists; each spec was still compared against its own
        # batch-of-one above.
        assert not golden["candidates"]
    else:
        assert counts["compared_vs_golden"] == len(payload["variants"])
    print(f"\nSINGLE-vs-BATCH-OF-ONE {case_name}: {dict(counts)}")


def test_pinned_source_collision_candidates_single_spec_byte_identical(
    golden_store: ArrayStore,
) -> None:
    """The pinned EMA source-collision candidates, called out explicitly:
    `/range` for each is byte-identical to its golden line and sections."""

    golden = load_golden_case("probe_source_distinct_same_period")
    payload = golden["request_payload"]
    variants = {variant["variant_id"]: variant for variant in payload["variants"]}
    for variant_id in _PINNED:
        single = record_single(payload, variants[variant_id])
        assert single.outcome is None, variant_id
        assert_context_of_one(single)
        assert_single_equals_candidate("golden", single, golden, golden_store)


# -- HTTP level and diagnostics -----------------------------------------------------------------


def test_range_http_body_equals_batch_line_result() -> None:
    """Over the real ASGI stack: `/range` returns 200 with a body whose
    JSON equals the golden batch line's `result` object; a failing
    candidate returns the error envelope with the batch error's code,
    message and details."""

    golden = load_golden_case("synthetic_failures_mixed")
    payload = golden["request_payload"]
    with (
        recording_services(Recorder()) as services,
        TestClient(create_app(services=services)) as client,
    ):
        for variant in payload["variants"]:
            candidate, line = _candidate(golden, variant["variant_id"])
            expected = json.loads(line)
            response = client.post(
                "/v1/strategy-evaluations/range", json=_single_payload(payload, variant)
            )
            if expected["error"] is None:
                assert response.status_code == 200, variant["variant_id"]
                assert response.json() == expected["result"], variant["variant_id"]
            else:
                body = response.json()
                assert response.status_code >= 400, variant["variant_id"]
                assert {key: body[key] for key in ("error", "message", "details")} == (
                    expected["error"]
                ), variant["variant_id"]


@contextlib.contextmanager
def plain_services() -> Iterator[ApplicationServices]:
    """Production `build_services` wiring with only the fixture MDS client
    swapped in (no recording hooks: the recorder only tracks projection
    calls)."""

    with harness._patched(wiring, "MarketDataServiceClient", harness._fixture_mds_client):
        services = wiring.build_services(Settings(mds_base_url=harness._FAKE_MDS_URL))
    try:
        yield services
    finally:
        services.close()


_DIAGNOSTIC_CASES = (
    ("real_3d_grid_subset", 0),
    ("probe_timeframe_alias", None),
    ("probe_source_distinct_same_period", None),
    ("synthetic_exit_structure", None),
)


def test_diagnostics_through_context_of_one_equal_context_free_evaluation() -> None:
    """`/range/diagnostics` runs through the same context-of-one mechanism;
    its dense output equals the strategy evaluator run directly on the same
    request with no evaluation context at all (every node computed
    directly, the pre-memoization behaviour)."""

    compared = 0
    for case_name, only in _DIAGNOSTIC_CASES:
        payload = load_golden_case(case_name)["request_payload"]
        variants = payload["variants"] if only is None else [payload["variants"][only]]
        for variant in variants:
            model = StrategyRangeRequestModel.model_validate(_single_payload(payload, variant))
            with single_contexts() as probe, plain_services() as services:
                via_route = strategy_routes.evaluate_strategy_range_diagnostics(model, services)
                request = model.to_domain()
                evaluator = services.evaluate_strategy_range._registry.evaluator(  # noqa: SLF001
                    request.strategy.strategy_id
                )
                assert evaluator is not None
                assert request.evaluation_context is None
                direct = serialize_strategy_diagnostic_evaluation(
                    evaluator.evaluate_diagnostics(request)
                )
            assert len(probe.contexts) == 1 and len(probe.planned[0]) == 1
            assert probe.contexts[0].live_entries == 0
            assert json.dumps(via_route).encode() == json.dumps(direct).encode(), (
                case_name,
                variant["variant_id"],
            )
            compared += 1
    assert compared >= 4
