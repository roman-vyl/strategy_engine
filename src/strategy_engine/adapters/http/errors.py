"""Stable error envelopes and FastAPI exception handlers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from strategy_engine.domain.errors import StrategyEngineError


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid.uuid4())


def _payload(
    *,
    error: str,
    message: str,
    details: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    return {
        "error": error,
        "message": message,
        "details": details,
        "request_id": request_id,
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StrategyEngineError)
    async def handle_application_error(
        request: Request,
        exc: StrategyEngineError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(
                error=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                error="invalid_request",
                message="request validation failed",
                details={"errors": exc.errors()},
                request_id=_request_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_internal_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_payload(
                error="internal_error",
                message="internal server error",
                details={},
                request_id=_request_id(request),
            ),
        )
