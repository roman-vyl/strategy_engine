"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from strategy_engine.adapters.http.errors import install_exception_handlers
from strategy_engine.adapters.http.health import router as health_router
from strategy_engine.adapters.http.indicator_routes import router as indicator_router
from strategy_engine.adapters.http.strategy_routes import router as strategy_router
from strategy_engine.service.settings import Settings
from strategy_engine.service.wiring import ApplicationServices, build_services


def create_app(
    *,
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_services = services or build_services(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = resolved_services
        yield
        resolved_services.close()

    app = FastAPI(
        title="Strategy Engine",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(indicator_router)
    app.include_router(strategy_router)
    return app
