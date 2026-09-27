"""All node families memoized together: the end-to-end golden-corpus gate
(OpenSpec `batch-computation-reuse`, task 4.8).

Tasks 4.4-4.7 enabled memoization one node family at a time (indicators ->
direction / blocker / setup / trigger + mask compositions -> exit rule /
aggregate / select) and each stage proved its own family in isolation. This
module adds no mechanism: it runs the already-built evaluator with every
family memoized at once, through the one `EvaluationContext`, and checks the
combined system:

1. Full golden corpus: memo ON == memo OFF == Group 1 golden, bit-exact,
   every case (intermediates, projection, NDJSON bytes, failure records).
2. Batch shapes, classified from the D5 pre-pass predictions themselves:
   homogeneous, partially shared, fully heterogeneous, duplicated-spec (all
   present) and shuffled order.
3. The pinned feature-plan EMA source-collision candidates.
4. Failure semantics: caught per variant, memoized failure replay in three
   families inside one batch, uncaught non-engine propagation.
5. NDJSON: request order, exact bytes, first line emitted through the real
   route body before any later-only identity (in any family) is computed.
6. After every completed batch: no live memo entry, empty refcount map,
   every root's predicted consumptions settled, and -- the hard gate -- zero
   consumptions the pre-pass did not predict.

Plus the consolidated compute-call-count report per family (OFF / ON /
unique) on the real corpus, printed by `test_zz_compute_call_count_report`.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import random
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

import strategy_engine.indicators.implementations.range_evaluator as range_evaluator_module
import strategy_engine.strategies.application.evaluate_range_batch as batch_module
import strategy_engine.strategies.ema_pullback.evaluator as evaluator_module
import strategy_engine.strategies.ema_pullback.exits as exits_module
import strategy_engine.strategies.ema_pullback.setups as setups_module
from parity import test_exit_node_memo as exit_memo
from parity import test_indicator_memo as indicator_memo
from parity import test_strategy_node_memo as strategy_memo
from parity.compare import FAILURE_FIELDS, compare_case, compare_encoded, format_report
from parity.corpus import (
    _RSI_BLOCKER,
    _TREND_BLOCKER,
    _atr_exit,
    _ema,
    _exits,
    _untouched,
    _variant,
    _width,
    _with,
    base_spec,
)
from parity.harness import (
    GOLDEN_DIR,
    Recorder,
    batch_payload,
    record_payload,
    recording_services,
)
from parity.snapshot import ArrayStore
from parity.test_parity_golden import CASE_NAMES, load_golden_case
from strategy_engine.adapters.http import strategy_routes
from strategy_engine.adapters.http.models import StrategyRangeBatchRequestModel
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec, canonical, node_spec
from strategy_engine.indicators.evaluation_context import EvaluationContext, EvaluationStats

# -- node families -------------------------------------------------------------------

INDICATOR = "indicator.*"
DIRECTION = "direction.*"
BLOCKER = "blocker.*"
SETUP = "setup.*"
TRIGGER = "trigger.*"
MASK = "mask.*"
EXIT_DISTANCE = "exit.distance.*"
EXIT_SIGNAL = "exit.signal.*"
EXIT_AGGREGATE = "exit.aggregate.*"
EXIT_SELECT = "exit.select.*"

FAMILIES = (
    INDICATOR,
    DIRECTION,
    BLOCKER,
    SETUP,
    TRIGGER,
    MASK,
    EXIT_DISTANCE,
    EXIT_SIGNAL,
    EXIT_AGGREGATE,
    EXIT_SELECT,
)

_KIND_PREFIXES = (
    ("indicator.", INDICATOR),
    ("direction.", DIRECTION),
    ("blocker.", BLOCKER),
    ("setup.", SETUP),
    ("trigger.", TRIGGER),
    ("mask.", MASK),
    ("exit.distance.", EXIT_DISTANCE),
    ("exit.signal.", EXIT_SIGNAL),
    ("exit.aggregate.", EXIT_AGGREGATE),
    ("exit.select_", EXIT_SELECT),
)

_WIDTH_PREFIX_KIND = "setup.anchor_stack_width.prefix"


def family(identity: NodeSpec) -> str:
    """Report family of a memoized identity. Any other kind fails: every
    memoized node must belong to one of the families enabled in 4.4-4.7."""

    for prefix, name in _KIND_PREFIXES:
        if identity.kind.startswith(prefix):
            return name
    raise AssertionError(f"memoized node of unknown family: {identity.kind}")


# Raw compute-function spies (reused from the per-family stages) -> family.
# Indicator spies are kept per kind: ADX/DI+/DI- share one `compute_adx_dmi`.
_STRATEGY_SPY_FAMILY = {
    strategy_memo.DIRECTION: DIRECTION,
    strategy_memo.GATED: MASK,
    strategy_memo.AND_ALL: MASK,
    strategy_memo.WIDTH_PREFIX: SETUP,
    strategy_memo.WIDTH_SUFFIX: SETUP,
    strategy_memo.UNTOUCHED: SETUP,
    strategy_memo.BOUNCE: SETUP,
    strategy_memo.TRIGGER: TRIGGER,
}
_EXIT_SPY_FAMILY = {
    exit_memo.SIGNAL: EXIT_SIGNAL,
    exit_memo.DISTANCE: EXIT_DISTANCE,
    exit_memo.ANY_SIGNAL: EXIT_AGGREGATE,
    exit_memo.MIN: EXIT_AGGREGATE,
    exit_memo.READY: EXIT_AGGREGATE,
    exit_memo.SELECT_BOOL: EXIT_SELECT,
    exit_memo.SELECT_FLOAT: EXIT_SELECT,
}


def _spy_family(node_type: str) -> str:
    if node_type.startswith("indicator."):
        return INDICATOR
    if node_type.startswith("blocker."):
        return BLOCKER
    if node_type in _STRATEGY_SPY_FAMILY:
        return _STRATEGY_SPY_FAMILY[node_type]
    return _EXIT_SPY_FAMILY[node_type]


# -- instrumentation: one context, every family's raw spies at once -----------------------


@dataclass
class Probe:
    contexts: list[EvaluationContext] = field(default_factory=list)
    raw_calls: Counter[str] = field(default_factory=Counter)
    # Per root, the D5 pre-pass prediction handed to `plan_roots`.
    predicted: list[Counter[NodeSpec]] = field(default_factory=list)
    # Cumulative `compute_calls` snapshot taken as each root ends.
    after_root: list[Counter[NodeSpec]] = field(default_factory=list)

    @property
    def context(self) -> EvaluationContext:
        assert len(self.contexts) == 1, len(self.contexts)
        return self.contexts[0]

    @property
    def stats(self) -> EvaluationStats:
        return self.context.stats

    def root_computes(self) -> list[Counter[NodeSpec]]:
        """Identities each root computed itself (not served by the memo)."""

        deltas = []
        previous: Counter[NodeSpec] = Counter()
        for snapshot in self.after_root:
            deltas.append(snapshot - previous)
            previous = snapshot
        return deltas


@contextlib.contextmanager
def _patched(module: Any, name: str, value: Any) -> Iterator[None]:
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextlib.contextmanager
def instrumented() -> Iterator[Probe]:
    probe = Probe()

    class CapturingContext(EvaluationContext):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            probe.contexts.append(self)

        def plan_roots(self, roots: Any) -> None:
            materialized = [tuple(identities) for identities in roots]
            probe.predicted.extend(Counter(identities) for identities in materialized)
            super().plan_roots(materialized)

        @contextlib.contextmanager
        def root(self, index: int) -> Iterator[None]:
            try:
                with super().root(index):
                    yield
            finally:
                probe.after_root.append(Counter(self.stats.compute_calls))

    def spy(function: Callable[..., Any], classify: Callable[..., str]) -> Callable[..., Any]:
        @functools.wraps(function)
        def counted(*args: Any, **kwargs: Any) -> Any:
            probe.raw_calls[classify(*args, **kwargs)] += 1
            return function(*args, **kwargs)

        return counted

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(batch_module, "EvaluationContext", CapturingContext))
        for kind, name in indicator_memo._SPIED.items():
            stack.enter_context(
                _patched(
                    range_evaluator_module,
                    name,
                    spy(getattr(range_evaluator_module, name), lambda *a, _k=kind, **k: _k),
                )
            )
        for module, name, classify in strategy_memo._SPIED:
            stack.enter_context(_patched(module, name, spy(getattr(module, name), classify)))
        for name, node_type in exit_memo._SPIED:
            stack.enter_context(
                _patched(
                    exits_module,
                    name,
                    spy(getattr(exits_module, name), lambda *a, _t=node_type, **k: _t),
                )
            )
        yield probe


def record(
    name: str, payload: dict[str, Any], *, memo_enabled: bool
) -> tuple[dict[str, Any], ArrayStore, Probe]:
    with instrumented() as probe:
        actual, store = record_payload(name, payload, memo_enabled=memo_enabled)
    # Indicator spies are recorded under their bare kind; tag them.
    for kind in indicator_memo._SPIED:
        if kind in probe.raw_calls:
            probe.raw_calls[f"indicator.{kind}"] = probe.raw_calls.pop(kind)
    return actual, store, probe


@pytest.fixture(scope="module")
def golden_store() -> ArrayStore:
    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=True)


# -- requirement 6: post-batch invariants -------------------------------------------------


def _all_ok(record_: Mapping[str, Any]) -> bool:
    return record_["ndjson"]["termination"] == {"kind": "complete"} and all(
        candidate["outcome"]["disposition"] == "ok" for candidate in record_["candidates"]
    )


def assert_post_batch(probe: Probe, record_: Mapping[str, Any], label: str) -> None:
    """Invariants after a batch whose stream completed.

    Every batch: no live entry, empty refcount map, every root's predicted
    consumptions settled. On a batch where every candidate succeeded, the
    hard gate: zero unforeseen consumptions, and every consumption the
    pre-pass predicted actually happened (memo OFF: exactly; memo ON:
    exactly, except the width prefix, which is consumed only from inside a
    *computed* width suffix and is released unconsumed when the suffix is
    served from the memo)."""

    assert record_["ndjson"]["termination"] == {"kind": "complete"}, label
    context = probe.context
    stats = context.stats
    assert context.live_entries == 0, (label, context.live_entries)
    assert context._refcounts == {}, (label, len(context._refcounts))  # noqa: SLF001
    assert context._pending is not None  # noqa: SLF001
    assert all(not counts for counts in context._pending), label  # noqa: SLF001
    assert len(probe.predicted) == len(record_["request_payload"]["variants"]), label
    assert len(probe.after_root) == len(record_["candidates"]), label
    if not _all_ok(record_):
        # Not the hard gate, but no corpus/constructed failure batch has
        # ever produced one either: every early exit is a predicted,
        # released consumption, never an unpredicted one.
        assert stats.unforeseen_consumptions == 0, (label, stats.unforeseen_consumptions)
        return
    assert stats.unforeseen_consumptions == 0, (
        f"HARD GATE {label}: {stats.unforeseen_consumptions} consumption(s) the D5 "
        "pre-pass did not predict on a fully successful batch"
    )
    predicted: Counter[NodeSpec] = Counter()
    for counts in probe.predicted:
        predicted.update(counts)
    consumed = stats.compute_calls + stats.hit_calls
    over = {
        identity: predicted[identity] - consumed[identity]
        for identity in predicted
        if predicted[identity] != consumed[identity]
    }
    assert set(consumed) <= set(predicted), label
    if context.memo_enabled:
        assert all(identity.kind == _WIDTH_PREFIX_KIND for identity in over), (
            label,
            Counter(identity.kind for identity in over),
        )
        assert all(count > 0 for count in over.values()), label
    else:
        assert not over, (label, Counter(identity.kind for identity in over))


# -- reuse contract + per-family counts ---------------------------------------------------


@dataclass(frozen=True)
class Row:
    off: int  # compute executions, memo OFF (context accounting)
    on: int  # compute executions, memo ON
    unique: int  # distinct semantic identities
    raw_off: int  # independent raw spy, memo OFF
    raw_on: int  # independent raw spy, memo ON


def _by(counts: Counter[NodeSpec], key: Callable[[NodeSpec], str]) -> dict[str, Counter[NodeSpec]]:
    grouped: dict[str, Counter[NodeSpec]] = {}
    for identity, count in counts.items():
        grouped.setdefault(key(identity), Counter())[identity] += count
    return grouped


def assert_reuse_and_count(
    off: Probe, on: Probe, *, all_ok: bool
) -> tuple[dict[str, Row], dict[str, Row]]:
    """The combined reuse contract over every family at once, from context
    accounting and the raw spies; returns (per-family rows, per-kind rows)."""

    off_stats, on_stats = off.stats, on.stats
    assert off_stats.hits == 0 and off_stats.peak_entries == 0
    assert set(on_stats.compute_calls) == set(off_stats.compute_calls)
    assert all(count == 1 for count in on_stats.compute_calls.values())
    for identity, count in off_stats.compute_calls.items():
        if identity.kind == _WIDTH_PREFIX_KIND:
            continue
        assert on_stats.hit_calls[identity] == count - 1, identity.kind
    # Width prefix: consumed once per *computed* width suffix.
    suffixes = sum(
        1
        for identity in on_stats.compute_calls
        if identity.kind == "setup.anchor_stack_width_setup"
    )
    prefix_consumed = sum(
        on_stats.compute_calls[i] + on_stats.hit_calls[i]
        for i in on_stats.compute_calls
        if i.kind == _WIDTH_PREFIX_KIND
    )
    assert prefix_consumed == suffixes

    raw_off_by_family: Counter[str] = Counter()
    raw_on_by_family: Counter[str] = Counter()
    for node_type, count in off.raw_calls.items():
        raw_off_by_family[_spy_family(node_type)] += count
    for node_type, count in on.raw_calls.items():
        raw_on_by_family[_spy_family(node_type)] += count

    # Independent raw spies agree with the context accounting.
    for kind in ("ema", "atr", "rsi", "atr_distance"):
        for probe in (off, on):
            computed = sum(
                n for i, n in probe.stats.compute_calls.items() if i.kind == f"indicator.{kind}"
            )
            assert probe.raw_calls[f"indicator.{kind}"] == computed, kind
    adx_groups = {
        (i.param("timeframe"), i.param("period"))
        for i in on_stats.compute_calls
        if i.kind in ("indicator.adx", "indicator.di_plus", "indicator.di_minus")
    }
    assert on.raw_calls["indicator.adx_dmi"] == len(adx_groups)
    off_family = _by(off_stats.compute_calls, family)
    on_family = _by(on_stats.compute_calls, family)
    for name in FAMILIES:
        if name == INDICATOR:
            continue
        direct_off = raw_off_by_family[name] - off_family.get(name, Counter()).total()
        direct_on = raw_on_by_family[name] - on_family.get(name, Counter()).total()
        # Direct (unmemoized) executions are those of candidates whose
        # identities could not be resolved (they fail in that stage):
        # exactly as many memo OFF as ON, and none on a successful batch.
        assert direct_off == direct_on >= 0, (name, direct_off, direct_on)
        if all_ok:
            assert direct_off == 0, (name, direct_off)

    families = {}
    for name in FAMILIES:
        off_counts = off_family.get(name, Counter())
        families[name] = Row(
            off=off_counts.total(),
            on=on_family.get(name, Counter()).total(),
            unique=len(off_counts),
            raw_off=raw_off_by_family[name],
            raw_on=raw_on_by_family[name],
        )
    kinds = {}
    off_kind = _by(off_stats.compute_calls, lambda i: i.kind)
    on_kind = _by(on_stats.compute_calls, lambda i: i.kind)
    for kind in sorted(off_kind):
        kinds[kind] = Row(
            off=off_kind[kind].total(),
            on=on_kind[kind].total(),
            unique=len(off_kind[kind]),
            raw_off=0,
            raw_on=0,
        )
    return families, kinds


def format_table(title: str, rows: Mapping[str, Row], *, raw: bool) -> str:
    header = f"{'family':32s} {'OFF':>7s} {'ON':>6s} {'unique':>7s}"
    if raw:
        header += f" {'rawOFF':>7s} {'rawON':>6s}"
    lines = [title, header]
    total = Row(0, 0, 0, 0, 0)
    for name, row in rows.items():
        line = f"{name:32s} {row.off:7d} {row.on:6d} {row.unique:7d}"
        if raw:
            line += f" {row.raw_off:7d} {row.raw_on:6d}"
        lines.append(line)
        total = Row(
            total.off + row.off,
            total.on + row.on,
            total.unique + row.unique,
            total.raw_off + row.raw_off,
            total.raw_on + row.raw_on,
        )
    line = f"{'TOTAL memoized nodes':32s} {total.off:7d} {total.on:6d} {total.unique:7d}"
    if raw:
        line += f" {total.raw_off:7d} {total.raw_on:6d}"
    lines.append(line)
    return "\n".join(lines)


# -- batch shapes, from the pre-pass predictions ---------------------------------------------


@dataclass(frozen=True)
class Shape:
    homogeneous: bool
    fully_heterogeneous: bool
    partially_shared: bool
    duplicated_spec: bool


def classify(predicted: list[Counter[NodeSpec]]) -> Shape:
    """Shape of a batch over the identity sets its roots will consume.
    Roots predicting nothing (e.g. an unknown strategy) are ignored."""

    sets = [frozenset(counts) for counts in predicted if counts]
    pairs = [(a, b) for index, a in enumerate(sets) for b in sets[index + 1 :]]
    homogeneous = len(sets) > 1 and len(set(sets)) == 1
    disjoint = len(sets) > 1 and all(not (a & b) for a, b in pairs)
    duplicated = len(set(sets)) < len(sets)
    return Shape(
        homogeneous=homogeneous,
        fully_heterogeneous=disjoint,
        partially_shared=len(sets) > 1 and not homogeneous and not disjoint,
        duplicated_spec=duplicated,
    )


SHAPES_SEEN: dict[str, Shape] = {}
PROPAGATION_STATE: dict[str, dict[str, int]] = {}
CORPUS_COUNTS: dict[str, tuple[int, dict[str, Row], dict[str, Row]]] = {}


# -- requirements 1 + 6: the full golden corpus, every family memoized ---------------------


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_full_corpus_all_families_memoized_equals_memo_off_and_golden(
    case_name: str, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    payload = golden["request_payload"]
    off, off_store, off_probe = record(case_name, payload, memo_enabled=False)
    on, on_store, on_probe = record(case_name, payload, memo_enabled=True)

    for label, actual, store in (("OFF", off, off_store), ("ON", on, on_store)):
        mismatches = compare_case(golden, actual, golden_store, store)
        assert not mismatches, f"memo {label} vs golden:\n" + format_report(mismatches)
    on_vs_off = compare_case(off, on, off_store, on_store)
    assert not on_vs_off, "memo ON vs OFF:\n" + format_report(on_vs_off)

    if golden["ndjson"]["termination"]["kind"] == "request_failed":
        assert off_probe.contexts == [] and on_probe.contexts == []
        assert not off_probe.raw_calls and not on_probe.raw_calls
        return

    assert on_probe.context.memo_enabled and not off_probe.context.memo_enabled
    assert_post_batch(off_probe, off, f"{case_name} OFF")
    assert_post_batch(on_probe, on, f"{case_name} ON")
    assert on_probe.stats.failure_replays == 0  # no corpus case fails inside a compute
    families, kinds = assert_reuse_and_count(off_probe, on_probe, all_ok=_all_ok(on))
    SHAPES_SEEN[case_name] = classify(on_probe.predicted)
    CORPUS_COUNTS[case_name] = (len(payload["variants"]), families, kinds)

    if case_name.startswith("real_"):
        # Non-vacuous: on the real sweeps every family present is shared,
        # except where the swept parameter is read by every node of that
        # family (the untouched-lookback sweep: each untouched setup and its
        # gated/AND compositions are a distinct identity per candidate).
        for name, row in families.items():
            if row.off:
                assert row.on == row.unique <= row.off, (name, row)
                if name not in (SETUP, MASK):
                    assert row.on < row.off, (name, row)
        assert sum(r.on for r in families.values()) < sum(r.off for r in families.values())
    print(
        "\n"
        + format_table(
            f"ALL-FAMILIES {case_name} ({len(payload['variants'])} variants)", families, raw=True
        )
    )


# -- requirement 2: batch shapes ------------------------------------------------------------


def _line(record_: Mapping[str, Any], variant_id: str) -> tuple[dict[str, Any], str]:
    for candidate in record_["candidates"]:
        if candidate["variant_id"] == variant_id:
            return candidate, record_["ndjson"]["lines"][candidate["variant_index"]]
    raise KeyError(variant_id)


def assert_variant_equal(
    reference: Mapping[str, Any],
    reference_id: str,
    reference_store: ArrayStore,
    actual: Mapping[str, Any],
    actual_id: str,
    actual_store: ArrayStore,
) -> None:
    """One candidate bit-identical to a reference candidate, possibly
    recorded under another variant_id: every section, the failure record
    (minus position/id) and the exact NDJSON line bytes, with the reference
    line's single `variant_id` value swapped for the actual one."""

    reference_candidate, reference_line = _line(reference, reference_id)
    actual_candidate, actual_line = _line(actual, actual_id)
    old = f'"variant_id": {json.dumps(reference_id)}'
    assert reference_line.count(old) == 1
    expected_line = reference_line.replace(old, f'"variant_id": {json.dumps(actual_id)}')
    assert actual_line.encode("utf-8") == expected_line.encode("utf-8"), actual_id
    for name in FAILURE_FIELDS:
        if name not in ("variant_index", "variant_id"):
            assert reference_candidate["outcome"][name] == actual_candidate["outcome"][name], name
    for section in ("plan", "frame", "evaluation", "projection"):
        mismatches = compare_encoded(
            f"{actual_id}.{section}",
            reference_candidate[section],
            actual_candidate[section],
            reference_store,
            actual_store,
        )
        assert not mismatches, format_report(mismatches)


