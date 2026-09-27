"""Direction / blocker / trigger / setup-component memoization: memo OFF vs
memo ON (OpenSpec `batch-computation-reuse`, task 4.6).

Same two gates as the indicator stage (`test_indicator_memo.py`), for the
strategy-node families:

1. Correctness. The same evaluator code, recorded memo OFF and memo ON,
   reproduces the golden baseline bit-for-bit over the whole corpus
   (including the pinned EMA source-collision cases, whose direction and
   context-gated setups are now memoized too).
2. Reuse, per node type. The underlying compute functions are spied on
   directly (independently of `EvaluationContext.stats`) and counted per
   node type: direction, each blocker kind, trigger, the width setup's
   side-free prefix and its threshold suffix, untouched-anchor, bounce
   counter, and the gated / AND-composition masks. Memo OFF computes once
   per consumption; memo ON computes exactly once per unique identity.

Plus the composition-granularity proof (setups A and C shared while B
diverges), the width prefix/suffix split, failure memoization/replay (D6),
and lazy streaming, for these families.
"""

from __future__ import annotations

import contextlib
import functools
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

import strategy_engine.strategies.application.evaluate_range_batch as batch_module
import strategy_engine.strategies.ema_pullback.direction_blockers as direction_module
import strategy_engine.strategies.ema_pullback.setups as setups_module
import strategy_engine.strategies.ema_pullback.triggers as triggers_module
from parity.compare import compare_case, compare_encoded, format_report
from parity.corpus import _untouched, _variant, _width, _with, base_spec
from parity.harness import GOLDEN_DIR, Recorder, batch_payload, record_payload, recording_services
from parity.snapshot import ArrayStore
from parity.test_parity_golden import CASE_NAMES, load_golden_case
from strategy_engine.adapters.http.models import StrategyRangeBatchRequestModel
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.evaluation_context import EvaluationContext, EvaluationStats
from strategy_engine.strategies.ema_pullback.evaluation import resolve_memoized_stages
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)

# -- node families ------------------------------------------------------------------

DIRECTION = "direction"
TRIGGER = "trigger"
WIDTH_PREFIX = "width_prefix"
WIDTH_SUFFIX = "width_suffix"
UNTOUCHED = "untouched_anchor"
BOUNCE = "bounce_counter"
GATED = "mask.gated"
AND_ALL = "mask.all"


def family(identity: NodeSpec) -> str | None:
    """Node type of a memoized identity (`None` for indicators and for the
    exit-rule/aggregate/select family, which `test_exit_node_memo.py`
    accounts for). Any other kind fails."""

    kind = identity.kind
    if kind.startswith(("indicator.", "exit.")):
        return None
    if kind.startswith("direction."):
        return DIRECTION
    if kind.startswith("blocker."):
        return kind  # one family per blocker kind
    if kind == "setup.anchor_stack_width.prefix":
        return WIDTH_PREFIX
    if kind == "setup.anchor_stack_width_setup":
        return WIDTH_SUFFIX
    if kind == "setup.untouched_anchor_setup":
        return UNTOUCHED
    if kind == "setup.ema_bounce_counter_setup":
        return BOUNCE
    if kind.startswith("trigger."):
        return TRIGGER
    if kind in (GATED, AND_ALL):
        return kind
    raise AssertionError(f"unexpected memoized node kind: {kind}")


def by_family(counts: Counter[NodeSpec]) -> dict[str, Counter[NodeSpec]]:
    grouped: dict[str, Counter[NodeSpec]] = defaultdict(Counter)
    for identity, count in counts.items():
        name = family(identity)
        if name is not None:
            grouped[name][identity] += count
    return grouped


# -- instrumentation: independent spies on the raw compute functions ---------------------

