"""Exit-rule / per-profile aggregate / profile-select memoization: memo OFF vs
memo ON (OpenSpec `batch-computation-reuse`, task 4.7).

Same gates as the earlier families (`test_indicator_memo.py`,
`test_strategy_node_memo.py`), for the exit family, enabled in three
sub-stages (rule nodes -> per-profile aggregates -> profile-select):

1. Correctness. The same evaluator code, recorded memo OFF and memo ON,
   reproduces the golden baseline bit-for-bit over the whole corpus.
2. Reuse, per exit node type. The underlying exit compute functions are
   spied on directly (independently of `EvaluationContext.stats`): memo OFF
   computes once per consumption; memo ON exactly once per unique identity.

Plus the two opposing identity proofs (exit nodes shared by candidates
that differ only in setups/triggers/entries; never shared when a rule,
the exit-profile context, the sides or a rule's placement differ), failure
memoization/replay at rule, aggregate and select level (D6), the
unresolvable-identity fallback, the pinned EMA source collision, D5
retention (nothing left after the batch) and lazy streaming.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

import parity.harness as harness_module
import strategy_engine.strategies.application.evaluate_range_batch as batch_module
import strategy_engine.strategies.ema_pullback.exits as exits_module
from parity.compare import compare_case, compare_encoded, format_report
from parity.corpus import (
    _atr_exit,
    _exits,
    _htf_context,
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
    market_fixture_meta,
    record_payload,
    recording_services,
)
from parity.snapshot import ArrayStore
from parity.test_parity_golden import CASE_NAMES, load_golden_case
from strategy_engine.adapters.http.models import StrategyRangeBatchRequestModel
from strategy_engine.domain.errors import InvalidRequestError
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.indicators.evaluation_context import EvaluationContext, EvaluationStats
from strategy_engine.strategies.ema_pullback.evaluation import (
    MemoizedStageIdentities,
    memoized_stage_consumptions,
    resolve_memoized_stages,
)
from strategy_engine.strategies.ema_pullback.exits import (
    ExitPolicyIdentity,
    exit_policy_consumptions,
)
from strategy_engine.strategies.ema_pullback.feature_plan import (
    build_feature_plan_from_canonical_spec,
)
from strategy_engine.strategies.ema_pullback.raw_spec_identity import resolve_exit_rule_groups

_BASE_TIMEFRAME = market_fixture_meta()["timeframe"]

# Numbers the proofs below observed, printed at the end of the module.
REUSE_PROOF: dict[str, Any] = {}

# -- exit node families ---------------------------------------------------------------

SIGNAL = "exit.signal"
DISTANCE = "exit.distance"
ANY_SIGNAL = "exit.aggregate.any_signal"
MIN = "exit.aggregate.min"  # min_ratio and min_distance (both `_min`)
READY = "exit.aggregate.ready"
SELECT_BOOL = "exit.select_bool"
SELECT_FLOAT = "exit.select_float"

# The exit families memoized so far (4.7 sub-stages are enabled in order).
MEMOIZED_EXIT_FAMILIES = (SIGNAL, DISTANCE, ANY_SIGNAL, MIN, READY, SELECT_BOOL, SELECT_FLOAT)


def exit_family(identity: NodeSpec) -> str | None:
    """Exit node type of a memoized identity (`None` for any non-exit
    family). An exit kind that is not (yet) memoized fails."""

    kind = identity.kind
    if not kind.startswith("exit."):
        return None
    if kind.startswith("exit.signal."):
        name = SIGNAL
    elif kind.startswith("exit.distance."):
        name = DISTANCE
    elif kind == ANY_SIGNAL:
        name = ANY_SIGNAL
    elif kind in ("exit.aggregate.min_ratio", "exit.aggregate.min_distance"):
        name = MIN
    elif kind == READY:
        name = READY
    elif kind in (SELECT_BOOL, SELECT_FLOAT):
        name = kind
    else:
        raise AssertionError(f"unexpected memoized exit node kind: {kind}")
    assert name in MEMOIZED_EXIT_FAMILIES, kind
    return name


def by_family(counts: Counter[NodeSpec]) -> dict[str, Counter[NodeSpec]]:
    grouped: dict[str, Counter[NodeSpec]] = defaultdict(Counter)
    for identity, count in counts.items():
        name = exit_family(identity)
        if name is not None:
            grouped[name][identity] += count
    return grouped


# -- instrumentation: independent spies on the raw exit compute functions -------------

# (global name in exits.py, node type of one call). Each is looked up by
# module-global name at its call site, so patching it counts every real
# execution, memoized or not.
_SPIED: tuple[tuple[str, str], ...] = (
    ("_signal_rule", SIGNAL),
    ("_false_signal", SIGNAL),
    ("_distance", DISTANCE),
    ("_or", ANY_SIGNAL),
    ("_min", MIN),
    ("_ready", READY),
    ("_select_bool", SELECT_BOOL),
    ("_select", SELECT_FLOAT),
)


@dataclass
class Instrumented:
    contexts: list[EvaluationContext] = field(default_factory=list)
    raw_calls: Counter[str] = field(default_factory=Counter)
    recorders: list[Recorder] = field(default_factory=list)

    @property
    def recorder(self) -> Recorder:
        assert len(self.recorders) == 1, len(self.recorders)
        return self.recorders[0]

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

    def spy(function: Callable[..., Any], node_type: str) -> Callable[..., Any]:
        @functools.wraps(function)
        def counted(*args: Any, **kwargs: Any) -> Any:
            probe.raw_calls[node_type] += 1
            return function(*args, **kwargs)

        return counted

    class CapturingRecorder(Recorder):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            probe.recorders.append(self)

    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(batch_module, "EvaluationContext", CapturingContext))
        stack.enter_context(_patched(harness_module, "Recorder", CapturingRecorder))
        for name, node_type in _SPIED:
            stack.enter_context(
                _patched(exits_module, name, spy(getattr(exits_module, name), node_type))
            )
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


# -- per-family reuse accounting --------------------------------------------------------


@dataclass(frozen=True)
class FamilyCounts:
    """One exit node type over one batch: real compute executions memo OFF /
    ON (spied), and the number of unique semantic identities."""

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
    for name in MEMOIZED_EXIT_FAMILIES:
        unique = set(off_computes[name])
        # Memo ON computes exactly the identities memo OFF computed, each once.
        assert set(on_computes[name]) == unique, name
        assert all(count == 1 for count in on_computes[name].values()), name
        # Raw executions beyond the memoized ones are direct (unmemoized)
        # computations for candidates whose exit identities could not be
        # resolved; exactly as many memo OFF as memo ON.
        direct_off = off.raw_calls[name] - off_computes[name].total()
        direct_on = on.raw_calls[name] - on_computes[name].total()
        assert direct_off == direct_on >= 0, (name, direct_off, direct_on)
        # Every consumption beyond the first per identity is a memo hit.
        assert on_hits[name].total() == off_computes[name].total() - len(unique), name
        report[name] = FamilyCounts(
            off=off.raw_calls[name], on=on.raw_calls[name], unique=len(unique)
        )
    for probe in (off, on):
        assert probe.stats.unforeseen_consumptions == 0
        # Nothing memoized outlives the batch (D5): no retained entry at all.
        assert probe.context.live_entries == 0
    return report


def format_counts(case_name: str, variants: int, report: dict[str, FamilyCounts]) -> str:
    lines = [f"\nREUSE-4.7 {case_name} ({variants} variants): exit node type: OFF -> ON (unique)"]
    for name, counts in report.items():
        lines.append(f"    {name:32s} {counts.off:5d} -> {counts.on:4d} ({counts.unique})")
    return "\n".join(lines)


# -- 4.7: memo OFF vs memo ON over the whole golden corpus ---------------------------------

_CASES_WITH_UNRESOLVABLE_EXITS = ("synthetic_failures_mixed", "synthetic_heterogeneous_shuffled")


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_exit_memo_off_and_on_match_golden_and_reuse_per_node_type(
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

    # (2) reuse, per exit node type.
    report = assert_family_reuse(off_probe, on_probe)
    if case_name not in _CASES_WITH_UNRESOLVABLE_EXITS:
        # Every candidate's exit identities resolved: every raw execution is
        # memoized.
        for name, counts in report.items():
            assert counts.on == counts.unique, (name, counts)
    if case_name.startswith("real_"):
        # Guard against a vacuous pass: real sweeps share their exit rules.
        assert report[DISTANCE].on < report[DISTANCE].off
    print(format_counts(case_name, len(payload["variants"]), report))


# -- exit specs used by the proofs below --------------------------------------------------

_RSI_EXIT = {
    "component_id": "rsi_signal_exit",
    "exit_kind": "signal",
    "instance_id": "rsi-exit",
    "rsi": {"timeframe": "base", "period": 14},
    "long_exit_above": 70.0,
    "short_exit_below": 30.0,
}


def _close_loss(confirm_bars: int = 2) -> dict[str, Any]:
    return {
        "component_id": "ema_close_loss_exit",
        "exit_kind": "signal",
        "instance_id": "close-loss",
        "ema": {"timeframe": "base", "period": 100},
        "confirm_bars": confirm_bars,
    }


_CROSS = {
    "component_id": "ema_cross_loss_exit",
    "exit_kind": "signal",
    "instance_id": "cross",
    "fast_ema": {"timeframe": "base", "period": 20},
    "slow_ema": {"timeframe": "base", "period": 50},
    "confirm_bars": 1,
}


def _usd(instance_id: str, kind: str, usd_distance: float) -> dict[str, Any]:
    return {
        "component_id": f"constant_usd_{kind}",
        "exit_kind": kind,
        "instance_id": instance_id,
        "usd_distance": usd_distance,
    }


def rich_exit_spec(
    *,
    sl_multiplier: float = 3.0,
    usd_tp: float = 1250.0,
    rsi_long_exit_above: float = 70.0,
    close_loss_confirm: int = 2,
    htf_timeframe: str = "1h",
    atr_tp_in_always_on: bool = True,
) -> dict[str, Any]:
    """Every exit node kind at once: ATR + USD distances, RSI / EMA-close /
    EMA-cross signals, always_on + per-profile rules, and profiles selected
    per bar by an HTF context (exit_profile_by_htf_state)."""

    atr_tp = _atr_exit("tp", "take_profit", 6.0)
    always_on = [
        _atr_exit("sl", "stop_loss", sl_multiplier),
        _RSI_EXIT | {"long_exit_above": rsi_long_exit_above},
        _close_loss(close_loss_confirm),
    ]
    if atr_tp_in_always_on:
        always_on.insert(1, atr_tp)
    spec = _exits(
        _with(base_spec(), "contexts", {"htf": _htf_context(htf_timeframe)}),
        always_on,
        aligned=[_usd("usd-tp", "take_profit", usd_tp)],
        countertrend=[_CROSS],
        neutral=[] if atr_tp_in_always_on else [atr_tp],
    )
    spec["trade_management"]["exit_policy"]["context_consumption"] = {
        "context_ref": "htf",
        "policy": {"policy_id": "exit_profile_by_htf_state"},
    }
    return spec


def _resolved(spec: dict[str, Any]) -> MemoizedStageIdentities:
    return resolve_memoized_stages(
        spec, build_feature_plan_from_canonical_spec(spec), base_timeframe=_BASE_TIMEFRAME
    )


def exit_nodes(identities: ExitPolicyIdentity) -> dict[str, NodeSpec]:
    """Every memoized exit node of one candidate, by a readable path."""

    nodes: dict[str, NodeSpec] = {}
    for instance_id, per_side in identities.signal_rules.items():
        for side, node in per_side.items():
            nodes[f"rule.{instance_id}.{side}"] = node
    for instance_id, node in identities.distance_rules.items():
        nodes[f"rule.{instance_id}"] = node
    for profile, aggregate in identities.by_profile.items():
        for name in (
            "signal_long",
            "signal_short",
            "stop_loss_ratio",
            "take_profit_ratio",
            "stop_loss_distance",
            "take_profit_distance",
            "ready",
        ):
            nodes[f"aggregate.{profile}.{name}"] = getattr(aggregate, name)
    for (name, side), node in identities.select.items():
        nodes[f"select.{name}.{side}"] = node
    return nodes


def upstream_closure(node: NodeSpec) -> set[NodeSpec]:
    seen: set[NodeSpec] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        for _role, dependency in current.upstream:
            items = (
                ()
                if dependency is None
                else dependency
                if isinstance(dependency, frozenset)
                else (dependency,)
            )
            for item in items:
                if item not in seen:
                    seen.add(item)
                    stack.append(item)
    return seen


def _differing(a: dict[str, NodeSpec], b: dict[str, NodeSpec]) -> set[str]:
    assert a.keys() == b.keys()
    return {path for path in a if a[path] != b[path]}


# -- proof 1: reuse when exit computation is truly independent of the difference -------


_INDEPENDENT_VARIANTS = {
    "base": rich_exit_spec(),
    "untouched-90": _with(rich_exit_spec(), "setups", 1, _untouched(lookback=90)),
    "width-2": _with(rich_exit_spec(), "setups", 0, _width(min_current_width_atr=2)),
    "reclaim-3": _with(
        rich_exit_spec(),
        "components",
        "trigger",
        {"component_id": "reclaim_anchor", "lookback": 3},
    ),
    "no-setups-counter-blocker": _with(
        _with(rich_exit_spec(), "setups", []),
        "components",
        "blockers",
        [{"component_id": "counter_candle_blocker", "instance_id": "counter-candle"}],
    ),
}


def test_exit_nodes_are_shared_by_candidates_differing_only_in_setups_triggers_entries() -> None:
    """Five candidates with the exact same exit rules, exit context and
    sides, differing only in setups / trigger / blockers (hence entries).
    Exit computation reads none of those, so every exit node has one
    identity for the whole batch and is computed exactly once."""

    # The compute signature itself: no setups, triggers or entries parameter.
    assert list(inspect.signature(exits_module.evaluate_exit_policy).parameters) == [
        "raw_spec",
        "frame",
        "plan",
        "consumption",
        "context",
        "identities",
    ]

    resolved = {name: _resolved(spec) for name, spec in _INDEPENDENT_VARIANTS.items()}
    exit_ids = {name: stages.exit_policy for name, stages in resolved.items()}
    assert all(item is not None for item in exit_ids.values())
    reference = exit_nodes(exit_ids["base"])  # type: ignore[arg-type]
    for name, identities in exit_ids.items():
        assert exit_nodes(identities) == reference, name  # type: ignore[arg-type]
    # ... while their setup / trigger / blocker identities genuinely differ.
    upstream_stages = {
        (stages.direction_blockers, stages.setups, stages.triggers) for stages in resolved.values()
    }
    assert len(upstream_stages) == len(_INDEPENDENT_VARIANTS)
    # No exit identity depends, even transitively, on a setup, trigger,
    # direction, blocker or entry-mask node.
    forbidden = ("setup.", "trigger.", "direction.", "blocker.", "mask.", "risk.", "entry.")
    for path, node in reference.items():
        kinds = {item.kind for item in upstream_closure(node)}
        assert not {k for k in kinds if k.startswith(forbidden)}, (path, kinds)

    payload = batch_payload([_variant(n, s) for n, s in _INDEPENDENT_VARIANTS.items()])
    off, off_store, off_probe = record("independent", payload, memo_enabled=False)
    on, on_store, on_probe = record("independent", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    assert all(c["outcome"]["disposition"] == "ok" for c in on["candidates"])
    report = assert_family_reuse(off_probe, on_probe)
    print(format_counts("independent_of_setups_triggers", len(_INDEPENDENT_VARIANTS), report))

    n = len(_INDEPENDENT_VARIANTS)
    per_root = Counter(exit_policy_consumptions(exit_ids["base"]))  # type: ignore[arg-type]
    unique = set(reference.values())
    assert set(per_root) == unique
    for node in unique:
        assert on_probe.stats.compute_calls[node] == 1, node
        assert on_probe.stats.hit_calls[node] == n * per_root[node] - 1, node
        assert off_probe.stats.compute_calls[node] == n * per_root[node], node
    for name, counts in report.items():
        assert counts.on == counts.unique and counts.off >= n * counts.on, (name, counts)
    # Candidate-level: entries differ, the exit policy is bit-identical.
    evaluations = [capture.evaluation for capture in on_probe.recorder.captures]
    assert len({repr(evaluation.entries) for evaluation in evaluations}) > 1
    assert all(evaluation.exit_policy == evaluations[0].exit_policy for evaluation in evaluations)
    # Nothing mutable is shared: each candidate gets its own dicts.
    assert evaluations[0].exit_policy.signal_by_profile_long is not (
        evaluations[1].exit_policy.signal_by_profile_long
    )
    REUSE_PROOF["independent"] = {
        "variants": n,
        "unique_exit_identities": len(unique),
        "consumptions_per_root": per_root.total(),
        "report": report,
    }


# -- proof 2: no reuse when exit computation actually depends on the difference --------


_DEPENDENT_VARIANTS = {
    "reference": rich_exit_spec(),
    "sl-atr-multiplier-2.5": rich_exit_spec(sl_multiplier=2.5),
    "aligned-usd-tp-900": rich_exit_spec(usd_tp=900.0),
    "rsi-long-exit-75": rich_exit_spec(rsi_long_exit_above=75.0),
    "close-loss-confirm-3": rich_exit_spec(close_loss_confirm=3),
    "exit-context-4h": rich_exit_spec(htf_timeframe="4h"),
    "long-only": _with(rich_exit_spec(), "trade_sides", ["long"]),
    "atr-tp-moved-to-neutral": rich_exit_spec(atr_tp_in_always_on=False),
}

_SIGNAL_SELECT = {"select.signal.long", "select.signal.short"}
_SL_SELECT = {f"select.stop_loss_{f}.{s}" for f in ("ratio", "distance") for s in ("long", "short")}
_TP_SELECT = {
    f"select.take_profit_{f}.{s}" for f in ("ratio", "distance") for s in ("long", "short")
}
_READY_SELECT = {"select.ready.long", "select.ready.short"}
_PROFILES = ("aligned", "countertrend", "neutral")


def _agg(names: tuple[str, ...], profiles: tuple[str, ...] = _PROFILES) -> set[str]:
    return {f"aggregate.{p}.{n}" for p in profiles for n in names}


# Exactly the exit nodes whose identity must differ from the reference's.
_EXPECTED_DIFFERENCES = {
    "sl-atr-multiplier-2.5": {"rule.sl"}
    | _agg(("stop_loss_ratio", "stop_loss_distance", "ready"))
    | _SL_SELECT
    | _READY_SELECT,
    "aligned-usd-tp-900": {"rule.usd-tp"}
    | _agg(("take_profit_ratio", "take_profit_distance", "ready"), ("aligned",))
    | _TP_SELECT
    | _READY_SELECT,
    "rsi-long-exit-75": {"rule.rsi-exit.long"} | _agg(("signal_long",)) | {"select.signal.long"},
    "close-loss-confirm-3": {"rule.close-loss.long", "rule.close-loss.short"}
    | _agg(("signal_long", "signal_short"))
    | _SIGNAL_SELECT,
    # Profile input only: every rule and per-profile aggregate is shared,
    # every select (which reads the per-bar profile) is not.
    "exit-context-4h": _SIGNAL_SELECT | _SL_SELECT | _TP_SELECT | _READY_SELECT,
    # Short side disabled: short signals become the constant all-False
    # signal and the short profile the constant neutral one.
    "long-only": {f"rule.{r}.short" for r in ("rsi-exit", "close-loss", "cross")}
    | _agg(("signal_short",))
    | {
        f"select.{f}.short"
        for f in (
            "signal",
            "stop_loss_ratio",
            "take_profit_ratio",
            "stop_loss_distance",
            "take_profit_distance",
            "ready",
        )
    },
    # Same rule, different placement: aligned/countertrend lose it,
    # neutral keeps it -> only aligned/countertrend TP aggregates change.
    "atr-tp-moved-to-neutral": _agg(
        ("take_profit_ratio", "take_profit_distance", "ready"), ("aligned", "countertrend")
    )
    | _TP_SELECT
    | _READY_SELECT,
}


def test_exit_nodes_are_not_shared_when_exit_rules_context_or_sides_differ() -> None:
    """Each candidate differs from the reference in exactly one input the
    exit computation reads (a rule parameter, the exit-profile context, the
    enabled sides, a rule's profile placement). Every node that reads it
    gets a distinct identity and is computed separately -- never served
    another candidate's result -- while every node that does not read it is
    still shared. The differing nodes' actual outputs are also checked to
    differ, so the distinction is not vacuous."""

    nodes = {
        name: exit_nodes(_resolved(spec).exit_policy)  # type: ignore[arg-type]
        for name, spec in _DEPENDENT_VARIANTS.items()
    }
    reference = nodes["reference"]
    for name, expected in _EXPECTED_DIFFERENCES.items():
        assert _differing(reference, nodes[name]) == expected, name

    payload = batch_payload([_variant(n, s) for n, s in _DEPENDENT_VARIANTS.items()])
    off, off_store, off_probe = record("dependent", payload, memo_enabled=False)
    on, on_store, on_probe = record("dependent", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    assert all(c["outcome"]["disposition"] == "ok" for c in on["candidates"])
    report = assert_family_reuse(off_probe, on_probe)
    print(format_counts("dependent_exit_inputs", len(_DEPENDENT_VARIANTS), report))

    stats = on_probe.stats
    for name, expected in _EXPECTED_DIFFERENCES.items():
        for path in expected:
            ours, theirs = nodes[name][path], reference[path]
            # Distinct identities, each computed on its own, exactly once.
            assert ours != theirs
            assert stats.compute_calls[ours] == 1 and stats.compute_calls[theirs] == 1
        for path in reference.keys() - expected:
            assert nodes[name][path] == reference[path]  # shared

    by_variant = {
        variant: capture.evaluation.exit_policy
        for variant, capture in zip(_DEPENDENT_VARIANTS, on_probe.recorder.captures, strict=True)
    }
    ref = by_variant["reference"]
    # The separately-computed results really are different computations.
    assert by_variant["sl-atr-multiplier-2.5"].stop_loss_ratio_long != ref.stop_loss_ratio_long
    assert by_variant["sl-atr-multiplier-2.5"].take_profit_ratio_long == ref.take_profit_ratio_long
    assert (
        by_variant["aligned-usd-tp-900"].take_profit_by_profile["aligned"]
        != ref.take_profit_by_profile["aligned"]
    )
    assert by_variant["rsi-long-exit-75"].signal_exit_long != ref.signal_exit_long
    assert by_variant["rsi-long-exit-75"].signal_exit_short == ref.signal_exit_short
    assert by_variant["close-loss-confirm-3"].signal_by_profile_long != ref.signal_by_profile_long
    assert by_variant["exit-context-4h"].profile_long != ref.profile_long
    assert by_variant["exit-context-4h"].stop_loss_by_profile == ref.stop_loss_by_profile
    assert by_variant["long-only"].profile_short == ("neutral",) * len(ref.profile_short)
    assert not any(by_variant["long-only"].signal_exit_short)
    assert (
        by_variant["atr-tp-moved-to-neutral"].take_profit_by_profile["aligned"]
        != ref.take_profit_by_profile["aligned"]
    )
    REUSE_PROOF["dependent"] = {
        name: len(expected) for name, expected in _EXPECTED_DIFFERENCES.items()
    } | {"report": report}


# -- D6: failure memoization and replay for the exit family ------------------------------


def _failing(name: str, should_fail: Callable[..., bool], exc: Callable[[], Exception]) -> Any:
    original = getattr(exits_module, name)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if should_fail(*args, **kwargs):
            raise exc()
        return original(*args, **kwargs)

    return wrapper


def _shared_and_divergent(spec_for: Callable[[float], dict[str, Any]], shared: float, other: float):
    """Candidates 0, 2, 3 share the exit value `shared` (differing from each
    other only in setups / trigger), candidate 1 uses `other`."""

    return batch_payload(
        [
            _variant("shared-a", spec_for(shared)),
            _variant("divergent", spec_for(other)),
            _variant("shared-b", _with(spec_for(shared), "setups", 1, _untouched(lookback=90))),
            _variant(
                "shared-c",
                _with(
                    spec_for(shared),
                    "components",
                    "trigger",
                    {"component_id": "reclaim_anchor", "lookback": 2},
                ),
            ),
        ]
    )


def _assert_replayed(
    off: dict[str, Any], on: dict[str, Any], stores: tuple[ArrayStore, ArrayStore], message: str
) -> list[dict[str, Any]]:
    assert not compare_case(off, on, *stores), format_report(compare_case(off, on, *stores))
    outcomes = [candidate["outcome"] for candidate in on["candidates"]]
    assert [o["disposition"] for o in outcomes] == ["caught", "ok", "caught", "caught"]
    for outcome in (outcomes[2], outcomes[3]):
        assert outcome["message"] == message
        assert outcome["category"] == outcomes[0]["category"]
        assert outcome["stage"] == outcomes[0]["stage"]
        assert outcome["details"] == outcomes[0]["details"]
    assert outcomes[0]["stage"][-1] == "evaluate_exit_policy"
    assert on["ndjson"]["termination"] == {"kind": "complete"}
    return outcomes


def test_failure_in_shared_exit_rule_node_is_memoized_and_replayed(monkeypatch: Any) -> None:
    """Leaf level: the constant-USD distance rule with usd_distance=1250
    fails. Three candidates share that rule identity: it fails once and the
    failure is replayed to the other two at the same point; the fourth
    candidate (usd_distance=900, a distinct identity) is unaffected."""

    monkeypatch.setattr(
        exits_module,
        "_distance",
        _failing(
            "_distance",
            lambda df, rule, plan: rule.get("usd_distance") == 1250.0,
            lambda: InvalidRequestError("injected exit rule failure", rule="usd", k=[1]),
        ),
    )
    payload = _shared_and_divergent(lambda v: rich_exit_spec(usd_tp=v), 1250.0, 900.0)
    off, off_store, off_probe = record("rule-failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("rule-failure", payload, memo_enabled=True)
    _assert_replayed(off, on, (off_store, on_store), "injected exit rule failure")

    failing = exit_nodes(_resolved(rich_exit_spec(usd_tp=1250.0)).exit_policy)["rule.usd-tp"]  # type: ignore[arg-type]
    assert failing.kind == "exit.distance.constant_usd"
    assert on_probe.stats.compute_calls[failing] == 1  # failed once ...
    assert on_probe.stats.hit_calls[failing] == 2  # ... replayed to the other two
    assert on_probe.stats.failure_replays == 2
    assert off_probe.stats.compute_calls[failing] == 3
    assert on_probe.raw_calls[DISTANCE] < off_probe.raw_calls[DISTANCE]
    assert on_probe.context.live_entries == 0 and off_probe.context.live_entries == 0
    REUSE_PROOF["failure_rule"] = (
        off_probe.stats.compute_calls[failing],
        on_probe.stats.compute_calls[failing],
        on_probe.stats.failure_replays,
    )


def test_failure_in_shared_exit_aggregate_is_memoized_and_replayed(monkeypatch: Any) -> None:
    """Aggregate level: the aligned-profile min-distance aggregate that
    contains the USD 1250 take-profit fails (its rule nodes succeed)."""

    monkeypatch.setattr(
        exits_module,
        "_min",
        _failing(
            "_min",
            lambda ratios, index: any(bool((s == 1250.0).all()) for s in ratios),
            lambda: InvalidRequestError("injected exit aggregate failure", level="aggregate"),
        ),
    )
    payload = _shared_and_divergent(lambda v: rich_exit_spec(usd_tp=v), 1250.0, 900.0)
    off, off_store, off_probe = record("aggregate-failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("aggregate-failure", payload, memo_enabled=True)
    _assert_replayed(off, on, (off_store, on_store), "injected exit aggregate failure")

    nodes = exit_nodes(_resolved(rich_exit_spec(usd_tp=1250.0)).exit_policy)  # type: ignore[arg-type]
    failing = nodes["aggregate.aligned.take_profit_distance"]
    assert failing.kind == "exit.aggregate.min_distance"
    stats = on_probe.stats
    assert stats.compute_calls[failing] == 1 and stats.hit_calls[failing] == 2
    assert stats.failure_replays == 2
    assert off_probe.stats.compute_calls[failing] == 3
    # The leaf rule under it succeeded and was itself shared.
    assert stats.compute_calls[nodes["rule.usd-tp"]] == 1
    assert stats.hit_calls[nodes["rule.usd-tp"]] == 2
    assert on_probe.context.live_entries == 0
    REUSE_PROOF["failure_aggregate"] = (
        off_probe.stats.compute_calls[failing],
        stats.compute_calls[failing],
        stats.failure_replays,
    )


def _usd_stop_spec(usd_distance: float) -> dict[str, Any]:
    return _exits(
        base_spec(),
        [_usd("usd-sl", "stop_loss", usd_distance), _atr_exit("tp", "take_profit", 6.0)],
    )


def test_failure_in_shared_exit_select_is_memoized_and_replayed(monkeypatch: Any) -> None:
    """Select level: the stop-loss-distance profile-select fails when every
    profile's stop distance is the USD 500 constant; aggregates below it
    succeed and are shared."""

    monkeypatch.setattr(
        exits_module,
        "_select",
        _failing(
            "_select",
            lambda profile, values, index: all(
                bool((values[name] == 500.0).all()) for name in _PROFILES
            ),
            lambda: InvalidRequestError("injected exit select failure", level="select"),
        ),
    )
    payload = _shared_and_divergent(_usd_stop_spec, 500.0, 700.0)
    off, off_store, off_probe = record("select-failure", payload, memo_enabled=False)
    on, on_store, on_probe = record("select-failure", payload, memo_enabled=True)
    _assert_replayed(off, on, (off_store, on_store), "injected exit select failure")

    nodes = exit_nodes(_resolved(_usd_stop_spec(500.0)).exit_policy)  # type: ignore[arg-type]
    failing = nodes["select.stop_loss_distance.long"]
    assert failing.kind == "exit.select_float"
    stats = on_probe.stats
    assert stats.compute_calls[failing] == 1 and stats.hit_calls[failing] == 2
    assert stats.failure_replays == 2
    assert off_probe.stats.compute_calls[failing] == 3
    assert stats.compute_calls[nodes["aggregate.neutral.stop_loss_distance"]] == 1
    assert on_probe.context.live_entries == 0
    REUSE_PROOF["failure_select"] = (
        off_probe.stats.compute_calls[failing],
        stats.compute_calls[failing],
        stats.failure_replays,
    )


def test_non_engine_error_in_exit_select_still_propagates_uncaught(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        exits_module,
        "_select_bool",
        _failing(
            "_select_bool",
            lambda *args, **kwargs: True,
            lambda: ValueError("injected non-engine exit failure"),
        ),
    )
    payload = batch_payload([_variant(f"v{i}", rich_exit_spec()) for i in range(3)])
    off, off_store, _ = record("propagate", payload, memo_enabled=False)
    on, on_store, _ = record("propagate", payload, memo_enabled=True)
    assert not compare_case(off, on, off_store, on_store)
    termination = on["ndjson"]["termination"]
    assert termination["kind"] == "propagated" and termination["after_lines"] == 0
    assert termination["category"] == "builtins.ValueError"


# -- fail-safe fallback: unresolvable exit identities compute directly ----------------------


def test_unresolvable_exit_rule_computes_directly_and_fails_exactly_as_before() -> None:
    invalid = _exits(
        base_spec(),
        [
            _atr_exit("sl-measurement", "stop_loss", 3.0),
            _atr_exit("tp-measurement", "take_profit", 6.0),
            {k: v for k, v in _RSI_EXIT.items() if k != "long_exit_above"},
        ],
    )
    stages = _resolved(invalid)
    assert stages.triggers is not None and stages.exit_policy is None
    assert not any(n.kind.startswith("exit.") for n in memoized_stage_consumptions(stages))

    payload = batch_payload(
        [_variant("ok-a", base_spec()), _variant("invalid", invalid), _variant("ok-b", base_spec())]
    )
    recorded = []
    for memo in (False, True):
        actual, store, probe = record("fallback", payload, memo_enabled=memo)
        recorded.append((actual, store))
        outcomes = [c["outcome"] for c in actual["candidates"]]
        assert [o["disposition"] for o in outcomes] == ["ok", "caught", "ok"]
        assert outcomes[1]["message"] == "rsi_signal_exit requires long_exit_above"
        assert outcomes[1]["stage"][-1] == "evaluate_exit_policy"
        memoized = by_family(probe.stats.compute_calls)
        # The invalid candidate's two distance rules ran directly (no
        # identity), before its RSI rule raised -- in both modes.
        assert probe.raw_calls[DISTANCE] - memoized[DISTANCE].total() == 2
        assert probe.stats.unforeseen_consumptions == 0
        assert probe.context.live_entries == 0
        if memo:
            # The two valid candidates still share every exit node.
            assert all(count == 1 for count in memoized[DISTANCE].values())
            assert memoized[DISTANCE].total() == 2
    (off, off_store), (on, on_store) = recorded
    assert not compare_case(off, on, off_store, on_store)


def test_duplicate_exit_instance_ids_are_never_memoized() -> None:
    """Instance-keyed identity maps are ambiguous for duplicate ids, so such
    a spec's exit nodes are never memoized (they compute directly)."""

    unique = _exits(base_spec(), [_usd("a", "stop_loss", 500.0), _usd("b", "take_profit", 900.0)])
    dup = _exits(base_spec(), [_usd("a", "stop_loss", 500.0), _usd("a", "take_profit", 900.0)])
    identities = _resolved(unique).exit_policy
    assert identities is not None
    assert exits_module._matches_rules(identities, resolve_exit_rule_groups(unique))
    assert not exits_module._matches_rules(identities, resolve_exit_rule_groups(dup))
    dup_stages = _resolved(dup)
    assert dup_stages.triggers is not None and dup_stages.exit_policy is None


# -- pinned feature-plan EMA source collision, with exit memo on ----------------------------

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


def test_pinned_source_collision_cases_unchanged_with_exit_memo(golden_store: ArrayStore) -> None:
    """`within-spec-exit-ema-open-vs-anchor-close` asks its close-loss exit
    for an *open* EMA(200); the legacy `_ema_id` collision resolves that onto
    the close-EMA(200) plan label (pinned, not fixed). The exit signal
    identity is built from what the label actually holds, so the memoized
    exit reads exactly the close EMA it read before, and every pinned
    candidate stays byte-identical to its golden."""

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
        signals = by_family(probe.stats.compute_calls)[SIGNAL]
        close_loss = [s for s in signals if s.kind == "exit.signal.ema_close_loss_exit"]
        assert len(close_loss) == 2  # long + short, one candidate
        for node in close_loss:
            ema = node.dependency("ema")
            assert isinstance(ema, NodeSpec)
            assert ema.param("source") == ("str", "close")  # collision pinned
            assert ema.param("period") == ("int", 200)
            assert probe.stats.compute_calls[node] == 1


# -- D5 retention: nothing lingers after the batch --------------------------------------------


def test_exit_entries_are_retained_only_while_a_consumer_remains() -> None:
    specs = [rich_exit_spec(), rich_exit_spec(usd_tp=900.0), rich_exit_spec(), rich_exit_spec()]
    payload = batch_payload([_variant(f"v{i}", s) for i, s in enumerate(specs)])
    request = StrategyRangeBatchRequestModel.model_validate(payload).to_domain()
    with instrumented() as probe, recording_services(Recorder(), memo_enabled=True) as services:
        retained_after: list[int] = []
        for outcome in services.evaluate_strategy_range_batch.execute(request):
            assert outcome.error is None
            context = probe.context
            memo = context._memo  # noqa: SLF001 - white-box retention check
            # Every retained entry still has a pending consumer.
            assert all(context.refcount(identity) > 0 for identity in memo)
            retained_after.append(sum(1 for identity in memo if identity.kind.startswith("exit.")))
        context = probe.context
    assert retained_after[0] > 0  # shared exit nodes kept for later roots ...
    assert retained_after[-1] == 0  # ... and released at their last consumer
    assert context.live_entries == 0
    assert context._refcounts == {}  # noqa: SLF001
    assert context.stats.peak_entries > 0 and context.stats.evictions > 0
    REUSE_PROOF["retention"] = {
        "exit_entries_after_each_root": retained_after,
        "peak_entries": context.stats.peak_entries,
        "evictions": context.stats.evictions,
        "live_entries_after_batch": context.live_entries,
    }


# -- NDJSON laziness: first root does not wait for later-only exit nodes ---------------------


def test_first_root_is_emitted_before_later_only_exit_nodes_are_computed() -> None:
    later = rich_exit_spec(usd_tp=900.0)
    payload = batch_payload([_variant("first", rich_exit_spec()), _variant("later", later)])
    request = StrategyRangeBatchRequestModel.model_validate(payload).to_domain()
    later_nodes = exit_nodes(_resolved(later).exit_policy)  # type: ignore[arg-type]
    first_nodes = exit_nodes(_resolved(rich_exit_spec()).exit_policy)  # type: ignore[arg-type]
    later_only = [n for n in set(later_nodes.values()) if n not in set(first_nodes.values())]
    assert later_only and later_nodes["rule.usd-tp"] in later_only
    with instrumented() as probe, recording_services(Recorder(), memo_enabled=True) as services:
        outcomes = services.evaluate_strategy_range_batch.execute(request)
        first = next(outcomes)
        assert first.variant_id == "first" and first.error is None
        stats = probe.stats
        assert all(probe.context.refcount(node) >= 1 for node in later_only)
        assert not any(node in stats.compute_calls for node in later_only)
        second = next(outcomes)
        assert second.variant_id == "later" and second.error is None
        assert all(stats.compute_calls[node] == 1 for node in later_only)
        assert list(outcomes) == []


def test_zz_print_reuse_proof_numbers() -> None:
    for name, value in REUSE_PROOF.items():
        print(f"\nPROOF-4.7 {name}: {value}")