def _record_off_on(
    name: str, payload: dict[str, Any]
) -> tuple[tuple[dict[str, Any], ArrayStore, Probe], tuple[dict[str, Any], ArrayStore, Probe]]:
    off = record(name, payload, memo_enabled=False)
    on = record(name, payload, memo_enabled=True)
    mismatches = compare_case(off[0], on[0], off[1], on[1])
    assert not mismatches, "memo ON vs OFF:\n" + format_report(mismatches)
    assert_post_batch(off[2], off[0], f"{name} OFF")
    assert_post_batch(on[2], on[0], f"{name} ON")
    return off, on


def _alone(variant: dict[str, Any]) -> tuple[dict[str, Any], ArrayStore]:
    """Per-candidate reference: the variant alone in its own batch, memo
    OFF -- nothing can be shared with, or served from, another candidate."""

    return record_payload("alone", batch_payload([variant]), memo_enabled=False)


def test_homogeneous_batch_computes_everything_once_and_matches_golden(
    golden_store: ArrayStore,
) -> None:
    """Six identical copies of a real 3D-grid candidate: the first root
    computes every identity, the other five compute nothing at all, and
    every copy is bit-identical to that candidate's golden record."""

    golden = load_golden_case("real_3d_grid_subset")
    source = golden["request_payload"]["variants"][0]
    ids = [f"homogeneous-{index}" for index in range(6)]
    payload = batch_payload([_variant(i, source["strategy"]["raw_spec"]) for i in ids])
    (off, off_store, off_probe), (on, on_store, on_probe) = _record_off_on("homogeneous", payload)

    shape = classify(on_probe.predicted)
    assert shape.homogeneous and shape.duplicated_spec
    SHAPES_SEEN["constructed_homogeneous"] = shape
    for variant_id in ids:
        for actual, store in ((off, off_store), (on, on_store)):
            assert_variant_equal(
                golden, source["variant_id"], golden_store, actual, variant_id, store
            )
    per_root_on = on_probe.root_computes()
    per_root_off = off_probe.root_computes()
    root0 = set(on_probe.predicted[0])
    assert set(per_root_on[0]) == root0
    assert all(not delta for delta in per_root_on[1:]), [d.total() for d in per_root_on]
    assert {family(i) for i in root0} == set(FAMILIES) - {EXIT_SIGNAL}  # no signal exit here
    # OFF: every root recomputes everything.
    assert all(delta == per_root_off[0] for delta in per_root_off)
    assert on_probe.stats.total_compute_calls == len(root0)


