import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


class InMemoryTTLCache:
    """Process-local result cache with a fixed, non-sliding expiry."""

    def __init__(
        self,
        ttl: timedelta = timedelta(hours=5),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl
        self._now = now or (lambda: datetime.now(UTC))
        self._values: dict[str, tuple[object, datetime]] = {}

    def get(self, key: str) -> object | None:
        normalized_key = key.upper()
        cached = self._values.get(normalized_key)
        if cached is None:
            logger.debug("tool_cache.miss key=%s", normalized_key)
            return None

        value, expires_at = cached
        if self._now() >= expires_at:
            del self._values[normalized_key]
            logger.debug("tool_cache.expired key=%s", normalized_key)
            return None

        return value

    def set(self, key: str, value: object) -> None:
        self._values[key.upper()] = (value, self._now() + self._ttl)
        logger.debug(
            "tool_cache.set key=%s ttl_seconds=%s", key, self._ttl.total_seconds()
        )
