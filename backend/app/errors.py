"""One error envelope for the whole API.

Upstream failures keep the upstream's own message. A payer saying "member not
found" is information the user needs verbatim — collapsing it into a generic
500 destroys the only useful part of the response.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, message: str, *, status: int = 400, code: str = "error", detail=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.detail = detail


class Unconfigured(ApiError):
    """A capability was asked for whose credentials are not present."""

    def __init__(self, what: str, how: str):
        super().__init__(
            f"{what} is not configured.",
            status=503,
            code="unconfigured",
            detail={"capability": what, "resolution": how},
        )


class UpstreamError(ApiError):
    def __init__(self, upstream: str, message: str, *, status: int = 502, detail=None):
        super().__init__(message, status=status, code="upstream_error",
                         detail={"upstream": upstream, **(detail or {})})


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
    )


async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": str(exc), "detail": None}},
    )