def _heterogeneous_spec(index: int) -> dict[str, Any]:
    """Candidate `index` of a batch in which no two candidates share any
    memoized node: every EMA / ATR / RSI period, threshold, lookback and
    exit parameter is distinct per candidate, and the blocker / signal exit
    kinds read side- and parameter-specific inputs."""

    fast, anchor, slow = 11 + index, 31 + index, 91 + index
    spec = _with(
        base_spec(),
        "anchor_stack",
        {"fast": _ema(fast), "anchor": _ema(anchor), "slow": _ema(slow)},
    )
    spec = _with(
        spec,
        "setups",
        [
            _width(
                atr_period=21 + index,
                min_current_width_atr=1 + index / 4,
                min_recent_width_atr=3 + index / 2,
                width_lookback_bars=60 + index,
            ),
            _untouched(lookback=40 + index, active_bars=2 + index),
        ],
    )
    spec = _with(spec, "components", "trigger", {"component_id": "reclaim_anchor", "lookback": 1})
    spec["components"]["blockers"] = [
        {**_RSI_BLOCKER, "rsi": {"timeframe": "base", "period": 9 + index}, "lookback": 10 + index}
    ]
    return _exits(
        spec,
        [
            _atr_exit("sl", "stop_loss", 2.0 + index / 8, period=33 + index),
            _atr_exit("tp", "take_profit", 4.0 + index / 8, period=33 + index),
            {
                "component_id": "ema_close_loss_exit",
                "exit_kind": "signal",
                "instance_id": "close-loss",
                "ema": {"timeframe": "base", "period": 151 + index},
                "confirm_bars": 1 + index,
            },
        ],
    )


