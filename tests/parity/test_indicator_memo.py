"""Indicator-family memoization: memo OFF vs memo ON (OpenSpec
`batch-computation-reuse`, tasks 4.1-4.5).

Two independent things are proven here, over the whole golden corpus:

1. Correctness. The same evaluator code, recorded once with the range-batch
   memo OFF and once ON, reproduces the golden baseline bit-for-bit
   (intermediates, projection, NDJSON bytes, failure semantics) -- including
   heterogeneous, duplicated-spec and shuffled-order batches.
2. Reuse actually happens. The underlying indicator compute functions are
   spied on directly (independently of the context's own accounting): memo
   OFF computes once per consumption (today's behaviour); memo ON computes
   exactly once per unique `NodeSpec` identity in the batch.

Plus failure memoization/replay (D6), refcount eviction (D5), scope, and
lazy streaming checks.
"""

from __future__ import annotations

import contextlib
import functools
import random
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

import strategy_engine.indicators.implementations.range_evaluator as range_evaluator_module
import strategy_engine.strategies.application.evaluate_range_batch as batch_module
import strategy_engine.strategies.ema_pullback.evaluator as evaluator_module
from parity.compare import (
    FAILURE_FIELDS,
    Mismatch,
    compare_case,
    compare_encoded,
    format_report,
)
from parity.corpus import _variant, base_spec
from parity.harness import (
    Recorder,
    _fixture_mds_client,
    batch_payload,
    market_fixture_meta,
    record_payload,
    recording_services,
)
from parity.snapshot import ArrayStore
from parity.test_parity_golden import CASE_NAMES, load_golden_case
from strategy_engine.adapters.http.models import StrategyRangeBatchRequestModel
from strategy_engine.domain.errors import (
    EvaluationInvariantError,
    InvalidRequestError,
    StrategyEngineError,
)
from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.node_identity import NodeSpec, canonical, node_spec
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.evaluation_context import EvaluationContext, FailureRecord
from strategy_engine.indicators.implementations.range_evaluator import RangeIndicatorEvaluator
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)

# -- instrumentation ----------------------------------------------------------------

# The underlying per-kind indicator compute functions, looked up by module
# global name inside `range_evaluator._compute_feature` -- spying on them
# counts real executions, independently of `EvaluationContext.stats`.
_SPIED = {
    "ema": "_ema_values",
    "atr": "_atr_values",
    "rsi": "_rsi_values",
    "adx_dmi": "compute_adx_dmi",
    "atr_distance": "_atr_distance_values",
}


@dataclass
class Instrumented:
    contexts: list[EvaluationContext] = field(default_factory=list)
    raw_calls: Counter[str] = field(default_factory=Counter)

    @property
    def context(self) -> EvaluationContext:
        assert len(self.contexts) == 1, len(self.contexts)
        return self.contexts[0]


@contextlib.contextmanager
def _patched(module: Any, name: str, value: Any) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextlib.contextmanager
def instrumented() -> Iterator[Instrumented]:
    probe = Instrumented()

    class CapturingContext(EvaluationContext):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            probe.contexts.append(self)

    def spy(kind: str, function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def counted(*args: Any, **kwargs: Any) -> Any:
            probe.raw_calls[kind] += 1
            return function(*args, **kwargs)

        return counted

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(batch_module, "EvaluationContext", CapturingContext))
        for kind, name in _SPIED.items():
            stack.enter_context(
                _patched(
                    range_evaluator_module,
                    name,
                    spy(kind, getattr(range_evaluator_module, name)),
                )
            )
        yield probe


def record(
    name: str, payload: dict[str, Any], *, memo_enabled: bool
) -> tuple[dict[str, Any], ArrayStore, Instrumented]:
    with instrumented() as probe:
        actual, store = record_payload(name, payload, memo_enabled=memo_enabled)
    return actual, store, probe


def _kind(identity: NodeSpec) -> str:
    return identity.kind.removeprefix("indicator.")


def _indicator_only(counts: Counter[NodeSpec]) -> Counter[NodeSpec]:
    return Counter(
        {identity: n for identity, n in counts.items() if identity.kind.startswith("indicator.")}
    )


def _expected_raw_calls(compute_calls: Counter[NodeSpec]) -> Counter[str]:
    """Raw compute-function executions implied by per-identity compute
    calls: one per identity computation, except ADX/DI+/DI- which share one
    `compute_adx_dmi` per (timeframe, period) within a candidate."""

    expected: Counter[str] = Counter()
    for identity, count in compute_calls.items():
        kind = _kind(identity)
        if kind not in {"adx", "di_plus", "di_minus"}:
            expected[kind] += count
    return expected


