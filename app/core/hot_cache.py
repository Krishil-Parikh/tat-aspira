"""
Hot Pipeline Cache — Redis hash-backed read cache with a recency index.

Each sample is stored once under its sample_id key, which avoids duplicate
stale members while still allowing ordered reads through a small sorted-set
index of sample ids.
"""
from __future__ import annotations
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import orjson
import redis

from config.settings import cfg
from app.core.circuit_breaker import get_redis_circuit_breaker

logger = logging.getLogger("hot_cache")

_circuit_breaker = get_redis_circuit_breaker()

_HASH_KEY   = cfg.CACHE_HOT_PIPELINE
_ORDER_KEY  = f"{cfg.CACHE_HOT_PIPELINE}:order"
_MAX_ITEMS = 500   # keep the freshest 500 records in hot cache

_r: Optional[redis.Redis] = None


def _redis() -> redis.Redis:
    global _r
    if _r is None:
        # decode_responses=False → bytes in, bytes out (no overhead)
        _r = redis.from_url(
            cfg.REDIS_URL, 
            decode_responses=False,
            health_check_interval=30,
            socket_timeout=10,
            retry_on_timeout=True,
            ssl_cert_reqs=None
        )
    return _r


def _score() -> float:
    """Monotonic float score for Redis sorted-set ordering."""
    return datetime.utcnow().timestamp()


def _record_key(record: Dict[str, Any]) -> str:
    candidate = (
        record.get("sample_id")
        or record.get("sampleId")
        or record.get("accession_no")
        or record.get("accessionNo")
        or record.get("external_bill_id")
        or record.get("externalBillId")
        or record.get("bill_id")
        or record.get("billId")
    )
    if candidate is not None:
        return str(candidate)
    return hashlib.sha256(orjson.dumps(record, option=orjson.OPT_SORT_KEYS)).hexdigest()


def push(record: Dict[str, Any]) -> None:
    """
    Add / update a pipeline record in the hot cache.

    Uses a Pipeline for atomic ZADD + ZREMRANGEBYRANK (trim to _MAX_ITEMS).
    """
    def _push():
        payload = orjson.dumps(record)
        key = _record_key(record)
        redis_conn = _redis()

        overflow = redis_conn.zcard(_ORDER_KEY) - _MAX_ITEMS + 1
        trimmed_keys: List[bytes] = []
        if overflow > 0:
            trimmed_keys = redis_conn.zrange(_ORDER_KEY, 0, overflow - 1)

        pipe = redis_conn.pipeline()
        pipe.hset(_HASH_KEY, key, payload)
        pipe.zadd(_ORDER_KEY, {key: _score()})
        if trimmed_keys:
            pipe.zrem(_ORDER_KEY, *trimmed_keys)
            pipe.hdel(_HASH_KEY, *trimmed_keys)
        pipe.execute()
    
    try:
        _circuit_breaker.call(_push)
    except Exception as exc:
        logger.warning("hot_cache push failed: %s", exc)


def get_all() -> bytes:
    """
    Return all cached records as a raw JSON bytes array.

    Sorted newest-first.  Returns pre-joined bytes so the FastAPI
    response layer never needs to parse + re-serialise.
    """
    def _get():
        keys = _redis().zrevrange(_ORDER_KEY, 0, -1)
        if keys:
            pipe = _redis().pipeline()
            for key in keys:
                pipe.hget(_HASH_KEY, key)
            raws = [raw for raw in pipe.execute() if raw]
            if raws:
                return b"[" + b",".join(raws) + b"]"
        return b"[]"
    
    try:
        return _circuit_breaker.call(_get, fallback=lambda: b"[]")
    except Exception as exc:
        logger.warning("hot_cache get_all failed: %s", exc)
        return b"[]"


def get_page(offset: int = 0, limit: int = 50) -> bytes:
    """Paginated read from hot cache."""
    def _get():
        keys = _redis().zrevrange(_ORDER_KEY, offset, offset + limit - 1)
        if keys:
            pipe = _redis().pipeline()
            for key in keys:
                pipe.hget(_HASH_KEY, key)
            raws = [raw for raw in pipe.execute() if raw]
            if raws:
                return b"[" + b",".join(raws) + b"]"
        return b"[]"
    
    try:
        return _circuit_breaker.call(_get, fallback=lambda: b"[]")
    except Exception as exc:
        logger.warning("hot_cache get_page failed: %s", exc)
        return b"[]"


def invalidate(sample_id: str) -> None:
    """
    Remove all entries for a given sample_id from the hot cache.

    Scans all members and removes matching ones.  O(N) — acceptable
    since the cache is bounded to _MAX_ITEMS.
    """
    def _invalidate():
        r = _redis()
        pipe = r.pipeline()
        pipe.hdel(_HASH_KEY, sample_id)
        pipe.zrem(_ORDER_KEY, sample_id)
        pipe.execute()
    
    try:
        _circuit_breaker.call(_invalidate)
    except Exception as exc:
        logger.warning("hot_cache invalidate failed: %s", exc)


def flush() -> None:
    """Clear the entire hot cache (dev / testing use)."""
    def _flush():
        _redis().delete(_HASH_KEY, _ORDER_KEY)
    
    try:
        _circuit_breaker.call(_flush)
    except Exception as exc:
        logger.warning("hot_cache flush failed: %s", exc)