# (module, global name, node type of one call). Every one of these is looked
# up by module-global name at its call site, so patching the name counts
# every real execution, memoized or not.
_SPIED: tuple[tuple[Any, str, Callable[..., str]], ...] = (
    (direction_module, "_direction", lambda *a, **k: DIRECTION),
    (direction_module, "_blocker_intrinsic", lambda cid, *a, **k: f"blocker.{cid}"),
    (direction_module, "_apply_gate", lambda *a, **k: GATED),
    (direction_module, "_combine_blocker_masks", lambda *a, **k: AND_ALL),
    (direction_module, "and_pair", lambda *a, **k: AND_ALL),
    (setups_module, "_anchor_stack_width_prefix", lambda *a, **k: WIDTH_PREFIX),
    (setups_module, "_anchor_stack_width", lambda *a, **k: WIDTH_SUFFIX),
    (setups_module, "_untouched_anchor", lambda *a, **k: UNTOUCHED),
    (setups_module, "_ema_bounce_counter", lambda *a, **k: BOUNCE),
    (setups_module, "_apply_gate", lambda *a, **k: GATED),
    (setups_module, "_combine_setup_masks", lambda *a, **k: AND_ALL),
    (setups_module, "and_pair", lambda *a, **k: AND_ALL),
    (triggers_module, "_touch_anchor", lambda *a, **k: TRIGGER),
    (triggers_module, "_rolling_reclaim", lambda *a, **k: TRIGGER),
    (triggers_module, "and_pair", lambda *a, **k: AND_ALL),
)


@dataclass
class Instrumented:
    contexts: list[EvaluationContext] = field(default_factory=list)
    raw_calls: Counter[str] = field(default_factory=Counter)

    @property
    def context(self) -> EvaluationContext:
        assert len(self.contexts) == 1, len(self.contexts)
        return self.contexts[0]

    @property
    def stats(self) -> EvaluationStats:
        return self.context.stats


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

    def spy(function: Callable[..., Any], classify: Callable[..., str]) -> Callable[..., Any]:
        @functools.wraps(function)
        def counted(*args: Any, **kwargs: Any) -> Any:
            probe.raw_calls[classify(*args, **kwargs)] += 1
            return function(*args, **kwargs)

        return counted

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(batch_module, "EvaluationContext", CapturingContext))
        for module, name, classify in _SPIED:
            stack.enter_context(_patched(module, name, spy(getattr(module, name), classify)))
        yield probe


def record(
    name: str, payload: dict[str, Any], *, memo_enabled: bool
) -> tuple[dict[str, Any], ArrayStore, Instrumented]:
    with instrumented() as probe:
        actual, store = record_payload(name, payload, memo_enabled=memo_enabled)
    return actual, store, probe


@pytest.fixture(scope="module")
def golden_store() -> ArrayStore:
    return ArrayStore.load(GOLDEN_DIR / "arrays.npz", verify=True)


# -- per-family reuse accounting -----------------------------------------------------------


@dataclass(frozen=True)
class FamilyCounts:
    """One node type over one batch: real compute executions memo OFF / ON
    (spied), and the number of unique semantic identities."""

    off: int
    on: int
    unique: int


def assert_family_reuse(off: Instrumented, on: Instrumented) -> dict[str, FamilyCounts]:
    """The per-family reuse contract, checked from two independent sources
    (context accounting and raw compute spies)."""

    off_computes = by_family(off.stats.compute_calls)
    on_computes = by_family(on.stats.compute_calls)
    on_hits = by_family(on.stats.hit_calls)
    assert off.stats.hits == 0 and off.stats.peak_entries == 0

    report: dict[str, FamilyCounts] = {}
    for name in sorted(set(off_computes) | set(on_computes) | set(off.raw_calls)):
        unique = set(off_computes[name])
        # Memo ON computes exactly the identities memo OFF computed, each once.
        assert set(on_computes[name]) == unique, name
        assert all(count == 1 for count in on_computes[name].values()), name
        # Raw executions beyond the memoized ones are direct (unmemoized)
        # computations of nodes whose identity could not be resolved -- a
        # candidate that fails in that very stage. There are exactly as many
        # memo OFF as memo ON.
        direct_off = off.raw_calls[name] - off_computes[name].total()
        direct_on = on.raw_calls[name] - on_computes[name].total()
        assert direct_off == direct_on >= 0, (name, direct_off, direct_on)
        if name == WIDTH_PREFIX:
            # The prefix is consumed from inside its suffix's computation, so
            # memo ON consumes it once per *computed* suffix: each unique
            # suffix identity, never a served one.
            assert on_computes[name].total() + on_hits[name].total() == len(
                on_computes[WIDTH_SUFFIX]
            )
        else:
            # Every consumption beyond the first per identity is a memo hit.
            assert on_hits[name].total() == off_computes[name].total() - len(unique), name
        report[name] = FamilyCounts(
            off=off.raw_calls[name], on=on.raw_calls[name], unique=len(unique)
        )
    for probe in (off, on):
        assert probe.stats.unforeseen_consumptions == 0
        assert probe.context.live_entries == 0
    return report


