"""Golden recorder (OpenSpec `batch-computation-reuse`, task 1.1).

Drives the real, unmodified Strategy Engine in-process, exactly the way a
Research Service batch reaches it:

    JSON body -> StrategyRangeBatchRequestModel -> real `/range-batch` route
    function -> EvaluateStrategyRangeBatch (production `build_services`
    wiring) -> EvaluateStrategyRange.execute_projection per variant ->
    EmaPullbackRangeEvaluator -> real MarketDataServiceClient (served the
    recorded MDS response bytes through an httpx.MockTransport)

and records, per candidate:

- `plan`        EmaPullbackFeaturePlan
- `frame`       NativeFeatureFrame (indicator series as float64 bytes,
                validity, hashes; market_bars omitted - pinned by the input
                fixture + market_data_hash)
- `evaluation`  EmaPullbackEvaluation: contexts, context-consumption gates,
                direction/blocker masks, setup masks + traces, trigger
                masks + traces, entries, every ExitPolicyEvaluation field,
                potential entries
- `projection`  HistoricalExecutionProjection
- `outcome`     ok / caught / propagated failure record (category, code,
                message, details, variant position, stage path)

plus the exact NDJSON bytes of every streamed line and how the stream
terminated. Hooks are test-only subclasses/proxies and a reversible patch
of module-level stage-function names; no production file is modified.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import gzip
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

import strategy_engine.service.wiring as wiring
import strategy_engine.strategies.ema_pullback.evaluation as evaluation_module
import strategy_engine.strategies.ema_pullback.evaluator as evaluator_module
from parity.snapshot import ArrayStore, encode
from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.models import StrategyRangeBatchRequestModel
from strategy_engine.adapters.market_data_service.client import MarketDataServiceClient
from strategy_engine.domain.errors import StrategyEngineError
from strategy_engine.service.settings import Settings
from strategy_engine.service.wiring import ApplicationServices
from strategy_engine.strategies.application.evaluate_range import EvaluateStrategyRange
from strategy_engine.strategies.ema_pullback.evaluator import EmaPullbackRangeEvaluator

PARITY_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = PARITY_DIR / "fixtures"
CORPUS_DIR = PARITY_DIR / "corpus"
GOLDEN_DIR = PARITY_DIR / "golden"
MARKET_FIXTURE = "mds_btcusdt_p_5m_1786800000000_1790400000000.json.gz"
_FAKE_MDS_URL = "http://parity-fixture-mds"

# Stage functions called by name from the evaluation modules. Wrapping the
# module-global names (reversibly, for the duration of one recording) lets
# the harness report *where* inside a candidate's evaluation a failure was
# raised without touching production files.
_EVALUATION_STAGES = (
    "build_context_bundle",
    "build_context_consumption_evidence",
    "evaluate_direction_and_blockers",
    "evaluate_setups",
    "evaluate_triggers",
    "evaluate_risk_and_entries",
    "evaluate_exit_policy",
    "project_potential_entries",
)
_EVALUATOR_STAGES = ("evaluate_ema_pullback_frame", "build_historical_execution_projection")


# -- market data fixture ------------------------------------------------------


@functools.lru_cache(maxsize=1)
def market_fixture_bytes() -> bytes:
    return gzip.decompress((FIXTURE_DIR / MARKET_FIXTURE).read_bytes())


@functools.lru_cache(maxsize=1)
def market_fixture_meta() -> dict[str, Any]:
    payload = json.loads(market_fixture_bytes())
    return {
        "ticker": payload["ticker"],
        "timeframe": payload["timeframe"],
        "from_ms": payload["from_ms"],
        "to_ms": payload["to_ms"],
        "market_data_hash": payload["market_data_hash"],
        "bar_count": len(payload["candles"]),
    }


def _fixture_mds_transport() -> httpx.MockTransport:
    body = market_fixture_bytes()
    meta = market_fixture_meta()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/candles":
            query = request.url.params
            identity = (
                query.get("ticker"),
                query.get("timeframe"),
                int(query.get("from_ms", -1)),
                int(query.get("to_ms", -1)),
            )
            expected_hash = None
        elif request.method == "POST" and request.url.path == "/v1/historical-candles":
            data = json.loads(request.content)
            identity = (data["ticker"], data["timeframe"], data["from_ms"], data["to_ms"])
            expected_hash = data.get("expected_market_data_hash")
        else:
            return httpx.Response(404, json={"error": "not_found"})
        if identity != (meta["ticker"], meta["timeframe"], meta["from_ms"], meta["to_ms"]):
            return httpx.Response(
                409, json={"error": "fixture_range_mismatch", "message": repr(identity)}
            )
        if expected_hash is not None and expected_hash != meta["market_data_hash"]:
            return httpx.Response(
                409, json={"error": "market_data_hash_mismatch", "message": expected_hash}
            )
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    return httpx.MockTransport(handler)


def _fixture_mds_client(base_url: str, **_: Any) -> MarketDataServiceClient:
    return MarketDataServiceClient(
        base_url,
        client=httpx.Client(base_url=_FAKE_MDS_URL, transport=_fixture_mds_transport()),
    )


# -- recording hooks ------------------------------------------------------------


class StageTracer:
    """Tracks the stage stack of the candidate currently being evaluated
    and snapshots it at the innermost stage an exception escapes from."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.failure_stage: tuple[str, ...] | None = None

    def reset(self) -> None:
        self.stack.clear()
        self.failure_stage = None

    def wrap(self, name: str, function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def traced(*args: Any, **kwargs: Any) -> Any:
            self.stack.append(name)
            try:
                return function(*args, **kwargs)
            except BaseException:
                if self.failure_stage is None:
                    self.failure_stage = tuple(self.stack)
                raise
            finally:
                self.stack.pop()

        return traced


class _TracedMethod:
    """Pass-through proxy: traces one method, delegates everything else."""

    def __init__(self, target: Any, method: str, stage: str, tracer: StageTracer) -> None:
        self._target = target
        self._method = method
        self._traced = tracer.wrap(stage, getattr(target, method))

    def __getattr__(self, name: str) -> Any:
        if name == self._method:
            return self._traced
        return getattr(self._target, name)


@dataclass(slots=True)
class _CandidateCapture:
    index: int
    exception: BaseException | None = None
    failure_stage: tuple[str, ...] | None = None
    plan: Any = None
    frame: Any = None
    evaluation: Any = None
    projection: Any = None


@dataclass(slots=True)
class Recorder:
    tracer: StageTracer = field(default_factory=StageTracer)
    captures: list[_CandidateCapture] = field(default_factory=list)

    def begin(self) -> _CandidateCapture:
        self.tracer.reset()
        capture = _CandidateCapture(index=len(self.captures))
        self.captures.append(capture)
        return capture

    @property
    def current(self) -> _CandidateCapture:
        return self.captures[-1]


def _recording_strategy_range(recorder: Recorder) -> type[EvaluateStrategyRange]:
    class RecordingEvaluateStrategyRange(EvaluateStrategyRange):
        def __init__(self, registry: Any, validator: Any) -> None:
            super().__init__(
                registry, _TracedMethod(validator, "execute", "validate", recorder.tracer)
            )

        def _prepare(self, request: Any) -> Any:
            return recorder.tracer.wrap("prepare", super()._prepare)(request)

        def execute_projection(self, request: Any) -> Any:
            capture = recorder.begin()
            try:
                return recorder.tracer.wrap("execute_projection", super().execute_projection)(
                    request
                )
            except BaseException as exc:
                capture.exception = exc
                capture.failure_stage = recorder.tracer.failure_stage
                raise

    return RecordingEvaluateStrategyRange


def _recording_ema_pullback(recorder: Recorder) -> type[EmaPullbackRangeEvaluator]:
    class RecordingEmaPullbackRangeEvaluator(EmaPullbackRangeEvaluator):
        def __init__(self, feature_planner: Any, indicator_evaluator: Any) -> None:
            super().__init__(
                _TracedMethod(feature_planner, "execute", "feature_plan", recorder.tracer),
                _TracedMethod(indicator_evaluator, "execute_native", "indicators", recorder.tracer),
            )
            self._untraced_planner = feature_planner

        def _evaluate_frame_native(self, request: Any) -> Any:
            frame, evaluation = recorder.tracer.wrap(
                "evaluate_frame_native", super()._evaluate_frame_native
            )(request)
            capture = recorder.current
            capture.plan = self._untraced_planner.execute(request.strategy)
            capture.frame = frame
            capture.evaluation = evaluation
            return frame, evaluation

        def evaluate_execution_projection(self, request: Any) -> Any:
            projection = super().evaluate_execution_projection(request)
            recorder.current.projection = projection
            return projection

    return RecordingEmaPullbackRangeEvaluator


@contextlib.contextmanager
def _patched(module: Any, name: str, value: Any) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextlib.contextmanager
def recording_services(
    recorder: Recorder, *, memo_enabled: bool | None = None
) -> Iterator[ApplicationServices]:
    """Production `build_services` wiring with recording hooks and the
    fixture-backed MDS client. Stage-name patches stay active while the
    context is open (i.e. while the batch stream is being drained).

    `memo_enabled` (batch-computation-reuse group 4): None keeps the
    production default; True/False forces the range-batch memo toggle, so
    the same evaluator code can be recorded memo-ON and memo-OFF."""

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(wiring, "MarketDataServiceClient", _fixture_mds_client))
        if memo_enabled is not None:
            stack.enter_context(
                _patched(
                    wiring,
                    "EvaluateStrategyRangeBatch",
                    functools.partial(wiring.EvaluateStrategyRangeBatch, memo_enabled=memo_enabled),
                )
            )
        stack.enter_context(
            _patched(wiring, "EvaluateStrategyRange", _recording_strategy_range(recorder))
        )
        stack.enter_context(
            _patched(wiring, "EmaPullbackRangeEvaluator", _recording_ema_pullback(recorder))
        )
        services = wiring.build_services(Settings(mds_base_url=_FAKE_MDS_URL))
        for name in _EVALUATION_STAGES:
            stack.enter_context(
                _patched(
                    evaluation_module,
                    name,
                    recorder.tracer.wrap(name, getattr(evaluation_module, name)),
                )
            )
        for name in _EVALUATOR_STAGES:
            stack.enter_context(
                _patched(
                    evaluator_module,
                    name,
                    recorder.tracer.wrap(name, getattr(evaluator_module, name)),
                )
            )
        try:
            yield services
        finally:
            services.close()


