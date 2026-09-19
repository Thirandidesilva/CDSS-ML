"""ApiError -> {"code","response"} envelope. FastAPI's native validation-error shape is
left untouched (see routers) to preserve the already-tested 422-names-the-field contract.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .codes import HTTP_STATUS, BusinessCode


class ApiError(Exception):
    # Routers do `raise ApiError(BusinessCode.DOG_NOT_FOUND, "dog not found")` and never
    # build a JSONResponse themselves — the handler below turns this into one envelope
    # shape everywhere, so every error looks the same to API clients.
    def __init__(self, code: BusinessCode, message: str):
        self.code = code
        self.message = message
        self.status_code = HTTP_STATUS.get(code, 200)  # defaults to 200 for business codes
        super().__init__(message)


def envelope(code: BusinessCode, response: list) -> dict:
    # The one place that assembles {"code", "response"} — every success path (routers)
    # and every error path (below) both go through this, so the shape can't drift.
    return {"code": code.value, "response": response}


def register_exception_handlers(app: FastAPI) -> None:
    # Called once from create_app(). @app.exception_handler intercepts a raised
    # exception anywhere in a route and converts it to a response instead of a 500.
    @app.exception_handler(ApiError)
    def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(exc.code, [{"message": exc.message}]),
        )

    # Catch-all safety net: anything NOT raised as an ApiError (a bug, a DB error, etc.)
    # still comes back as a valid envelope instead of FastAPI's default plain-text 500.
    @app.exception_handler(Exception)
    def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=envelope(BusinessCode.SERVER_ERROR, [{"message": "internal server error"}]),
        )
