import structlog
import logging
import uuid

from structlog.processors import JSONRenderer, TimeStamper, format_exc_info


def setup_logging(debug: bool = False) -> None:
    timestamper = TimeStamper(fmt="iso")

    processors = [
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
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = JSONRenderer()

    processors.append(renderer)

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
