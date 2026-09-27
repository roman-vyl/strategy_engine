"""Batch-scoped evaluation context: shared range arrays + identity memo.

OpenSpec change `batch-computation-reuse`, group 4 (design.md D1, D2, D4,
D5, D6). One `EvaluationContext` exists per range evaluation request: a
`/range-batch` call builds one with N roots (`EvaluateStrategyRangeBatch`),
a single-spec `/range` (or `/range/diagnostics`) request builds one with
exactly one root (`EvaluateStrategyRange`) -- one mechanism, differing only
in root count. It owns:

- the shared range-invariant `MarketArrays` bundle of that request (group 2);
- a memo `NodeSpec identity -> immutable result`, where a "result" is
  either the node's computed value or an immutable `FailureRecord`;
- per-identity reference counts, computed from every root's resolved
  identities *before* streaming begins (`plan_roots`), used to evict a
  memoized entry the moment its last expected consumer has read it.

The context is scoped to exactly one market range (`scope`): it is built
from one `MarketFrame`, and callers check they are evaluating that exact
frame (object identity) before consulting it, so memo entries from
different ranges can never meet -- which is why identities themselves
never repeat the market/range identity (design.md D2).

Memoized node families: indicators (4.4); direction / blocker /
setup-component / trigger nodes plus the mask compositions those stages
build (4.6); exit-rule, per-profile aggregate and profile-select nodes
(4.7).

D1: this is scoped memoization *inside* the existing pipeline, not an
executor. The evaluator keeps its execution order and control flow; each
memo-enabled node call site resolves its identity at the point it would
compute today and goes through `memoized(identity, compute)`. A hit
returns the memoized value (or replays the memoized failure) at that same
point; a miss runs the same `compute` the evaluator always ran.

Memo toggle (design.md D3's A/B tool): `memo_enabled=False` keeps every
line of this code path -- identity resolution, refcount bookkeeping,
compute counting -- but never stores an entry, so every consumption
computes. Memo OFF vs memo ON therefore differ only in whether results are
reused, never in which code runs. Production never turns it off (no wiring
or request field sets it); it is kept as the regression-testing knob the
`tests/parity` memo-OFF vs memo-ON gates rely on.

D5 refcounts count *consumptions* (a root that reads one identity twice,
e.g. two timeframe-aliased plan columns, contributes 2). A root's
consumptions that never happen (the root failed earlier, or its pre-pass
over-predicted) are released when that root ends, so an entry is never
retained past its last possible consumer. A consumption the pre-pass did
not predict is still served (hit or compute) but never extends retention.
If eviction ever happened too early the only effect would be a
recomputation -- the pre-change behaviour -- never a wrong value.

D6 failures: a memo-retained compute failure is stored as a
`FailureRecord` (category, args, and for `StrategyEngineError` its code /
message / details / status), never the exception object or traceback.
A later consumer of that identity gets a freshly built exception of the
same category and payload raised at its own consumption point, so the
existing catch boundaries (the batch's `StrategyEngineError`-only catch;
everything else propagates) see exactly what they saw before. A failure
that cannot be faithfully rebuilt is not memoized at all (the next
consumer recomputes and fails on its own, as before).
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from strategy_engine.domain.errors import EvaluationInvariantError, StrategyEngineError
from strategy_engine.domain.market import MarketFrame, MarketStream
from strategy_engine.domain.node_identity import NodeSpec
from strategy_engine.domain.ranges import TimeRange
from strategy_engine.indicators.market_arrays import MarketArrays

T = TypeVar("T")


# -- failure memoization (design.md D6) ----------------------------------------


def _observable(exc: BaseException) -> tuple[object, ...]:
    """Everything about a failure the pre-change evaluator makes observable
    (category, str, args, and the engine error payload the batch serializes)
    -- never object or traceback identity."""

    if isinstance(exc, StrategyEngineError):
        engine: tuple[object, ...] = (exc.code, exc.message, exc.details, exc.status_code)
    else:
        engine = ()
    return (type(exc), str(exc), exc.args, engine)


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """Immutable representation of one node failure.

    `category` is the exception type; propagation behaviour follows from it
    exactly as today (`caught_by_engine_boundary`). `args` and
    `engine_payload` are private deep copies, and every `replay()` hands
    out new deep copies, so no mutable state is shared between the
    candidates that observe the failure.
    """

    category: type[Exception]
    args: tuple[Any, ...]
    engine_payload: tuple[str, str, dict[str, Any], int] | None

    @property
    def caught_by_engine_boundary(self) -> bool:
        return issubclass(self.category, StrategyEngineError)

    @classmethod
    def capture(cls, exc: Exception) -> FailureRecord | None:
        """A record that replays `exc` observably identically, or `None`
        when that cannot be guaranteed (then the failure is not memoized)."""

        try:
            engine_payload = None
            if isinstance(exc, StrategyEngineError):
                engine_payload = (
                    exc.code,
                    exc.message,
                    copy.deepcopy(exc.details),
                    exc.status_code,
                )
            record = cls(type(exc), copy.deepcopy(exc.args), engine_payload)
            if _observable(record.replay()) != _observable(exc):
                return None
        except Exception:
            return None
        return record

    def replay(self) -> Exception:
        """A new exception object, observably identical to the original."""

        args = copy.deepcopy(self.args)
        if self.engine_payload is None:
            return self.category(*args)
        code, message, details, status_code = self.engine_payload
        # Engine error subclasses have their own __init__ signatures; build
        # the instance with the original args and set the dataclass payload
        # directly, exactly as the subclass __init__ ultimately did.
        exc = self.category.__new__(self.category, *args)
        StrategyEngineError.__init__(exc, code, message, copy.deepcopy(details), status_code)  # type: ignore[arg-type]
        return exc


@dataclass(frozen=True, slots=True)
class _Value:
    value: Any


@dataclass(frozen=True, slots=True)
class _Failure:
    record: FailureRecord


# -- statistics ----------------------------------------------------------------------


@dataclass(slots=True)
class EvaluationStats:
    """Reuse accounting for one context: cheap per-consumption counters that
    the `tests/parity` gates assert on (each identity computed exactly once
    with memo on, hits = consumptions - 1, zero `unforeseen_consumptions` on
    a successful evaluation -- the D5 pre-pass completeness invariant) and
    that stay available for runtime inspection."""

    compute_calls: Counter[NodeSpec] = field(default_factory=Counter)
    hit_calls: Counter[NodeSpec] = field(default_factory=Counter)
    hits: int = 0
    failure_replays: int = 0
    evictions: int = 0
    unforeseen_consumptions: int = 0
    peak_entries: int = 0

    @property
    def total_compute_calls(self) -> int:
        return sum(self.compute_calls.values())


# -- the context -------------------------------------------------------------------------


class EvaluationContext:
    """Per-request evaluation context, one or N roots (see module docstring)."""

    def __init__(
        self,
        market_frame: MarketFrame,
        market_arrays: MarketArrays | None = None,
        *,
        memo_enabled: bool = True,
    ) -> None:
        if market_arrays is None:
            market_arrays = MarketArrays.from_market_frame(market_frame)
        elif not market_arrays.is_derived_from(market_frame):
            raise EvaluationInvariantError(
                "shared market arrays were not derived from the context's market frame"
            )
        self._market_frame = market_frame
        self._market_arrays = market_arrays
        self._memo_enabled = memo_enabled
        self._memo: dict[NodeSpec, _Value | _Failure] = {}
        self._refcounts: dict[NodeSpec, int] = {}
        self._pending: list[Counter[NodeSpec]] | None = None
        self._active_root: int | None = None
        self.stats = EvaluationStats()

    # -- scope ---------------------------------------------------------------

    @property
    def market_frame(self) -> MarketFrame:
        return self._market_frame

    @property
    def market_arrays(self) -> MarketArrays:
        return self._market_arrays

    @property
    def scope(self) -> tuple[MarketStream, TimeRange, str]:
        """The market/range identity every memo entry is implicitly scoped
        under (design.md D2)."""

        frame = self._market_frame
        return (frame.market, frame.requested_range, frame.market_data_hash)

    def is_for(self, market_frame: MarketFrame) -> bool:
        """True only for the exact frame this context was built for
        (object identity -- never a content comparison)."""

        return market_frame is self._market_frame

    @property
    def memo_enabled(self) -> bool:
        return self._memo_enabled

    @property
    def live_entries(self) -> int:
        return len(self._memo)

    def refcount(self, identity: NodeSpec) -> int:
        return self._refcounts.get(identity, 0)

    # -- refcounts (design.md D5) ---------------------------------------------

    def plan_roots(self, roots: Iterable[Iterable[NodeSpec]]) -> None:
        """Record every root's expected identity consumptions, in root
        order, before the first root is evaluated."""

        if self._pending is not None or self._active_root is not None:
            raise EvaluationInvariantError("evaluation context roots were already planned")
        pending = [Counter(identities) for identities in roots]
        for counts in pending:
            for identity, count in counts.items():
                self._refcounts[identity] = self._refcounts.get(identity, 0) + count
        self._pending = pending

    @contextmanager
    def root(self, index: int) -> Iterator[None]:
        """Scope one root's evaluation. On exit (normal or raising) every
        consumption that root was expected to make but did not is released,
        so nothing is retained for a consumer that will never come. Never
        suppresses or replaces an exception raised inside."""

        if self._active_root is not None:
            raise EvaluationInvariantError("evaluation context roots cannot nest")
        self._active_root = index
        try:
            yield
        finally:
            self._active_root = None
            pending = self._pending
            if pending is not None and 0 <= index < len(pending):
                leftover = pending[index]
                for identity, count in leftover.items():
                    self._release(identity, count)
                leftover.clear()

    def _release(self, identity: NodeSpec, count: int) -> int:
        remaining = self._refcounts.get(identity, 0) - count
        if remaining > 0:
            self._refcounts[identity] = remaining
            return remaining
        self._refcounts.pop(identity, None)
        if self._memo.pop(identity, None) is not None:
            self.stats.evictions += 1
        return 0

    def _consume(self, identity: NodeSpec) -> int:
        """Account one consumption of `identity` by the active root and
        return how many further consumptions remain in the batch."""

        pending = self._pending
        root = self._active_root
        if pending is not None and root is not None and 0 <= root < len(pending):
            counts = pending[root]
            if counts.get(identity, 0) > 0:
                counts[identity] -= 1
                if not counts[identity]:
                    del counts[identity]
                remaining = self._refcounts.get(identity, 0) - 1
                if remaining > 0:
                    self._refcounts[identity] = remaining
                else:
                    self._refcounts.pop(identity, None)
                return max(remaining, 0)
        self.stats.unforeseen_consumptions += 1
        return self._refcounts.get(identity, 0)

    # -- memoized computation --------------------------------------------------

    def memoized(self, identity: NodeSpec, compute: Callable[[], T]) -> T:
        """The result of the node `identity` at this consumption point.

        Hit: the memoized value, or a replay of the memoized failure.
        Miss: `compute()` -- the node's unchanged computation -- whose value
        or failure is retained only if memo is enabled and a later
        consumption of this identity is still expected.
        """

        entry = self._memo.get(identity)
        remaining = self._consume(identity)
        if entry is not None:
            if remaining == 0:
                del self._memo[identity]
                self.stats.evictions += 1
            self.stats.hits += 1
            self.stats.hit_calls[identity] += 1
            if isinstance(entry, _Failure):
                self.stats.failure_replays += 1
                raise entry.record.replay()
            return entry.value  # type: ignore[no-any-return]

        retain = self._memo_enabled and remaining > 0
        self.stats.compute_calls[identity] += 1
        try:
            value = compute()
        except Exception as exc:
            if retain:
                record = FailureRecord.capture(exc)
                if record is not None:
                    self._store(identity, _Failure(record))
            raise
        if retain:
            self._store(identity, _Value(value))
        return value

    def _store(self, identity: NodeSpec, entry: _Value | _Failure) -> None:
        self._memo[identity] = entry
        if len(self._memo) > self.stats.peak_entries:
            self.stats.peak_entries = len(self._memo)


def compute_through[R](
    context: EvaluationContext | None,
    identity: NodeSpec | None,
    compute: Callable[[], R],
) -> R:
    """`context.memoized(identity, compute)` when both a context and a
    resolved identity are available; otherwise `compute()` directly, exactly
    as before memoization existed. A node whose identity could not be
    resolved is therefore never memoized -- its unchanged computation runs
    and raises (or not) on its own, at its own point."""

    if context is None or identity is None:
        return compute()
    return context.memoized(identity, compute)
