import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except AppError as exc:
            if exc.status_code >= 500:
                logger.exception("Server error: %s", exc)
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            )
