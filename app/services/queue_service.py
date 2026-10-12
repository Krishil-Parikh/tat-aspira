"""
Queue Service — Redis-backed work queues with priority scoring.

Uses Redis sorted-sets (ZADD / BZPOPMIN) instead of plain lists so
HIGH-priority samples jump ahead of NORMAL ones.  Priority scores:
  URGENT → 1   (lowest score = highest priority in min-heap)
  HIGH   → 5
  NORMAL → 10

The Celery layer reads from these same queues, so both the lightweight
HTTP path and the Celery worker pool share one broker surface.
"""
from __future__ import annotations
import json
import logging
import time as _time
from typing import Any, Dict, Optional

import redis

from config.settings import cfg

logger = logging.getLogger("queue_service")

_PRIORITY_SCORE = {"URGENT": 1, "HIGH": 5, "NORMAL": 10}

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
            ssl_cert_reqs=None
        )
    return _r


def _score(priority: str) -> float:
    base  = _PRIORITY_SCORE.get(priority.upper(), 10)
    # tie-break with wall-clock so FIFO within same priority
    return base * 1e12 + _time.time()


def enqueue(queue: str, job_name: str, data: Dict[str, Any], priority: str = "NORMAL") -> None:
    """
    Push a job onto a named priority queue.

    queue     : one of cfg.QUEUE_*
    job_name  : logical name used by workers for routing
    data      : arbitrary JSON-serialisable payload
    priority  : "URGENT" | "HIGH" | "NORMAL"
    """
    payload = json.dumps({"name": job_name, "data": data, "attempts": 0})
    score   = _score(priority)
    try:
        _redis().zadd(queue, {payload: score})
        logger.debug("Queued %s/%s priority=%s score=%.0f", queue, job_name, priority, score)
    except Exception as exc:
        logger.error("Queue enqueue failed: %s", exc)
        raise


def dequeue(queue: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
    """
    Blocking pop of the highest-priority job from *queue*.

    Returns the decoded job dict or None on timeout.
    """
    try:
        result = _redis().bzpopmin(queue, timeout=timeout)
        if result:
            _queue, raw, _score = result
            return json.loads(raw)
    except Exception as exc:
        logger.error("Queue dequeue failed: %s", exc)
    return None


# ── Domain helpers ────────────────────────────────────────────────────────────

def enqueue_sample(sample_data: Dict[str, Any]) -> None:
    """Push a sample-processing job with priority derived from the payload."""
    priority = sample_data.get("priority_tat", sample_data.get("priority", "NORMAL"))
    enqueue(cfg.QUEUE_SAMPLE, "process-sample", sample_data, priority)


def enqueue_result(result_data: Dict[str, Any]) -> None:
    """Push a result-processing job at fixed HIGH priority."""
    enqueue(cfg.QUEUE_RESULT, "process-result", result_data, "HIGH")


def enqueue_alert(alert_data: Dict[str, Any]) -> None:
    """Push an alert job — lower priority than results."""
    enqueue(cfg.QUEUE_ALERT, "send-alert", alert_data, "NORMAL")


def enqueue_projection(projection_data: Dict[str, Any]) -> None:
    """Push a read-model projection refresh."""
    enqueue(cfg.QUEUE_PROJECTION, "refresh-projection", projection_data, "NORMAL")