def test_fully_heterogeneous_batch_shares_nothing_across_candidates() -> None:
    """Spec scenario "Fully heterogeneous batch degrades gracefully": no
    identity is shared by two candidates, so each root computes exactly its
    own identities (memo hits only ever serve a repeat inside one root), and
    every candidate is bit-identical to that candidate evaluated alone."""

    variants = [_variant(f"hetero-{index}", _heterogeneous_spec(index)) for index in range(5)]
    payload = batch_payload(variants)
    (off, off_store, off_probe), (on, on_store, on_probe) = _record_off_on("heterogeneous", payload)
    assert _all_ok(on)

    shape = classify(on_probe.predicted)
    assert shape.fully_heterogeneous and not shape.duplicated_spec
    SHAPES_SEEN["constructed_fully_heterogeneous"] = shape
    covered = {family(i) for counts in on_probe.predicted for i in counts}
    assert covered == set(FAMILIES), set(FAMILIES) - covered
    for index, delta in enumerate(on_probe.root_computes()):
        assert set(delta) == set(on_probe.predicted[index]), index
        assert all(count == 1 for count in delta.values())
    for variant in variants:
        reference, reference_store = _alone(variant)
        for actual, store in ((off, off_store), (on, on_store)):
            assert_variant_equal(
                reference,
                variant["variant_id"],
                reference_store,
                actual,
                variant["variant_id"],
                store,
            )


