import time
from enum import Enum

from shared.exceptions.handlers import ServiceUnavailableException
from shared.logging.logger import logger


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Per-service Circuit Breaker managing transition between CLOSED, OPEN, and HALF_OPEN.
    Prevents cascading failures by tripping OPEN when consecutive failure count exceeds threshold.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0

    def allow_request(self) -> bool:
        """Check if request is allowed through circuit breaker."""
        now = time.time()

        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"CircuitBreaker for '{self.service_name}' entering HALF_OPEN trial state")
                self.state = CircuitState.HALF_OPEN
                return True
            else:
                return False
        return True

    def record_success(self) -> None:
        """Record successful call, resetting failure counts and closing circuit."""
        if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            logger.info(f"CircuitBreaker for '{self.service_name}' recovered to CLOSED state")
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record failed call, tripping circuit OPEN if threshold reached."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(
                    f"CircuitBreaker for '{self.service_name}' tripped OPEN after {self.failure_count} consecutive failures"
                )
            self.state = CircuitState.OPEN


class CircuitBreakerRegistry:
    """Registry maintaining CircuitBreaker instances for all microservices."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 10.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, service_name: str) -> CircuitBreaker:
        """Retrieve or instantiate CircuitBreaker for service."""
        name = service_name.lower()
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(
                service_name=name,
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
            )
        return self.breakers[name]

    def verify_request_allowed(self, service_name: str) -> None:
        """Verify circuit breaker state or raise ServiceUnavailableException."""
        breaker = self.get_breaker(service_name)
        if not breaker.allow_request():
            raise ServiceUnavailableException(
                message=f"Downstream service '{service_name}' circuit breaker is OPEN due to recent failures",
                details={
                    "service": service_name,
                    "circuit_state": breaker.state.value,
                    "recovery_timeout_sec": breaker.recovery_timeout,
                },
            )


_breaker_registry_instance: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Accessor for global CircuitBreakerRegistry."""
    global _breaker_registry_instance
    if _breaker_registry_instance is None:
        _breaker_registry_instance = CircuitBreakerRegistry()
    return _breaker_registry_instance