def format_counts(case_name: str, variants: int, report: dict[str, FamilyCounts]) -> str:
    lines = [f"\nREUSE-4.6 {case_name} ({variants} variants): node type: OFF -> ON (unique)"]
    for name, counts in report.items():
        lines.append(f"    {name:40s} {counts.off:5d} -> {counts.on:4d} ({counts.unique})")
    return "\n".join(lines)


# -- 4.6: memo OFF vs memo ON over the whole golden corpus ------------------------------

_CASES_WITH_UNRESOLVABLE_STAGES = ("synthetic_failures_mixed", "synthetic_heterogeneous_shuffled")


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_strategy_node_memo_off_and_on_match_golden_and_reuse_per_node_type(
    case_name: str, golden_store: ArrayStore
) -> None:
    golden = load_golden_case(case_name)
    payload = golden["request_payload"]

    off, off_store, off_probe = record(case_name, payload, memo_enabled=False)
    on, on_store, on_probe = record(case_name, payload, memo_enabled=True)

    # (1) correctness: both modes bit-identical to the golden baseline.
    for label, actual, store in (("OFF", off, off_store), ("ON", on, on_store)):
        mismatches = compare_case(golden, actual, golden_store, store)
        assert not mismatches, f"memo {label}:\n" + format_report(mismatches)
    on_vs_off = compare_case(off, on, off_store, on_store)
    assert not on_vs_off, "memo ON vs OFF:\n" + format_report(on_vs_off)

    if golden["ndjson"]["termination"]["kind"] == "request_failed":
        assert off_probe.contexts == [] and on_probe.contexts == []
        assert not off_probe.raw_calls and not on_probe.raw_calls
        return

    # (2) reuse, per node type.
    report = assert_family_reuse(off_probe, on_probe)
    if case_name not in _CASES_WITH_UNRESOLVABLE_STAGES:
        # Every candidate's stages resolved: every raw execution is memoized.
        for name, counts in report.items():
            assert counts.on == counts.unique, (name, counts)
    if case_name.startswith("real_"):
        # Guard against a vacuous pass: real sweeps share direction/trigger.
        assert report[DIRECTION].on == report[DIRECTION].unique == 2
        assert report[DIRECTION].off == 2 * len(payload["variants"])
        assert report[TRIGGER].on == 2 < report[TRIGGER].off
        if WIDTH_PREFIX in report:  # the untouched-only sweep has no width setup
            assert report[WIDTH_PREFIX].on < report[WIDTH_PREFIX].off
    print(format_counts(case_name, len(payload["variants"]), report))


# -- width prefix / suffix granularity ------------------------------------------------------


def _record_off_on(payload: dict[str, Any]) -> tuple[Instrumented, Instrumented]:
    off, off_store, off_probe = record("synthetic", payload, memo_enabled=False)
    on, on_store, on_probe = record("synthetic", payload, memo_enabled=True)
    mismatches = compare_case(off, on, off_store, on_store)
    assert not mismatches, format_report(mismatches)
    assert all(c["outcome"]["disposition"] == "ok" for c in on["candidates"])
    return off_probe, on_probe