def _all_family_spec(*, untouched: int = 70, usd_tp: float = 1250.0) -> dict[str, Any]:
    """Every memoized family in one spec: HTF context selecting exit
    profiles, three blocker kinds, width + untouched + bounce setups, a
    reclaim trigger, ATR/USD distances and RSI/EMA signal exits."""

    spec = exit_memo.rich_exit_spec(usd_tp=usd_tp)
    spec = _with(
        spec,
        "setups",
        [_width(), _untouched(lookback=untouched), strategy_memo._BOUNCE],
    )
    spec["components"]["blockers"] = [
        {"component_id": "counter_candle_blocker", "instance_id": "counter-candle"},
        _RSI_BLOCKER,
        _TREND_BLOCKER,
    ]
    spec["components"]["trigger"] = {"component_id": "reclaim_anchor", "lookback": 2}
    return spec


def test_duplicated_spec_batch_duplicates_compute_nothing_new() -> None:
    """Two all-family specs A and B interleaved with duplicates
    (A, B, A, A, B, A): every duplicate root computes zero new identities,
    and each duplicate is bit-identical to its spec evaluated alone."""

    spec_a = _all_family_spec()
    spec_b = _all_family_spec(untouched=90, usd_tp=900.0)
    order = ["A", "B", "A", "A", "B", "A"]
    specs = {"A": spec_a, "B": spec_b}
    variants = [_variant(f"dup-{name}-{index}", specs[name]) for index, name in enumerate(order)]
    payload = batch_payload(variants)
    (off, off_store, off_probe), (on, on_store, on_probe) = _record_off_on("duplicated", payload)
    assert _all_ok(on)

    shape = classify(on_probe.predicted)
    assert shape.duplicated_spec and shape.partially_shared
    SHAPES_SEEN["constructed_duplicated_all_families"] = shape
    covered = {family(i) for i in on_probe.predicted[0]}
    assert covered == set(FAMILIES), set(FAMILIES) - covered
    deltas = on_probe.root_computes()
    first_seen: set[str] = set()
    for index, name in enumerate(order):
        if name in first_seen:
            assert not deltas[index], (index, name, deltas[index].total())
        else:
            assert deltas[index], index
        first_seen.add(name)
    # B shares everything that does not read its two differing inputs.
    assert set(deltas[1]) < set(on_probe.predicted[1])
    references = {name: _alone(_variant(f"alone-{name}", spec)) for name, spec in specs.items()}
    for index, name in enumerate(order):
        reference, reference_store = references[name]
        for actual, store in ((off, off_store), (on, on_store)):
            assert_variant_equal(
                reference,
                f"alone-{name}",
                reference_store,
                actual,
                f"dup-{name}-{index}",
                store,
            )


