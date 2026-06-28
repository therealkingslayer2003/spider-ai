import logging
import sys

from rich.logging import RichHandler

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    level = logging.DEBUG if settings.app_debug else logging.INFO
    handler: logging.Handler

    if settings.app_pretty_logs:
        handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=False,
        )
        log_format = "%(message)s"
    else:
        handler = logging.StreamHandler(sys.stdout)
        log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[handler],
        force=True,
    )
