"""EMA stack episode HTTP routes (OpenSpec `ema-stack-episode-query-v1`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from strategy_engine.adapters.http.dependencies import services
from strategy_engine.adapters.http.models import EpisodeHistoryRequestModel
from strategy_engine.domain.errors import UnsupportedCapabilityError
from strategy_engine.service.wiring import ApplicationServices

router = APIRouter(prefix="/v1", tags=["ema-stack-episodes"])


@router.post("/ema-stack-episodes/history")
def episode_history(
    request: EpisodeHistoryRequestModel,
    app: ApplicationServices = Depends(services),
) -> dict[str, object]:
    """Read-only: pages of whole finished episodes of one side, newest
    first, and the current episode. Not a strategy evaluation."""

    if app.query_episode_history is None:
        raise UnsupportedCapabilityError("ema_stack_episode_history")
    return app.query_episode_history.execute(request.to_domain())