# -- case execution ---------------------------------------------------------------


def batch_payload(
    variants: Sequence[Mapping[str, Any]], *, expected_market_data_hash: bool = True
) -> dict[str, Any]:
    """Range-batch request body in the exact shape Research Service sends
    (`strategy_engine_client.py`: market + expected hash + variants)."""

    meta = market_fixture_meta()
    return {
        "market": {
            "ticker": meta["ticker"],
            "base_timeframe": meta["timeframe"],
            "from_ms": meta["from_ms"],
            "to_ms": meta["to_ms"],
        },
        "expected_market_data_hash": (
            meta["market_data_hash"] if expected_market_data_hash else None
        ),
        "variants": [dict(variant) for variant in variants],
    }


def _exception_record(exc: BaseException) -> dict[str, Any]:
    kind = type(exc)
    record: dict[str, Any] = {
        "category": f"{kind.__module__}.{kind.__qualname__}",
        "code": exc.code if isinstance(exc, StrategyEngineError) else None,
        "message": exc.message if isinstance(exc, StrategyEngineError) else str(exc),
        "details": encode(exc.details, ArrayStore())
        if isinstance(exc, StrategyEngineError)
        else None,
    }
    return record


def _drain_route(services: ApplicationServices, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    model = StrategyRangeBatchRequestModel.model_validate(json.loads(body))
    try:
        response = strategy_routes.evaluate_strategy_range_batch(model, services)
    except Exception as exc:  # whole-request failure, before streaming
        return {"lines": [], "termination": {"kind": "request_failed", **_exception_record(exc)}}
    lines: list[str] = []

    async def drain() -> None:
        async for chunk in response.body_iterator:
            assert isinstance(chunk, bytes)
            lines.append(chunk.decode("utf-8"))

    try:
        asyncio.run(drain())
    except Exception as exc:  # propagated out of the stream mid-flight
        return {
            "lines": lines,
            "termination": {
                "kind": "propagated",
                "after_lines": len(lines),
                **_exception_record(exc),
            },
        }
    return {"lines": lines, "termination": {"kind": "complete"}}


def _frame_view(frame: Any) -> dict[str, Any] | None:
    if frame is None:
        return None
    return {
        "market": frame.market,
        "requested_range": frame.requested_range,
        "time_ms": frame.time_ms,
        "series": frame.series,
        "validity": frame.validity,
        "plan_hash": frame.plan_hash,
        "market_data_hash": frame.market_data_hash,
        "market_bar_count": len(frame.market_bars),
    }


def _outcome(
    capture: _CandidateCapture,
    variant_id: str,
    ndjson: Mapping[str, Any],
) -> dict[str, Any]:
    outcome: dict[str, Any] = {
        "disposition": "ok",
        "category": None,
        "code": None,
        "message": None,
        "details": None,
        "variant_index": capture.index,
        "variant_id": variant_id,
        "stage": None,
    }
    if capture.exception is None:
        return outcome
    termination = ndjson["termination"]
    lines = ndjson["lines"]
    if termination["kind"] == "propagated" and termination["after_lines"] == capture.index:
        disposition = "propagated"
    elif capture.index < len(lines) and json.loads(lines[capture.index])["error"] is not None:
        disposition = "caught"
    else:
        disposition = "unobserved"
    outcome.update(_exception_record(capture.exception))
    outcome["disposition"] = disposition
    outcome["stage"] = list(capture.failure_stage or ())
    return outcome


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    group: str  # "real" | "synthetic" | "probe"
    description: str
    provenance: Mapping[str, Any]
    variants: Sequence[Mapping[str, Any]]
    expected_market_data_hash: bool = True

    def payload(self) -> dict[str, Any]:
        return batch_payload(
            self.variants, expected_market_data_hash=self.expected_market_data_hash
        )


def record_payload(
    name: str, payload: Mapping[str, Any], *, memo_enabled: bool | None = None
) -> tuple[dict[str, Any], ArrayStore]:
    """Run one range-batch request through the real evaluator and return
    its canonical record plus the array store its encoding refers to."""

    store = ArrayStore()
    recorder = Recorder()
    with recording_services(recorder, memo_enabled=memo_enabled) as services:
        ndjson = _drain_route(services, payload)
    variant_ids = [variant["variant_id"] for variant in payload["variants"]]
    candidates = []
    for capture in recorder.captures:
        variant_id = variant_ids[capture.index]
        candidates.append(
            {
                "variant_index": capture.index,
                "variant_id": variant_id,
                "outcome": _outcome(capture, variant_id, ndjson),
                "plan": encode(capture.plan, store),
                "frame": encode(_frame_view(capture.frame), store),
                "evaluation": encode(capture.evaluation, store),
                "projection": encode(capture.projection, store),
            }
        )
    record = {
        "case": name,
        "request_payload": json.loads(json.dumps(payload)),
        "ndjson": ndjson,
        "candidates": candidates,
    }
    return record, store


def record_case(case: Case) -> tuple[dict[str, Any], ArrayStore]:
    record, store = record_payload(case.name, case.payload())
    record = {
        "case": case.name,
        "group": case.group,
        "description": case.description,
        "provenance": dict(case.provenance),
        **{key: value for key, value in record.items() if key != "case"},
    }
    return record, store
