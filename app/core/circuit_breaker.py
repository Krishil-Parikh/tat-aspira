"""
Circuit Breaker Pattern for Redis Fail-Open Resilience

Implements a circuit breaker that trips after consecutive Redis failures,
routing reads/writes to PostgreSQL fallback to prevent worker starvation.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from threading import Lock

logger = logging.getLogger("circuit_breaker")

# Circuit breaker states
CLOSED = "closed"   # Normal operation
OPEN = "open"       # Circuit tripped, fast-fail
HALF_OPEN = "half_open"  # Testing if recovery is possible


class CircuitBreaker:
    """
    Circuit breaker for Redis operations.
    
    Trips to OPEN after failure_threshold consecutive failures.
    After timeout_seconds, transitions to HALF_OPEN to test recovery.
    On success in HALF_OPEN, transitions back to CLOSED.
    On failure in HALF_OPEN, returns to OPEN.
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        timeout_seconds: int = 60,
        name: str = "redis"
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.name = name
        
        self._state = CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = Lock()
    
    def _should_allow_request(self) -> bool:
        """Check if request should be allowed based on circuit state."""
        with self._lock:
            if self._state == CLOSED:
                return True
            
            if self._state == OPEN:
                # Check if timeout has elapsed
                if self._last_failure_time and (time.time() - self._last_failure_time) >= self.timeout_seconds:
                    logger.info(f"[CIRCUIT_BREAKER] {self.name} transitioning to HALF_OPEN")
                    self._state = HALF_OPEN
                    return True
                return False
            
            if self._state == HALF_OPEN:
                return True
            
            return False
    
    def _record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            if self._state == HALF_OPEN:
                logger.info(f"[CIRCUIT_BREAKER] {self.name} recovered, transitioning to CLOSED")
                self._state = CLOSED
            
            self._failure_count = 0
            self._last_failure_time = None
    
    def _record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._failure_count >= self.failure_threshold:
                if self._state != OPEN:
                    logger.warning(
                        f"[CIRCUIT_BREAKER] {self.name} tripped to OPEN after "
                        f"{self._failure_count} consecutive failures"
                    )
                    self._state = OPEN
    
    def call(self, func: Callable[[], Any], fallback: Optional[Callable[[], Any]] = None) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: The function to execute (typically a Redis operation)
            fallback: Optional fallback function to call if circuit is open or func fails
            
        Returns:
            Result of func or fallback
        """
        if not self._should_allow_request():
            logger.warning(f"[CIRCUIT_BREAKER] {self.name} is OPEN, using fallback")
            if fallback:
                return fallback()
            raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = func()
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            if fallback:
                logger.warning(f"[CIRCUIT_BREAKER] {self.name} operation failed, using fallback: {exc}")
                return fallback()
            raise
    
    @property
    def state(self) -> str:
        """Current circuit state."""
        with self._lock:
            return self._state
    
    @property
    def failure_count(self) -> int:
        """Current failure count."""
        with self._lock:
            return self._failure_count
    
    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            logger.info(f"[CIRCUIT_BREAKER] {self.name} manually reset to CLOSED")
            self._state = CLOSED
            self._failure_count = 0
            self._last_failure_time = None


# Global circuit breaker instances
_redis_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    timeout_seconds=60,
    name="redis_main"
)


def get_redis_circuit_breaker() -> CircuitBreaker:
    """Get the global Redis circuit breaker instance."""
    return _redis_circuit_breaker