@pytest.fixture(scope="module")
def golden_store() -> ArrayStore:
    from parity.harness import GOLDEN_DIR

    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=True)


# -- 4.5: memo OFF vs memo ON over the whole golden corpus --------------------------------

REUSE_REPORT: dict[str, dict[str, Any]] = {}


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_memo_off_and_on_match_golden_and_reuse_is_real(
    case_name: str, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    payload = golden["request_payload"]

    off, off_store, off_probe = record(case_name, payload, memo_enabled=False)
    on, on_store, on_probe = record(case_name, payload, memo_enabled=True)

    # (1) correctness: both modes bit-identical to the golden baseline, and
    # therefore to each other.
    off_mismatches = compare_case(golden, off, golden_store, off_store)
    assert not off_mismatches, "memo OFF:\n" + format_report(off_mismatches)
    on_mismatches = compare_case(golden, on, golden_store, on_store)
    assert not on_mismatches, "memo ON:\n" + format_report(on_mismatches)
    on_vs_off = compare_case(off, on, off_store, on_store)
    assert not on_vs_off, "memo ON vs OFF:\n" + format_report(on_vs_off)

    if golden["ndjson"]["termination"]["kind"] == "request_failed":
        # Whole-request failure before streaming: no context is ever built.
        assert off_probe.contexts == [] and on_probe.contexts == []
        assert not off_probe.raw_calls and not on_probe.raw_calls
        return

    off_stats = off_probe.context.stats
    on_stats = on_probe.context.stats
    # This is the indicator-family (4.4/4.5) check: other memoized families
    # (4.6) are proven in `test_strategy_node_memo.py`.
    off_computes = _indicator_only(off_stats.compute_calls)
    on_computes = _indicator_only(on_stats.compute_calls)
    consumptions = sum(off_computes.values())
    unique = set(off_computes)

    # Memo OFF is today's behaviour: every consumption computes, nothing is
    # retained or reused.
    assert off_stats.hits == 0 and off_stats.peak_entries == 0
    off_expected = _expected_raw_calls(off_computes)
    for kind in ("ema", "atr", "rsi", "atr_distance"):
        assert off_probe.raw_calls[kind] == off_expected[kind], (kind, off_probe.raw_calls)
    # ADX/DI+/DI- share one compute per (timeframe, period) per candidate.
    adx_computes_off = sum(
        count for identity, count in off_computes.items() if _kind(identity) == "adx"
    )
    assert off_probe.raw_calls["adx_dmi"] <= adx_computes_off

    # (2) reuse is real: memo ON computes each unique identity exactly once,
    # and every other consumption is served from the memo.
    assert set(on_computes) == unique
    assert all(count == 1 for count in on_stats.compute_calls.values()), on_stats.compute_calls
    assert sum(on_computes.values()) == len(unique)
    assert sum(_indicator_only(on_stats.hit_calls).values()) == consumptions - len(unique)
    assert on_stats.failure_replays == 0  # no corpus case fails inside a compute
    # Independent spy on the underlying compute functions agrees.
    on_expected = _expected_raw_calls(on_computes)
    for kind in ("ema", "atr", "rsi", "atr_distance"):
        assert on_probe.raw_calls[kind] == on_expected[kind], (kind, on_probe.raw_calls)
    adx_groups = {
        (identity.param("timeframe"), identity.param("period"))
        for identity in unique
        if _kind(identity) in {"adx", "di_plus", "di_minus"}
    }
    assert on_probe.raw_calls["adx_dmi"] == len(adx_groups)

    # The pre-pass predicted every consumption (every family); D5 eviction
    # left nothing.
    for stats in (off_stats, on_stats):
        assert stats.unforeseen_consumptions == 0
    assert on_probe.context.live_entries == 0
    assert off_probe.context.live_entries == 0

    if case_name in ("real_width_only_sweep", "real_3d_grid_subset", "real_tpsl_only_sweep"):
        # Guard against a vacuous pass: real sweeps share their indicators.
        assert sum(on_computes.values()) * 4 < consumptions, (consumptions, on_stats)
        assert on_probe.raw_calls["ema"] < off_probe.raw_calls["ema"]

    REUSE_REPORT[case_name] = {
        "variants": len(payload["variants"]),
        "consumptions_off": consumptions,
        "computes_on": sum(on_computes.values()),
        "unique": len(unique),
        "raw_off": dict(off_probe.raw_calls),
        "raw_on": dict(on_probe.raw_calls),
        "peak_entries_on": on_stats.peak_entries,
        "evictions_on": on_stats.evictions,
    }
    print(f"\nREUSE {case_name}: {REUSE_REPORT[case_name]}")


# -- shuffled-order batches -------------------------------------------------------------

_SHUFFLED_CASES = (
    "real_3d_grid_subset",
    "real_width_only_sweep",
    "synthetic_heterogeneous_shuffled",
    "synthetic_failures_mixed",
    "probe_source_distinct_same_period",
    "probe_timeframe_alias",
    "probe_duplicates_and_order",
)


def _by_variant(record_: dict[str, Any]) -> dict[str, tuple[dict[str, Any], str | None]]:
    lines = record_["ndjson"]["lines"]
    result = {}
    for candidate in record_["candidates"]:
        index = candidate["variant_index"]
        result[candidate["variant_id"]] = (candidate, lines[index] if index < len(lines) else None)
    return result


def _compare_by_variant(
    golden: dict[str, Any],
    actual: dict[str, Any],
    golden_store: ArrayStore,
    actual_store: ArrayStore,
) -> list[Mismatch]:
    """Per-variant parity for a reordered batch: every section, the failure
    record (minus the variant's position, which legitimately moved) and the
    variant's exact NDJSON line bytes."""

    golden_by = _by_variant(golden)
    actual_by = _by_variant(actual)
    mismatches: list[Mismatch] = []
    if sorted(golden_by) != sorted(actual_by):
        return [Mismatch("variants", "structure", "evaluated variant sets differ")]
    for variant_id, (golden_candidate, golden_line) in golden_by.items():
        actual_candidate, actual_line = actual_by[variant_id]
        where = f"variant={variant_id}"
        if golden_line != actual_line:
            mismatches.append(Mismatch(where, "ndjson-bytes", "line bytes differ"))
        for name in FAILURE_FIELDS:
            if name == "variant_index":
                continue
            if golden_candidate["outcome"].get(name) != actual_candidate["outcome"].get(name):
                mismatches.append(Mismatch(f"{where}.outcome.{name}", "failure", "differs"))
        for section in ("plan", "frame", "evaluation", "projection"):
            mismatches += compare_encoded(
                f"{where}.{section}",
                golden_candidate[section],
                actual_candidate[section],
                golden_store,
                actual_store,
            )
    return mismatches


@pytest.mark.parametrize("case_name", _SHUFFLED_CASES)
@pytest.mark.parametrize("seed", [1, 2])
def test_shuffled_order_memo_on_and_off_match_golden_per_variant(
    case_name: str, seed: int, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    assert golden["ndjson"]["termination"]["kind"] == "complete"
    payload = dict(golden["request_payload"])
    variants = list(payload["variants"])
    random.Random(seed).shuffle(variants)
    assert [v["variant_id"] for v in variants] != [v["variant_id"] for v in payload["variants"]]
    payload["variants"] = variants

    off, off_store, off_probe = record(case_name, payload, memo_enabled=False)
    on, on_store, on_probe = record(case_name, payload, memo_enabled=True)
    for label, actual, store in (("OFF", off, off_store), ("ON", on, on_store)):
        mismatches = _compare_by_variant(golden, actual, golden_store, store)
        assert not mismatches, f"memo {label}:\n" + format_report(mismatches)
    assert not compare_case(off, on, off_store, on_store)

    off_stats = off_probe.context.stats
    on_stats = on_probe.context.stats
    assert set(on_stats.compute_calls) == set(off_stats.compute_calls)
    assert all(count == 1 for count in on_stats.compute_calls.values())
    assert on_stats.unforeseen_consumptions == 0
    assert on_probe.context.live_entries == 0


# -- pinned feature-plan EMA source collision (must be untouched by memo) ------------------

_PINNED = (
    "anchor-ema200-close",
    "anchor-ema200-open",
    "anchor-ema200-high",
    "anchor-ema200-close-again",
    "within-spec-context-open-vs-stack-close",
    "within-spec-exit-ema-open-vs-anchor-close",
)


def test_pinned_source_collision_cases_byte_identical_with_memo_on(
    golden_store: ArrayStore,
) -> None:
    """`_ema_id` ignores source, so the plan label `ema_close_base_200` holds
    a close EMA in one candidate and an open/high EMA in another. The memo is
    keyed by source-aware identity, never by label: every candidate must
    still read exactly what it read before, and the within-spec collision
    (first-planned close EMA wins) must stay exactly as pinned."""

    case_name = "probe_source_distinct_same_period"
    golden = load_golden_case(case_name)
    on, on_store, probe = record(case_name, golden["request_payload"], memo_enabled=True)
    assert not compare_case(golden, on, golden_store, on_store)

    golden_by = _by_variant(golden)
    on_by = _by_variant(on)
    for variant_id in _PINNED:
        golden_candidate, golden_line = golden_by[variant_id]
        on_candidate, on_line = on_by[variant_id]
        assert on_line is not None and on_line.encode() == golden_line.encode(), variant_id
        for section in ("plan", "frame", "evaluation", "projection"):
            assert not compare_encoded(
                section, golden_candidate[section], on_candidate[section], golden_store, on_store
            ), (variant_id, section)

    ema200 = {
        identity.param("source")[1]
        for identity in probe.context.stats.compute_calls
        if identity.kind == "indicator.ema" and identity.param("period") == canonical(200)
    }
    # Distinct sources were computed separately (no cross-candidate collision)
    assert ema200 == {"close", "open", "high"}
    # ... and the within-spec open requests were never computed at all: the
    # plan still dedups them onto the close label (pinned, not fixed), and
    # the three close-anchored candidates plus the two within-spec ones share
    # the single close EMA(200) computation.
    close200 = node_spec(
        "indicator.ema",
        version=1,
        params={"timeframe": "5m", "source": "close", "period": 200},
    )
    assert probe.context.stats.compute_calls[close200] == 1


def test_within_spec_collision_alone_never_computes_the_open_ema(
    golden_store: ArrayStore,
) -> None:
    """With only the two within-spec collision candidates in the batch, no
    open-source EMA is ever computed (memo OFF or ON): plan deduplication
    still resolves both open requests onto the close label, exactly as
    pinned -- memoization sits downstream of that and does not alter it."""

    case_name = "probe_source_distinct_same_period"
    golden = load_golden_case(case_name)
    payload = dict(golden["request_payload"])
    payload["variants"] = [
        variant
        for variant in payload["variants"]
        if variant["variant_id"].startswith("within-spec-")
    ]
    assert len(payload["variants"]) == 2
    for memo in (False, True):
        actual, store, probe = record(case_name, payload, memo_enabled=memo)
        mismatches = _compare_by_variant(
            {
                **golden,
                "candidates": [
                    c for c in golden["candidates"] if c["variant_id"].startswith("within-spec-")
                ],
            },
            actual,
            golden_store,
            store,
        )
        assert not mismatches, format_report(mismatches)
        sources = {
            identity.param("source")[1]
            for identity in probe.context.stats.compute_calls
            if identity.kind == "indicator.ema"
        }
        assert sources == {"close"}, (memo, sources)


# -- D6: failure memoization and replay ----------------------------------------------


def _slow_ema_failure(exc_factory: Callable[[], Exception]) -> Callable[..., Any]:
    original = range_evaluator_module._ema_values

    def failing(frame: Any, feature: Any) -> Any:
        if feature.kind == "ema" and int(feature.parameters["period"]) == 500:
            raise exc_factory()
        return original(frame, feature)

    return failing


def _failure_payload() -> dict[str, Any]:
    base = base_spec()
    other = {**base, "anchor_stack": {**base["anchor_stack"], "slow": {"period": 400}}}
    return batch_payload(
        [
            _variant("uses-500-a", base),
            _variant("no-500", other),
            _variant("uses-500-b", base),
            _variant("uses-500-c", base),
        ]
    )


def test_engine_error_in_shared_node_is_memoized_and_replayed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        range_evaluator_module,
        "_ema_values",
        _slow_ema_failure(
            lambda: InvalidRequestError("injected failure", output_id="x", extra={"k": [1]})
        ),
    )
    payload = _failure_payload()
    off, off_store, off_probe = record("failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("failure", payload, memo_enabled=True)

    mismatches = compare_case(off, on, off_store, on_store)
    assert not mismatches, format_report(mismatches)
    outcomes = [candidate["outcome"] for candidate in on["candidates"]]
    assert [o["disposition"] for o in outcomes] == ["caught", "ok", "caught", "caught"]
    for outcome in (outcomes[0], outcomes[2], outcomes[3]):
        assert outcome["message"] == "injected failure"
        assert outcome["stage"] == outcomes[0]["stage"]
        assert outcome["details"] == outcomes[0]["details"]
    assert on["ndjson"]["termination"] == {"kind": "complete"}

    slow500 = node_spec(
        "indicator.ema", version=1, params={"timeframe": "5m", "source": "close", "period": 500}
    )
    on_stats = on_probe.context.stats
    assert on_stats.compute_calls[slow500] == 1  # failed once, replayed twice
    assert on_stats.failure_replays == 2
    assert off_probe.context.stats.compute_calls[slow500] == 3
    assert on_probe.raw_calls["ema"] < off_probe.raw_calls["ema"]
    assert on_probe.context.live_entries == 0


def test_non_engine_error_in_node_still_propagates_uncaught(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        range_evaluator_module,
        "_ema_values",
        _slow_ema_failure(lambda: ValueError("injected non-engine failure")),
    )
    payload = _failure_payload()
    off, off_store, _ = record("propagate", payload, memo_enabled=False)
    on, on_store, _ = record("propagate", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 0
    assert termination["category"] == "builtins.ValueError"


def test_projection_assertion_error_propagation_unchanged(monkeypatch: Any) -> None:
    original = evaluator_module.build_historical_execution_projection
    calls = {"n": 0}

    def flaky(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise AssertionError("injected projection assertion")
        return original(**kwargs)

    payload = batch_payload([_variant(f"v{i}", base_spec()) for i in range(3)])
    records = {}
    for memo in (False, True):
        calls["n"] = 0
        monkeypatch.setattr(evaluator_module, "build_historical_execution_projection", flaky)
        records[memo] = record("assertion", payload, memo_enabled=memo)
    (off, off_store, _), (on, on_store, _) = records[False], records[True]
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 1
    assert termination["category"] == "builtins.AssertionError"
    assert len(on["candidates"]) == 2  # the third variant is never evaluated


def test_failure_record_replays_observably_identical_new_objects() -> None:
    original = InvalidRequestError("bad", output_id="o", nested={"a": [1, 2]})
    record_ = FailureRecord.capture(original)
    assert record_ is not None and record_.caught_by_engine_boundary
    first, second = record_.replay(), record_.replay()
    for replayed in (first, second):
        assert type(replayed) is InvalidRequestError
        assert isinstance(replayed, StrategyEngineError)
        assert (replayed.code, replayed.message, replayed.details, replayed.status_code) == (
            original.code,
            original.message,
            original.details,
            original.status_code,
        )
        assert replayed.args == original.args and str(replayed) == str(original)
        assert replayed is not original and replayed.details is not original.details
    first.details["nested"]["a"].append(3)  # no shared mutable payload
    assert second.details == original.details == record_.replay().details

    value_error = FailureRecord.capture(ValueError("x", 1))
    assert value_error is not None and not value_error.caught_by_engine_boundary
    replayed_value_error = value_error.replay()
    assert type(replayed_value_error) is ValueError and replayed_value_error.args == ("x", 1)

    class Unrebuildable(Exception):
        def __init__(self, a: int, b: int) -> None:
            super().__init__(a + b)

    assert FailureRecord.capture(Unrebuildable(1, 2)) is None  # not memoized


# -- D5 refcounts / D1-D2 scope: unit level ------------------------------------------------


def _market_frame() -> MarketFrame:
    meta = market_fixture_meta()
    client = _fixture_mds_client("http://unused")
    try:
        return client.load_range(
            MarketStream(meta["ticker"], meta["timeframe"]),
            TimeRange(meta["from_ms"], meta["to_ms"]),
            expected_market_data_hash=meta["market_data_hash"],
        )
    finally:
        client.close()


@functools.lru_cache(maxsize=1)
def _shared_market_frame() -> MarketFrame:
    return _market_frame()


def _ident(name: str) -> NodeSpec:
    return node_spec(f"test.{name}", version=1)


def test_refcount_eviction_happens_at_last_consumer() -> None:
    a, b, c = _ident("a"), _ident("b"), _ident("c")
    context = EvaluationContext(_shared_market_frame())
    context.plan_roots([[a, b], [a], [a, c], [b]])
    assert (context.refcount(a), context.refcount(b), context.refcount(c)) == (3, 2, 1)
    calls: Counter[str] = Counter()

    def compute(name: str) -> Callable[[], tuple[str]]:
        def run() -> tuple[str]:
            calls[name] += 1
            return (name,)

        return run

    with context.root(0):
        assert context.memoized(a, compute("a")) == ("a",)
        assert context.memoized(b, compute("b")) == ("b",)
    assert context.live_entries == 2
    with context.root(1):
        assert context.memoized(a, compute("a")) == ("a",)
    with context.root(2):
        assert context.memoized(a, compute("a")) == ("a",)  # last consumer of a
        assert context.refcount(a) == 0
        assert context.memoized(c, compute("c")) == ("c",)  # single consumer: not retained
    assert context.live_entries == 1  # only b
    with context.root(3):
        context.memoized(b, compute("b"))
    assert context.live_entries == 0
    assert calls == Counter({"a": 1, "b": 1, "c": 1})
    assert context.stats.hits == 3 and context.stats.peak_entries == 2


def test_root_leftovers_are_released_when_a_root_fails_early() -> None:
    a, b = _ident("a"), _ident("b")
    context = EvaluationContext(_shared_market_frame())
    context.plan_roots([[a, b], [a, b], [b]])
    with context.root(0):
        context.memoized(a, lambda: 1)
        context.memoized(b, lambda: 2)
    with pytest.raises(InvalidRequestError), context.root(1):
        raise InvalidRequestError("root 1 fails before reading anything")
    # Root 1 will never read a: released, so a is evicted now, not at batch end.
    assert context.refcount(a) == 0 and context.refcount(b) == 1
    assert context.live_entries == 1
    with context.root(2):
        assert context.memoized(b, lambda: -1) == 2
    assert context.live_entries == 0


def test_unforeseen_consumption_is_served_but_never_extends_retention() -> None:
    a = _ident("a")
    context = EvaluationContext(_shared_market_frame())
    context.plan_roots([[], []])
    with context.root(0):
        assert context.memoized(a, lambda: 1) == 1
    with context.root(1):
        assert context.memoized(a, lambda: 2) == 2  # recomputed: nothing retained
    assert context.stats.unforeseen_consumptions == 2 and context.live_entries == 0


def test_memo_disabled_runs_the_same_bookkeeping_but_never_retains() -> None:
    a = _ident("a")
    context = EvaluationContext(_shared_market_frame(), memo_enabled=False)
    context.plan_roots([[a], [a], [a]])
    for index in range(3):
        with context.root(index):
            context.memoized(a, lambda: object())
    assert context.stats.compute_calls[a] == 3 and context.stats.hits == 0
    assert context.refcount(a) == 0 and context.live_entries == 0


def test_context_misuse_fails_closed() -> None:
    frame = _shared_market_frame()
    context = EvaluationContext(frame)
    context.plan_roots([[]])
    with pytest.raises(EvaluationInvariantError):
        context.plan_roots([[]])
    with pytest.raises(EvaluationInvariantError), context.root(0), context.root(0):
        pass
    assert context.scope == (frame.market, frame.requested_range, frame.market_data_hash)


def test_context_is_scoped_to_its_exact_market_frame() -> None:
    frame = _shared_market_frame()
    other = _market_frame()  # equal content, different object
    plan = build_feature_plan_from_canonical_spec(base_spec()).indicator_plan
    evaluator = RangeIndicatorEvaluator()
    with pytest.raises(EvaluationInvariantError, match="evaluation context"):
        evaluator.evaluate_native(other, plan, context=EvaluationContext(frame))
    context = EvaluationContext(frame)
    with pytest.raises(EvaluationInvariantError, match="context's arrays"):
        evaluator.evaluate_native(
            frame,
            plan,
            market_arrays=EvaluationContext(frame).market_arrays,
            context=context,
        )


# -- NDJSON laziness: first root does not wait for later-only nodes ---------------------------


def test_first_root_is_emitted_before_later_only_identities_are_computed() -> None:
    base = base_spec()
    later = {**base, "anchor_stack": {**base["anchor_stack"], "slow": {"period": 450}}}
    payload = batch_payload([_variant("first", base), _variant("later", later)])
    request = StrategyRangeBatchRequestModel.model_validate(payload).to_domain()
    later_only = node_spec(
        "indicator.ema", version=1, params={"timeframe": "5m", "source": "close", "period": 450}
    )
    with instrumented() as probe, recording_services(Recorder(), memo_enabled=True) as services:
        outcomes = services.evaluate_strategy_range_batch.execute(request)
        first = next(outcomes)
        assert first.variant_id == "first" and first.error is None
        stats = probe.context.stats
        assert later_only not in stats.compute_calls
        # ... although the pre-pass already knows the later root needs it.
        assert probe.context.refcount(later_only) == 1
        second = next(outcomes)
        assert second.variant_id == "later" and stats.compute_calls[later_only] == 1
        assert list(outcomes) == []
