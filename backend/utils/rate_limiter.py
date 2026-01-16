"""Rate limiting utility for spacing out form submissions."""

import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple rate limiter for async operations.

    Ensures a minimum interval between operations to avoid
    overwhelming municipal servers or triggering rate limits.
    """

    def __init__(self, min_interval: float = 30.0):
        """
        Initialize rate limiter.

        Args:
            min_interval: Minimum seconds between operations
        """
        self.min_interval = timedelta(seconds=min_interval)
        self.last_operation: datetime = None

    async def wait(self):
        """Wait until the minimum interval has passed since last operation."""
        if self.last_operation is None:
            self.last_operation = datetime.now()
            return

        elapsed = datetime.now() - self.last_operation

        if elapsed < self.min_interval:
            wait_time = (self.min_interval - elapsed).total_seconds()
            logger.debug(f"Rate limiting: waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        self.last_operation = datetime.now()

    def reset(self):
        """Reset the rate limiter."""
        self.last_operation = None
