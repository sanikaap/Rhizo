import logging
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("rhizo")


class RhizoError(Exception):
    status: int = 500
    code: str = "INTERNAL"
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(self, message: str = "Internal error") -> None:
        super().__init__(message)
        self.message = message


class BadRequest(RhizoError):
    status, code = 400, "BAD_REQUEST"


class NotFound(RhizoError):
    status, code = 404, "NOT_FOUND"


class Unauthenticated(RhizoError):
    status, code = 401, "UNAUTHENTICATED"
    headers: ClassVar[dict[str, str] | None] = {"WWW-Authenticate": "Bearer"}


class Conflict(RhizoError):
    status, code = 409, "CONFLICT"


class Busy(RhizoError):
    status, code = 409, "BUSY"


class UpstreamError(RhizoError):
    status, code = 503, "UPSTREAM"


def error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}, headers=headers
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(RhizoError)
    async def _rhizo(_: Request, e: RhizoError) -> JSONResponse:
        if e.status >= 500:
            log.warning("%s: %s", e.code, e.message)
        return error_response(e.status, e.code, e.message, e.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
        msg = f"{where}: {first.get('msg', 'invalid input')}" if where else first.get("msg", "invalid input")
        return error_response(400, "BAD_REQUEST", msg)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {400: "BAD_REQUEST", 404: "NOT_FOUND", 409: "BUSY", 503: "UPSTREAM"}.get(
            e.status_code, "INTERNAL"
        )
        return error_response(e.status_code, code, str(e.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return error_response(500, "INTERNAL", "Internal error")
