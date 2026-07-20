"""FastAPI dependency accessors."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from strategy_engine.service.wiring import ApplicationServices


def services(request: Request) -> ApplicationServices:
    return cast(ApplicationServices, request.app.state.services)