def test_golden_duplicated_spec_case_duplicates_compute_nothing_new(
    golden_store: ArrayStore,
) -> None:
    """The golden `probe_duplicates_and_order` case (dup-a, dup-b, five real
    candidates out of request order, dup-c): the two later duplicates of
    dup-a -- and the real candidate with the same spec -- compute nothing."""

    case_name = "probe_duplicates_and_order"
    golden = load_golden_case(case_name)
    on, on_store, probe = record(case_name, golden["request_payload"], memo_enabled=True)
    assert not compare_case(golden, on, golden_store, on_store)
    assert_post_batch(probe, on, case_name)
    ids = [variant["variant_id"] for variant in golden["request_payload"]["variants"]]
    deltas = dict(zip(ids, probe.root_computes(), strict=True))
    assert deltas["dup-a"]
    for variant_id in ("dup-b", "w01-lb070-r2_0", "dup-c"):  # same raw spec as dup-a
        assert not deltas[variant_id], variant_id


def test_every_batch_shape_is_exercised() -> None:
    """Runs last among the shape tests (file order): the corpus plus the
    constructed batches cover every required shape."""

    if not CORPUS_COUNTS:
        pytest.skip("corpus gate did not run in this session")
    shapes = SHAPES_SEEN.values()
    assert any(shape.homogeneous for shape in shapes)
    assert any(shape.fully_heterogeneous for shape in shapes)
    assert any(shape.partially_shared for shape in shapes)
    assert any(shape.duplicated_spec for shape in shapes)
    for name in (
        "real_3d_grid_subset",
        "real_width_only_sweep",
        "real_untouched_only_sweep",
        "real_tpsl_only_sweep",
    ):
        if name in SHAPES_SEEN:
            assert SHAPES_SEEN[name].partially_shared, name
    print("\nBATCH SHAPES:")
    for name, shape in sorted(SHAPES_SEEN.items()):
        flags = [key for key, value in vars(shape).items() if value]
        print(f"    {name:40s} {', '.join(flags)}")


_SHUFFLED_CASES = indicator_memo._SHUFFLED_CASES


