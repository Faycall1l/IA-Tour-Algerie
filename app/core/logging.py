import logging
from collections.abc import Callable
from typing import Any

import structlog
from structlog.processors import JSONRenderer, TimeStamper, format_exc_info

Processor = Callable[
    [Any, str, structlog.types.EventDict],
    structlog.types.EventDict | str | bytes | bytearray | tuple[Any, ...],
]


def setup_logging(debug: bool = False) -> None:
    timestamper = TimeStamper(fmt="iso")

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        format_exc_info,
        structlog.dev.set_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG if debug else logging.INFO,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or __name__)
