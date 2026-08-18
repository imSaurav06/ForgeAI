import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from shared.logging.logger import logger

T = TypeVar("T")


class RetryPolicy:
    """Configurable exponential backoff retry policy for transient HTTP operations."""

    IDEMPOTENT_METHODS: set[str] = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 0.1,
        backoff_factor: float = 2.0,
        retryable_status_codes: set[int] | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.retryable_status_codes = retryable_status_codes or {502, 503, 504}

    def is_retryable_method(self, method: str) -> bool:
        """Check if HTTP method is idempotent and eligible for retries."""
        return method.upper() in self.IDEMPOTENT_METHODS

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        is_retryable_exception: Callable[[Exception], bool],
        method: str = "GET",
    ) -> T:
        """
        Execute async function with exponential backoff retries.
        """
        if not self.is_retryable_method(method):
            return await func()

        delay = self.initial_delay
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return await func()
            except Exception as err:
                last_exception = err
                if not is_retryable_exception(err) or attempt == self.max_retries:
                    raise err

                logger.warning(
                    f"Retry attempt {attempt}/{self.max_retries} failed ({err}). Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                delay *= self.backoff_factor

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry policy failed unexpectedly without exception")