@pytest.mark.parametrize("case_name", _SHUFFLED_CASES)
@pytest.mark.parametrize("order", ["seed-3", "reversed"])
def test_shuffled_order_all_families_memoized_matches_golden_per_variant(
    case_name: str, order: str, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    payload = dict(golden["request_payload"])
    variants = list(payload["variants"])
    if order == "reversed":
        variants.reverse()
    else:
        random.Random(3).shuffle(variants)
    assert [v["variant_id"] for v in variants] != [v["variant_id"] for v in payload["variants"]]
    payload["variants"] = variants

    (off, off_store, off_probe), (on, on_store, on_probe) = _record_off_on(case_name, payload)
    for label, actual, store in (("OFF", off, off_store), ("ON", on, on_store)):
        mismatches = indicator_memo._compare_by_variant(golden, actual, golden_store, store)
        assert not mismatches, f"memo {label}:\n" + format_report(mismatches)
    assert_reuse_and_count(off_probe, on_probe, all_ok=_all_ok(on))


# -- requirement 3: pinned source-collision candidates -----------------------------------------

_PINNED = indicator_memo._PINNED


def test_pinned_source_collision_cases_with_all_families_memoized(
    golden_store: ArrayStore,
) -> None:
    """Every pin the per-family stages made, checked in one all-families
    run: byte-identical lines and sections for all six candidates; the
    close/open/high EMA(200)s computed separately; the within-spec open
    requests still resolved onto the close label (never computed); the
    direction of the close-anchored stack shared by exactly the candidates
    that read the close EMA(200); the open-EMA close-loss exit reading the
    close EMA identity."""

    case_name = "probe_source_distinct_same_period"
    golden = load_golden_case(case_name)
    on, on_store, probe = record(case_name, golden["request_payload"], memo_enabled=True)
    assert not compare_case(golden, on, golden_store, on_store)
    assert_post_batch(probe, on, case_name)
    for variant_id in _PINNED:
        assert_variant_equal(golden, variant_id, golden_store, on, variant_id, on_store)

    computes = probe.stats.compute_calls
    ema200 = {
        i.param("source")[1]
        for i in computes
        if i.kind == "indicator.ema" and i.param("period") == canonical(200)
    }
    assert ema200 == {"close", "open", "high"}
    close200 = node_spec(
        "indicator.ema", version=1, params={"timeframe": "5m", "source": "close", "period": 200}
    )
    assert computes[close200] == 1
    directions = [i for i in computes if family(i) == DIRECTION]
    assert Counter(i.dependency("anchor").param("source")[1] for i in directions) == Counter(  # type: ignore[union-attr]
        {"close": 2, "open": 2, "high": 2}
    )
    close_directions = [
        i
        for i in directions
        if i.dependency("anchor").param("source") == ("str", "close")  # type: ignore[union-attr]
    ]
    # close, close-again and both within-spec candidates: 4 consumers per side.
    assert [computes[i] + probe.stats.hit_calls[i] for i in close_directions] == [4, 4]
    close_loss = [i for i in computes if i.kind == "exit.signal.ema_close_loss_exit"]
    assert len(close_loss) == 2
    for node in close_loss:
        assert node.dependency("ema") == close200


# -- requirement 4: failure semantics with every family memoized ----------------------------


def _failing(module: Any, name: str, should_fail: Callable[..., bool]) -> Callable[..., Any]:
    original = getattr(module, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if should_fail(*args, **kwargs):
            raise InvalidRequestError(f"injected {name} failure", node=name, k=[1])
        return original(*args, **kwargs)

    return wrapper


def _failure_spec(
    *, untouched: int = 90, usd_tp: float = 900.0, slow: int = 500, reclaim: int = 2
) -> dict[str, Any]:
    spec = _all_family_spec(untouched=untouched, usd_tp=usd_tp)
    spec["components"]["trigger"] = {"component_id": "reclaim_anchor", "lookback": reclaim}
    if slow != 500:
        spec = _with(spec, "anchor_stack", "slow", _ema(slow))
    return spec


# (variant id, spec, expected disposition, failing family or None)
_CROSS_FAMILY_FAILURES: tuple[tuple[str, dict[str, Any], str, str | None], ...] = (
    ("setup-fail-a", _failure_spec(untouched=70), "caught", "setup"),
    ("exit-fail-a", _failure_spec(usd_tp=1250.0), "caught", "exit"),
    ("ok-a", _failure_spec(), "ok", None),
    # Would fail in exits too, but its shared setup fails first.
    ("setup-fail-b", _failure_spec(untouched=70, usd_tp=1250.0, reclaim=3), "caught", "setup"),
    ("exit-fail-b", _failure_spec(usd_tp=1250.0, reclaim=3), "caught", "exit"),
    ("indicator-fail-a", _failure_spec(slow=450), "caught", "indicator"),
    # Would fail in setups and exits too, but its shared indicator fails first.
    (
        "indicator-fail-b",
        _failure_spec(slow=450, untouched=70, usd_tp=1250.0),
        "caught",
        "indicator",
    ),
    ("exit-fail-c", _failure_spec(usd_tp=1250.0), "caught", "exit"),
    ("ok-b", _failure_spec(), "ok", None),
)


def test_failures_in_three_families_are_memoized_and_replayed_in_one_batch(
    monkeypatch: Any,
) -> None:
    """A shared indicator (EMA 450), a shared setup (untouched lookback 70)
    and a shared exit rule (USD take-profit 1250) all fail in the same
    batch. Each fails once and is replayed -- same category, message,
    payload and stage -- to every later candidate reaching it; the replays
    of one family never leak into another family's failure or into the
    successful candidates, and memo ON is bit-identical to memo OFF."""

    monkeypatch.setattr(
        range_evaluator_module,
        "_ema_values",
        _failing(
            range_evaluator_module,
            "_ema_values",
            lambda frame, feature: int(feature.parameters["period"]) == 450,
        ),
    )
    monkeypatch.setattr(
        setups_module,
        "_untouched_anchor",
        _failing(
            setups_module,
            "_untouched_anchor",
            lambda frame, anchor_id, params, side: int(params.get("lookback", 50)) == 70,
        ),
    )
    monkeypatch.setattr(
        exits_module,
        "_distance",
        _failing(
            exits_module, "_distance", lambda df, rule, plan: rule.get("usd_distance") == 1250.0
        ),
    )
    payload = batch_payload([_variant(v, spec) for v, spec, _, _ in _CROSS_FAMILY_FAILURES])
    (off, _, off_probe), (on, _, on_probe) = _record_off_on("cross-family-failures", payload)

    outcomes = {c["variant_id"]: c["outcome"] for c in on["candidates"]}
    stage_tail = {
        "indicator": "indicators",
        "setup": "evaluate_setups",
        "exit": "evaluate_exit_policy",
    }
    by_family: dict[str, list[dict[str, Any]]] = {}
    for variant_id, _spec, disposition, failing in _CROSS_FAMILY_FAILURES:
        outcome = outcomes[variant_id]
        assert outcome["disposition"] == disposition, variant_id
        if failing is not None:
            assert outcome["stage"][-1] == stage_tail[failing], (variant_id, outcome["stage"])
            by_family.setdefault(failing, []).append(outcome)
    for failing, items in by_family.items():
        first = items[0]
        for other in items[1:]:
            for name in ("category", "code", "message", "details", "stage"):
                assert other[name] == first[name], (failing, name)
    messages = {items[0]["message"] for items in by_family.values()}
    assert len(messages) == 3

    stats = on_probe.stats
    failing_ids = {
        "indicator": node_spec(
            "indicator.ema",
            version=1,
            params={"timeframe": "5m", "source": "close", "period": 450},
        ),
        "setup": next(
            i
            for i in stats.compute_calls
            if i.kind == "setup.untouched_anchor_setup"
            and i.param("lookback") == ("int", 70)
            and i.side == "long"
        ),
        "exit": next(
            i
            for i in stats.compute_calls
            if i.kind == "exit.distance.constant_usd"
            and i.param("usd_distance") == canonical(1250.0)
        ),
    }
    # (memo OFF computes, memo ON computes, ON replays) per failing identity.
    expected = {"indicator": (2, 1, 1), "setup": (2, 1, 1), "exit": (3, 1, 2)}
    for failing, identity in failing_ids.items():
        assert (
            off_probe.stats.compute_calls[identity],
            stats.compute_calls[identity],
            stats.hit_calls[identity],
        ) == expected[failing], failing
    assert stats.failure_replays == sum(replays for _, _, replays in expected.values())
    assert off_probe.stats.failure_replays == 0


def test_projection_assertion_error_still_propagates_with_all_families_memoized(
    monkeypatch: Any,
) -> None:
    original = evaluator_module.build_historical_execution_projection
    calls = {"n": 0}

    def flaky(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise AssertionError("injected projection assertion")
        return original(**kwargs)

    payload = batch_payload([_variant(f"v{i}", _all_family_spec()) for i in range(3)])
    recorded = {}
    for memo in (False, True):
        calls["n"] = 0
        monkeypatch.setattr(evaluator_module, "build_historical_execution_projection", flaky)
        recorded[memo] = record("assertion", payload, memo_enabled=memo)
    (off, off_store, _), (on, on_store, on_probe) = recorded[False], recorded[True]
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 1
    assert termination["category"] == "builtins.AssertionError"
    assert termination["message"] == "injected projection assertion"
    assert len(on["candidates"]) == 2  # the third variant is never evaluated
    # The second root's own nodes were all served by the memo before the
    # projection raised: its failure is the projection step's, nothing else.
    assert not on_probe.root_computes()[1]
    PROPAGATION_STATE["projection AssertionError"] = _abandoned_state(on_probe)


def test_non_engine_error_in_memoized_exit_node_propagates_mid_batch(monkeypatch: Any) -> None:
    def raising(df: Any, rule: Any, plan: Any) -> Any:
        if rule.get("usd_distance") == 1250.0:
            raise ValueError("injected non-engine exit failure")
        return original(df, rule, plan)

    original = exits_module._distance
    monkeypatch.setattr(exits_module, "_distance", raising)
    payload = batch_payload(
        [
            _variant("ok", _all_family_spec(usd_tp=900.0)),
            _variant("raises", _all_family_spec(usd_tp=1250.0)),
            _variant("never-reached", _all_family_spec(usd_tp=1250.0)),
        ]
    )
    off, off_store, _ = record("propagate", payload, memo_enabled=False)
    on, on_store, on_probe = record("propagate", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 1
    assert termination["category"] == "builtins.ValueError"
    assert [c["variant_id"] for c in on["candidates"]] == ["ok", "raises"]
    PROPAGATION_STATE["exit ValueError"] = _abandoned_state(on_probe)


def _abandoned_state(probe: Probe) -> dict[str, int]:
    """What a propagated (terminated) stream leaves in its context: the
    roots after the failure never ran, so their predicted consumptions are
    still counted and their shared entries still held -- by an object the
    batch has already abandoned (nothing references it once the stream
    ends). Reported, not asserted as zero."""

    context = probe.context
    return {
        "live_entries": context.live_entries,
        "refcount_identities": len(context._refcounts),  # noqa: SLF001
        "unforeseen_consumptions": context.stats.unforeseen_consumptions,
    }


# -- requirement 5: NDJSON first-byte laziness through the real route body --------------------


def test_first_ndjson_line_is_emitted_before_any_later_only_identity_is_computed() -> None:
    """The first line comes out of the real `/range-batch` streaming body
    while the second candidate's own identities -- in every family -- are
    predicted (refcount held) but not one of them has been computed. The
    full byte stream then equals memo OFF's, in request order."""

    first = _all_family_spec()
    later = _with(
        _all_family_spec(untouched=90, usd_tp=900.0),
        "anchor_stack",
        "slow",
        _ema(450),
    )
    later["components"]["blockers"][1] = {**_RSI_BLOCKER, "lookback": 25}
    later["components"]["trigger"] = {"component_id": "reclaim_anchor", "lookback": 3}
    later_exits = later["trade_management"]["exit_policy"]["always_on"]["exits"]
    later_exits[0] = _atr_exit("sl", "stop_loss", 2.5)
    assert later_exits[2]["component_id"] == "rsi_signal_exit"
    later_exits[2]["long_exit_above"] = 75.0
    payload = batch_payload([_variant("first", first), _variant("later", later)])
    model = StrategyRangeBatchRequestModel.model_validate(payload)

    with instrumented() as probe, recording_services(Recorder(), memo_enabled=True) as services:
        response = strategy_routes.evaluate_strategy_range_batch(model, services)

        async def drive() -> tuple[bytes, list[bytes], set[NodeSpec]]:
            chunks = response.body_iterator
            head = await chunks.__anext__()
            assert isinstance(head, bytes)
            later_only = set(probe.predicted[1]) - set(probe.predicted[0])
            covered = {family(identity) for identity in later_only}
            assert covered == set(FAMILIES), set(FAMILIES) - covered
            stats = probe.stats
            assert not any(identity in stats.compute_calls for identity in later_only)
            assert all(probe.context.refcount(identity) >= 1 for identity in later_only)
            tail = [chunk async for chunk in chunks]
            assert all(stats.compute_calls[identity] == 1 for identity in later_only)
            return head, tail, later_only  # type: ignore[return-value]

        head, tail, later_only = asyncio.run(drive())
    assert json.loads(head)["variant_id"] == "first"
    assert [json.loads(chunk)["variant_id"] for chunk in tail] == ["later"]
    off, _ = record_payload("lazy", payload, memo_enabled=False)
    assert [line.encode("utf-8") for line in off["ndjson"]["lines"]] == [head, *tail]
    assert later_only


# -- compute-call-count report ------------------------------------------------------------------

_REPORT_CASES = (
    "real_3d_grid_subset",
    "real_width_only_sweep",
    "real_untouched_only_sweep",
    "real_tpsl_only_sweep",
)


def test_zz_compute_call_count_report() -> None:
    """Consolidated per-family OFF / ON / unique compute counts on the real
    corpus (from the corpus gate above when it ran in this session)."""

    for case_name in _REPORT_CASES:
        if case_name not in CORPUS_COUNTS:
            golden = load_golden_case(case_name)
            payload = golden["request_payload"]
            _, _, off_probe = record(case_name, payload, memo_enabled=False)
            on, _, on_probe = record(case_name, payload, memo_enabled=True)
            families, kinds = assert_reuse_and_count(off_probe, on_probe, all_ok=_all_ok(on))
            CORPUS_COUNTS[case_name] = (len(payload["variants"]), families, kinds)
    for case_name in _REPORT_CASES:
        variants, families, kinds = CORPUS_COUNTS[case_name]
        print(f"\n=== {case_name}: {variants} candidates ===")
        print(format_table("per family:", families, raw=True))
        print(format_table("per node kind:", kinds, raw=False))
    for label, state in PROPAGATION_STATE.items():
        print(f"\nPROPAGATED STREAM {label}: {state}")
