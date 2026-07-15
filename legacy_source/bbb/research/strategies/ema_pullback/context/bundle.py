"""Build strategy-level context outputs once per run."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from research.strategies.ema_pullback.components.context import HtfContextMasks, htf_context
from research.strategies.ema_pullback.features.plan import FeaturePlan
from research.strategies.ema_pullback.spec import ContextProviderSpec, EmaPullbackStrategySpec


@dataclass(frozen=True)
class ContextOutput:
    context_ref: str
    provider: ContextProviderSpec
    masks: HtfContextMasks

    def state_series(self) -> pd.Series:
        return self.masks.state_series()


@dataclass(frozen=True)
class ContextBundle:
    outputs: tuple[ContextOutput, ...]

    @classmethod
    def build(
        cls,
        spec: EmaPullbackStrategySpec,
        df: pd.DataFrame,
        plan: FeaturePlan,
    ) -> ContextBundle:
        outputs: list[ContextOutput] = []
        for context_ref, provider in spec.contexts:
            columns = plan.htf_context_columns_for(context_ref)
            col_names = (columns["fast"], columns["anchor"], columns["slow"])
            if not all(col in df.columns for col in col_names):
                masks = HtfContextMasks(
                    up=pd.Series(False, index=df.index, dtype=bool),
                    down=pd.Series(False, index=df.index, dtype=bool),
                    neutral=pd.Series(True, index=df.index, dtype=bool),
                )
            else:
                masks = htf_context(
                    df,
                    fast_col=columns["fast"],
                    anchor_col=columns["anchor"],
                    slow_col=columns["slow"],
                )
            outputs.append(
                ContextOutput(
                    context_ref=context_ref,
                    provider=provider,
                    masks=masks,
                )
            )
        return cls(outputs=tuple(outputs))

    def get(self, context_ref: str) -> ContextOutput:
        for output in self.outputs:
            if output.context_ref == context_ref:
                return output
        raise KeyError(f"unknown context_ref {context_ref!r}")

    def has(self, context_ref: str) -> bool:
        return any(output.context_ref == context_ref for output in self.outputs)
