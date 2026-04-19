import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    level = logging.DEBUG if settings.app_debug else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
