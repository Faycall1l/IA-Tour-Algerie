from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

SUPPORTED_LOCALES = {"ar", "fr", "en", "tam"}
DEFAULT_LOCALE = "fr"


def detect_language(request: Request) -> str:
    lang = request.query_params.get("lang")
    if lang in SUPPORTED_LOCALES:
        return lang
    header = request.headers.get("Accept-Language", "")
    for part in header.split(","):
        code = part.strip().split(";")[0].split("-")[0]
        if code in SUPPORTED_LOCALES:
            return code
    return DEFAULT_LOCALE


class LocaleMiddleware(BaseHTTPMiddleware):
    """Set ``request.state.lang`` for downstream locale-aware handlers."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request.state.lang = detect_language(request)
        response = await call_next(request)
        response.headers.setdefault("Content-Language", request.state.lang)
        return response