def test_width_prefix_is_shared_across_thresholds_while_the_suffix_is_not() -> None:
    """Five width setups: four differ only in their thresholds (same
    fast/slow/atr/width_lookback_bars), one also differs in its lookback.
    The side-free prefix collapses to 2 computations; the threshold suffix
    to 5 (one per distinct threshold/lookback combination, side-free)."""

    base = base_spec()
    widths = [
        _width(min_current_width_atr=1),
        _width(min_current_width_atr=1.5),
        _width(min_current_width_atr=2),
        _width(min_current_width_atr=2, min_recent_width_atr=5.0),
        _width(min_current_width_atr=1, width_lookback_bars=60),
    ]
    payload = batch_payload(
        [_variant(f"width-{i}", _with(base, "setups", [w])) for i, w in enumerate(widths)]
    )
    off, on = _record_off_on(payload)
    report = assert_family_reuse(off, on)
    print(format_counts("width_prefix_suffix", len(widths), report))

    consumptions = len(widths) * 2  # two sides each
    assert report[WIDTH_SUFFIX] == FamilyCounts(off=consumptions, on=5, unique=5)
    assert report[WIDTH_PREFIX] == FamilyCounts(off=consumptions, on=2, unique=2)
    prefixes = {
        identity.param("width_lookback_bars"): identity
        for identity in on.stats.compute_calls
        if family(identity) == WIDTH_PREFIX
    }
    assert sorted(prefixes) == [("int", 60), ("int", 80)]
    # The four threshold-only variants' suffixes all hang off the one prefix.
    suffixes = [i for i in on.stats.compute_calls if family(i) == WIDTH_SUFFIX]
    shared_prefix = prefixes[("int", 80)]
    assert sum(1 for s in suffixes if s.dependency("prefix") == shared_prefix) == 4
    # The prefix was computed by the first suffix and served (memo hit) to
    # the three other threshold variants' suffixes.
    assert on.stats.hit_calls[shared_prefix] == 3


# -- composition granularity: setups A and C shared, B diverging --------------------------


_BOUNCE = {
    "component_id": "ema_bounce_counter_setup",
    "instance_id": "bounce1",
    "params": {"max_bounces": 2, "touch_lookback_bars": 20},
}


def _abc_spec(*, width: dict[str, Any], untouched: dict[str, Any]) -> dict[str, Any]:
    """Setups A = width (side-free), B = untouched anchor, C = bounce."""

    return _with(base_spec(), "setups", [width, untouched, _BOUNCE])


def test_setups_a_and_c_shared_while_b_diverges() -> None:
    """Four candidates share setups A (width) and C (bounce counter) and
    differ only in setup B (untouched-anchor lookback). A and C are computed
    once per identity for the whole batch, B once per candidate and side;
    so is every composition that depends on B, while direction, blockers
    and trigger (upstream of / beside B) are computed once."""

    lookbacks = (50, 60, 70, 80)
    payload = batch_payload(
        [
            _variant(f"b-lookback-{n}", _abc_spec(width=_width(), untouched=_untouched(lookback=n)))
            for n in lookbacks
        ]
    )
    off, on = _record_off_on(payload)
    report = assert_family_reuse(off, on)
    print(format_counts("shares_A_C_diverges_B", len(lookbacks), report))

    per_side = len(lookbacks) * 2
    # A (width): side-free -> 1 suffix, 1 prefix for the whole batch.
    assert report[WIDTH_SUFFIX] == FamilyCounts(off=per_side, on=1, unique=1)
    assert report[WIDTH_PREFIX] == FamilyCounts(off=per_side, on=1, unique=1)
    # C (bounce counter): reads the side -> 1 per side.
    assert report[BOUNCE] == FamilyCounts(off=per_side, on=2, unique=2)
    # B (untouched anchor): every candidate/side is a distinct identity.
    assert report[UNTOUCHED] == FamilyCounts(off=per_side, on=per_side, unique=per_side)
    # Upstream/beside B: shared.
    assert report[DIRECTION] == FamilyCounts(off=per_side, on=2, unique=2)
    assert report["blocker.no_blockers"] == FamilyCounts(off=per_side, on=1, unique=1)
    assert report[TRIGGER] == FamilyCounts(off=per_side, on=2, unique=2)

    # Compositions: gated finals of A/C are shared, B's are not; setups_ok,
    # pre_trigger and pre_risk depend on B and so are one per candidate/side,
    # while blockers_ok and pre_setup (upstream of B) are shared.
    computed = [i for i in on.stats.compute_calls if family(i) == GATED]
    gated_by_setup = Counter(i.dependency("mask").kind for i in computed)  # type: ignore[union-attr]
    assert gated_by_setup["setup.anchor_stack_width_setup"] == 1
    assert gated_by_setup["setup.ema_bounce_counter_setup"] == 2
    assert gated_by_setup["setup.untouched_anchor_setup"] == per_side
    and_all = [i for i in on.stats.compute_calls if family(i) == AND_ALL]
    # Shared: 1 blockers_ok (the ungated no_blockers mask is side-free, so
    # both sides' blockers_ok are one identity) + 2 pre_setup (direction
    # reads the side). B-dependent: per_side x (setups_ok, pre_trigger,
    # pre_risk).
    assert len(and_all) == 1 + 2 + 3 * per_side


