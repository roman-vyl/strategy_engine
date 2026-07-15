"""FastAPI dependency accessors."""

from __future__ import annotations

from fastapi import Request

from strategy_engine.service.wiring import ApplicationServices


def services(request: Request) -> ApplicationServices:
    return request.app.state.services
