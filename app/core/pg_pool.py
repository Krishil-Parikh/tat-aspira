"""
Shared psycopg2 connection pooling for synchronous code paths.

Celery workers and sync helper flows use this pool to avoid opening a new
TCP/SSL connection for every task or request.

Fixes applied:
  C3 — Neon cold-start: TCP keepalive params added to DSN so the OS
       maintains the connection and psycopg2 detects dead sessions quickly.
  C4 — Aborted transaction leak: pooled_connection() now rolls back before
       returning the connection to the pool so the next caller always gets
       a clean connection (not one stuck in InFailedSqlTransaction).
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config.settings import cfg

logger = logging.getLogger("pg_pool")

_pool: Optional[ThreadedConnectionPool] = None


def _build_dsn() -> str:
    """
    Append TCP keepalive + connect_timeout params to the configured DSN.

    Neon serverless pauses idle connections after ~5 min. Without keepalives
    the OS silently drops the TCP session and psycopg2 only discovers this on
    the next query (InterfaceError: connection already closed).

    keepalives=1            — enable TCP keepalive probes
    keepalives_idle=30      — send first probe after 30 s of silence
    keepalives_interval=10  — resend probe every 10 s
    keepalives_count=5      — declare dead after 5 failed probes
    connect_timeout=10      — abort new connections that take > 10 s
    """
    dsn = cfg.PG_DSN.strip()
    extras = (
        " keepalives=1"
        " keepalives_idle=30"
        " keepalives_interval=10"
        " keepalives_count=5"
        " connect_timeout=10"
    )
    # Only append if not already present (idempotent)
    if "keepalives" not in dsn:
        dsn += extras
    return dsn


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            minconn=max(1, cfg.PG_POOL_MIN),
            maxconn=max(cfg.PG_POOL_MIN + 1, cfg.PG_POOL_MAX),
            dsn=_build_dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


@contextmanager
def pooled_connection() -> Iterator[psycopg2.extensions.connection]:
    """
    Yield a psycopg2 connection from the shared pool.

    C4 fix — On every exit (normal or exception):
      - Rolls back any uncommitted / aborted transaction so the connection
        is returned clean. Callers that want to commit must do so explicitly
        BEFORE leaving this context manager (current pattern in handle_webhook
        is already correct — it calls conn.commit() inside the with block).
      - If the connection itself is broken (Neon cold-start / network drop),
        closes and discards it so callers never receive a zombie connection.
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        # Always rollback uncommitted / aborted work before returning.
        # This is a no-op when the caller already committed explicitly.
        try:
            if conn.closed:
                pool.putconn(conn, close=True)
            else:
                conn.rollback()
                pool.putconn(conn)
        except Exception as exc:
            # Broken connection (Neon cold-start, network drop, etc.) —
            # discard it entirely so the pool issues a fresh one next time.
            logger.warning("pg_pool: discarding broken connection: %s", exc)
            try:
                pool.putconn(conn, close=True)
            except Exception:
                pass