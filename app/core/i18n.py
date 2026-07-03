import gettext
from pathlib import Path

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "locales"
SUPPORTED_LOCALES = {"ar", "fr", "en", "tz"}
DEFAULT_LOCALE = "fr"

_translations: dict[str, gettext.GNUTranslations] = {}


def load_translations():
    for lang in SUPPORTED_LOCALES:
        try:
            t = gettext.translation("messages", localedir=str(LOCALES_DIR), languages=[lang])
            _translations[lang] = t
        except FileNotFoundError:
            pass


def gettext_best(lang: str, message: str) -> str:
    t = _translations.get(lang)
    if t is not None:
        return t.gettext(message)
    return message


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
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        lang = detect_language(request)
        request.state.lang = lang
        response = await call_next(request)
        return response
