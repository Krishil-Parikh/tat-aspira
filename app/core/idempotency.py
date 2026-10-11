"""
Idempotency Guard — Redis TTL-keyed deduplication.

Prevents duplicate processing of the same webhook event within a 48-hour window.
Mirrors the 'Idempotency Check' box in the architecture diagram.

Usage:
    guard = IdempotencyGuard()
    if guard.is_duplicate("sample", sample_id):
        return 202  # already accepted
    # ... process
    guard.mark_seen("sample", sample_id)
"""
from __future__ import annotations
import json
import logging
from typing import Optional

import redis

from config.settings import cfg
from app.core.circuit_breaker import get_redis_circuit_breaker

logger = logging.getLogger("idempotency")

_circuit_breaker = get_redis_circuit_breaker()

_r: Optional[redis.Redis] = None


def _redis() -> redis.Redis:
    global _r
    if _r is None:
        _r = redis.from_url(
            cfg.REDIS_URL, 
            decode_responses=True,
            health_check_interval=30,
            socket_timeout=10,
            retry_on_timeout=True,
            ssl_cert_reqs=None if cfg.REDIS_URL.startswith("rediss://") else "required"
        )
    return _r


class IdempotencyGuard:
    """Thread-safe Redis-backed deduplication gate."""

    def __init__(self, ttl_seconds: int = cfg.REDIS_RESULT_TTL):
        self._ttl = ttl_seconds

    def _key(self, event_type: str, event_id: str) -> str:
        return f"idem:{event_type}:{event_id}"

    def is_duplicate(self, event_type: str, event_id: str) -> bool:
        """Return True if this (type, id) pair has been seen before."""
        def _check():
            return bool(_redis().exists(self._key(event_type, event_id)))
        
        try:
            return _circuit_breaker.call(_check, fallback=lambda: False)
        except Exception as exc:
            logger.warning("Idempotency check failed: %s — allowing through", exc)
            return False   # fail-open: better to process a duplicate than drop events

    def mark_seen(self, event_type: str, event_id: str) -> None:
        """Record that this event was successfully accepted."""
        def _mark():
            _redis().set(self._key(event_type, event_id), "1", ex=self._ttl)
        
        try:
            _circuit_breaker.call(_mark)
        except Exception as exc:
            logger.warning("Idempotency mark failed: %s", exc)

    def release(self, event_type: str, event_id: str) -> None:
        """Remove a previously marked key after durable acceptance fails."""
        def _release():
            _redis().delete(self._key(event_type, event_id))
        
        try:
            _circuit_breaker.call(_release)
        except Exception as exc:
            logger.warning("Idempotency release failed: %s", exc)

    def check_and_mark(self, event_type: str, event_id: str) -> bool:
        """
        Atomic check-and-set using SET NX EX.

        Returns True if the event is new (we should process it).
        Returns False if it was already seen (duplicate — skip).
        """
        key = self._key(event_type, event_id)
        
        def _cas():
            # SET key "1" NX EX ttl → only sets if key does NOT exist
            result = _redis().set(key, "1", nx=True, ex=self._ttl)
            return result is True   # None → already existed
        
        try:
            return _circuit_breaker.call(_cas, fallback=lambda: True)
        except Exception as exc:
            logger.warning("Idempotency atomic CAS failed: %s — allowing through", exc)
            return True             # fail-open


# Module-level singleton for convenience
default_guard = IdempotencyGuard()


def _generate_event_key(payload: dict) -> str:
    """
    Generate a unique event key from webhook payload.
    
    Args:
        payload: Webhook payload dictionary
        
    Returns:
        Event key string for idempotency checking
    """
    # Try different fields in order of preference
    for field in ['bill_id', 'sampleId', 'labReportId']:
        if field in payload and payload[field]:
            return str(payload[field])
    
    # Fallback to hash of payload if no ID field found
    import hashlib
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(payload_str.encode()).hexdigest()[:16]