def test_setup_a_diverges_while_b_and_c_are_shared() -> None:
    """Mirror image: only setup A's width threshold differs. B and C collapse
    to one identity per side; A's suffix is one per threshold; A's prefix is
    one for the batch (thresholds are suffix-only)."""

    thresholds = (1, 1.5, 2, 3)
    payload = batch_payload(
        [
            _variant(
                f"a-threshold-{t}",
                _abc_spec(width=_width(min_current_width_atr=t), untouched=_untouched()),
            )
            for t in thresholds
        ]
    )
    off, on = _record_off_on(payload)
    report = assert_family_reuse(off, on)
    print(format_counts("shares_B_C_diverges_A", len(thresholds), report))

    per_side = len(thresholds) * 2
    assert report[WIDTH_SUFFIX] == FamilyCounts(off=per_side, on=4, unique=4)
    assert report[WIDTH_PREFIX] == FamilyCounts(off=per_side, on=1, unique=1)
    assert report[UNTOUCHED] == FamilyCounts(off=per_side, on=2, unique=2)
    assert report[BOUNCE] == FamilyCounts(off=per_side, on=2, unique=2)


# -- pinned feature-plan EMA source collision, with direction/setup memo on -------------------

_PINNED = (
    "anchor-ema200-close",
    "anchor-ema200-open",
    "anchor-ema200-high",
    "anchor-ema200-close-again",
    "within-spec-context-open-vs-stack-close",
    "within-spec-exit-ema-open-vs-anchor-close",
)


def _by_variant(record_: dict[str, Any]) -> dict[str, tuple[dict[str, Any], str | None]]:
    lines = record_["ndjson"]["lines"]
    return {
        c["variant_id"]: (c, lines[c["variant_index"]] if c["variant_index"] < len(lines) else None)
        for c in record_["candidates"]
    }


def test_pinned_source_collision_cases_unchanged_with_direction_and_setup_memo(
    golden_store: ArrayStore,
) -> None:
    """The legacy `_ema_id` source collision flows into direction (anchor
    stack EMAs) and into the context gating a setup. Direction/setup memo is
    keyed by the source-aware identity of what each candidate actually
    reads, so every pinned candidate stays byte-identical to its golden, the
    close-anchored stack's direction is shared only by the candidates that
    really read the close EMA(200) (including both within-spec collision
    candidates, whose open requests the plan still resolves onto the close
    label), and the open/high-anchored candidates get their own."""

    case_name = "probe_source_distinct_same_period"
    golden = load_golden_case(case_name)
    for memo in (False, True):
        actual, store, probe = record(case_name, golden["request_payload"], memo_enabled=memo)
        assert not compare_case(golden, actual, golden_store, store)
        golden_by, actual_by = _by_variant(golden), _by_variant(actual)
        for variant_id in _PINNED:
            golden_candidate, golden_line = golden_by[variant_id]
            actual_candidate, actual_line = actual_by[variant_id]
            assert actual_line is not None and actual_line.encode() == golden_line.encode()
            for section in ("plan", "frame", "evaluation", "projection"):
                assert not compare_encoded(
                    section,
                    golden_candidate[section],
                    actual_candidate[section],
                    golden_store,
                    store,
                ), (memo, variant_id, section)

        directions = by_family(probe.stats.compute_calls)[DIRECTION]
        anchor_sources = Counter(
            d.dependency("anchor").param("source")[1]  # type: ignore[union-attr]
            for d in directions
        )
        # 3 distinct anchors x 2 sides.
        assert anchor_sources == Counter({"close": 2, "open": 2, "high": 2})
        close_directions = [
            d
            for d in directions
            if d.dependency("anchor").param("source") == ("str", "close")  # type: ignore[union-attr]
        ]
        if memo:
            assert all(directions[d] == 1 for d in directions)
        else:
            # close, close-again and both within-spec candidates read the
            # close EMA(200) anchor: 4 consumers per side.
            assert [directions[d] for d in close_directions] == [4, 4]


# -- D6: failure memoization and replay for these families ------------------------------------


def _failing(
    module: Any, name: str, should_fail: Callable[..., bool], exc: Callable[[], Exception]
) -> Callable[..., Any]:
    original = getattr(module, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if should_fail(*args, **kwargs):
            raise exc()
        return original(*args, **kwargs)

    return wrapper


def _untouched_payload() -> dict[str, Any]:
    base = base_spec()  # untouched lookback 70
    other = _with(base, "setups", 1, _untouched(lookback=90))
    return batch_payload(
        [
            _variant("uses-70-a", base),
            _variant("no-70", other),
            _variant("uses-70-b", base),
            _variant("uses-70-c", _with(base, "setups", 0, _width(min_current_width_atr=2))),
        ]
    )


def test_engine_error_in_shared_setup_node_is_memoized_and_replayed(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        setups_module,
        "_untouched_anchor",
        _failing(
            setups_module,
            "_untouched_anchor",
            lambda frame, anchor_id, params, side: int(params.get("lookback", 50)) == 70,
            lambda: InvalidRequestError("injected setup failure", node="untouched", k=[1]),
        ),
    )
    payload = _untouched_payload()
    off, off_store, off_probe = record("failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("failure", payload, memo_enabled=True)

    mismatches = compare_case(off, on, off_store, on_store)
    assert not mismatches, format_report(mismatches)
    outcomes = [candidate["outcome"] for candidate in on["candidates"]]
    assert [o["disposition"] for o in outcomes] == ["caught", "ok", "caught", "caught"]
    for outcome in (outcomes[2], outcomes[3]):
        assert outcome["message"] == "injected setup failure"
        assert outcome["stage"] == outcomes[0]["stage"]
        assert outcome["details"] == outcomes[0]["details"]
    assert "evaluate_setups" in outcomes[0]["stage"]

    failing = [
        i
        for i in on_probe.stats.compute_calls
        if family(i) == UNTOUCHED and i.param("lookback") == ("int", 70)
    ]
    assert len(failing) == 1 and failing[0].side == "long"  # long fails first
    assert on_probe.stats.compute_calls[failing[0]] == 1  # failed once ...
    assert on_probe.stats.failure_replays == 2  # ... replayed to the other two
    assert off_probe.stats.compute_calls[failing[0]] == 3
    assert on_probe.raw_calls[UNTOUCHED] < off_probe.raw_calls[UNTOUCHED]
    assert on_probe.context.live_entries == 0


def test_failure_in_shared_width_prefix_replays_through_a_different_suffix(
    monkeypatch: Any,
) -> None:
    """The prefix fails inside the first suffix's computation. A later
    candidate with a different threshold (distinct suffix identity, same
    prefix identity) computes its suffix and gets the prefix failure
    replayed from inside it -- same category, payload and stage."""

    monkeypatch.setattr(
        setups_module,
        "_anchor_stack_width_prefix",
        _failing(
            setups_module,
            "_anchor_stack_width_prefix",
            lambda fast, slow, atr, lookback: lookback == 80,
            lambda: InvalidRequestError("injected prefix failure"),
        ),
    )
    base = base_spec()
    payload = batch_payload(
        [
            _variant("t1", base),
            _variant("t2", _with(base, "setups", 0, _width(min_current_width_atr=2))),
            _variant("t1-again", base),
        ]
    )
    off, off_store, off_probe = record("prefix-failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("prefix-failure", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    outcomes = [candidate["outcome"] for candidate in on["candidates"]]
    assert [o["disposition"] for o in outcomes] == ["caught"] * 3
    assert len({(o["message"], str(o["stage"])) for o in outcomes}) == 1

    stats = on_probe.stats
    prefix = next(i for i in stats.compute_calls if family(i) == WIDTH_PREFIX)
    suffixes = [i for i in stats.compute_calls if family(i) == WIDTH_SUFFIX]
    assert stats.compute_calls[prefix] == 1 and on_probe.raw_calls[WIDTH_PREFIX] == 1
    assert stats.hit_calls[prefix] == 1  # replayed inside t2's own suffix
    assert len(suffixes) == 2 and all(stats.compute_calls[s] == 1 for s in suffixes)
    # t1-again: its suffix failure (memoized when t1 failed) is replayed.
    assert stats.failure_replays == 2
    assert off_probe.raw_calls[WIDTH_PREFIX] == 3
    assert on_probe.context.live_entries == 0


def test_engine_error_in_shared_direction_is_replayed_for_every_candidate(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        direction_module,
        "_direction",
        _failing(
            direction_module,
            "_direction",
            lambda raw_spec, frame, plan, side: side == "short",
            lambda: InvalidRequestError("injected direction failure", side="short"),
        ),
    )
    payload = batch_payload([_variant(f"v{i}", base_spec()) for i in range(3)])
    off, off_store, off_probe = record("direction-failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("direction-failure", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    outcomes = [candidate["outcome"] for candidate in on["candidates"]]
    assert [o["disposition"] for o in outcomes] == ["caught"] * 3
    assert "evaluate_direction_and_blockers" in outcomes[0]["stage"]
    # long direction computed once (and served twice), short failed once
    # and was replayed twice.
    assert on_probe.raw_calls[DIRECTION] == 2 and off_probe.raw_calls[DIRECTION] == 6
    assert on_probe.stats.failure_replays == 2


def test_non_engine_error_in_trigger_still_propagates_uncaught(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        triggers_module,
        "_touch_anchor",
        _failing(
            triggers_module,
            "_touch_anchor",
            lambda *args, **kwargs: True,
            lambda: ValueError("injected non-engine trigger failure"),
        ),
    )
    payload = batch_payload([_variant(f"v{i}", base_spec()) for i in range(3)])
    off, off_store, _ = record("propagate", payload, memo_enabled=False)
    on, on_store, _ = record("propagate", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 0
    assert termination["category"] == "builtins.ValueError"


# -- memoized traces are never shared mutable state ----------------------------------------


def test_memoized_traces_are_private_per_candidate() -> None:
    payload = batch_payload([_variant(f"v{i}", base_spec()) for i in range(2)])
    request = StrategyRangeBatchRequestModel.model_validate(payload).to_domain()
    recorder = Recorder()
    with recording_services(recorder, memo_enabled=True) as services:
        outcomes = list(services.evaluate_strategy_range_batch.execute(request))
    assert all(outcome.error is None for outcome in outcomes)
    first, second = (capture.evaluation for capture in recorder.captures)
    pairs = [
        (first.direction_blockers[0].direction, second.direction_blockers[0].direction),
        (first.setups[0].setups[0], second.setups[0].setups[0]),
        (first.setups[0].setups[1], second.setups[0].setups[1]),
        (first.triggers[0].trigger, second.triggers[0].trigger),
    ]
    for a, b in pairs:
        assert a.trace == b.trace and a.trace is not b.trace
        # The underlying immutable arrays are shared, not recomputed.
        key = next(iter(a.trace))
        assert a.trace[key] is b.trace[key]


# -- NDJSON laziness: first root does not wait for later-only strategy nodes ------------------


def test_first_root_is_emitted_before_later_only_strategy_nodes_are_computed() -> None:
    base = base_spec()
    later = _with(base, "setups", 1, _untouched(lookback=90))
    payload = batch_payload([_variant("first", base), _variant("later", later)])
    request = StrategyRangeBatchRequestModel.model_validate(payload).to_domain()
    later_stages = resolve_memoized_stages(
        later,
        build_feature_plan_from_canonical_spec(later),
        base_timeframe=request.market.base_timeframe,
    )
    assert later_stages.setups is not None
    later_only = [side.setups[1].local for side in later_stages.setups]
    assert [family(identity) for identity in later_only] == [UNTOUCHED, UNTOUCHED]
    with instrumented() as probe, recording_services(Recorder(), memo_enabled=True) as services:
        outcomes = services.evaluate_strategy_range_batch.execute(request)
        first = next(outcomes)
        assert first.variant_id == "first" and first.error is None
        stats = probe.stats
        # The pre-pass already knows the later root needs them ...
        assert all(probe.context.refcount(identity) == 1 for identity in later_only)
        # ... but none was computed before the first line was emitted.
        assert not any(identity in stats.compute_calls for identity in later_only)
        assert probe.raw_calls[UNTOUCHED] == 2  # only the first root's (both sides)
        second = next(outcomes)
        assert second.variant_id == "later" and second.error is None
        assert all(stats.compute_calls[identity] == 1 for identity in later_only)
        assert list(outcomes) == []
