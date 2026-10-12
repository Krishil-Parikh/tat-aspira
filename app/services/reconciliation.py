"""
Reconciliation service for out-of-order webhook events.

Phase 1 scope:
- enqueue unresolved events durably
- sweep due reconciliation items
- resubmit due events through existing Celery pipeline
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core.pg_pool import pooled_connection
from config.settings import cfg

logger = logging.getLogger("reconciliation")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _next_backoff(attempt: int) -> datetime:
    # Exponential backoff: 60s, 120s, 240s, ... capped at 1 hour.
    delay = min(60 * (2 ** max(0, attempt - 1)), 3600)
    return _now() + timedelta(seconds=delay)


def enqueue_reconciliation(
    cur,
    *,
    webhook_event_id: int,
    webhook_type: str,
    prerequisite_type: str,
    external_bill_id: Optional[int] = None,
    prerequisite_detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert or update a pending reconciliation item for the given event."""
    if not cfg.MIGRATION_RECONCILIATION_ENABLED:
        return

    cur.execute(
        """
        INSERT INTO tat_reconciliation_queue
          (webhook_event_id, webhook_type, external_bill_id,
           prerequisite_type, prerequisite_detail,
           attempt_count, max_attempts, next_attempt_at, status)
        VALUES (%s,%s,%s,%s,%s,0,10,%s,'pending')
        ON CONFLICT (webhook_event_id) DO UPDATE
          SET prerequisite_type = EXCLUDED.prerequisite_type,
              prerequisite_detail = EXCLUDED.prerequisite_detail,
              external_bill_id = EXCLUDED.external_bill_id,
              status = 'pending',
              updated_at = CURRENT_TIMESTAMP
        """,
        (
            webhook_event_id,
            webhook_type,
            external_bill_id,
            prerequisite_type,
            prerequisite_detail,
            _next_backoff(1),
        ),
    )

    # Keep existing status enum untouched for current DB compatibility.
    cur.execute(
        """
        UPDATE tat_webhook_event
        SET status='failed',
            error_message=%s,
            retry_count=retry_count+1
        WHERE id=%s
        """,
        (f"Awaiting reconciliation: {prerequisite_type}", webhook_event_id),
    )


def process_reconciliation_batch(limit: int = 100) -> Dict[str, int]:
    """Pick due pending items and requeue through existing webhook task."""
    if not cfg.MIGRATION_RECONCILIATION_SWEEP_ENABLED:
        return {"pending": 0, "requeued": 0, "exhausted": 0}

    from app.workers.celery_app import process_webhook_task

    stats = {"pending": 0, "requeued": 0, "exhausted": 0}
    now = _now()

    with pooled_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, webhook_event_id, attempt_count, max_attempts
            FROM tat_reconciliation_queue
            WHERE status='pending' AND next_attempt_at <= %s
            ORDER BY next_attempt_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (now, limit),
        )
        rows = cur.fetchall()
        stats["pending"] = len(rows)

        for row in rows:
            rq_id = row["id"]
            event_id = row["webhook_event_id"]
            attempt_count = int(row["attempt_count"] or 0) + 1
            max_attempts = int(row["max_attempts"] or 10)

            if attempt_count >= max_attempts:
                cur.execute(
                    """
                    UPDATE tat_reconciliation_queue
                    SET status='exhausted',
                        attempt_count=%s,
                        last_attempt_at=%s,
                        last_error='Max attempts exceeded',
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                    """,
                    (attempt_count, now, rq_id),
                )
                stats["exhausted"] += 1
                continue

            process_webhook_task.delay(event_id)
            cur.execute(
                """
                UPDATE tat_reconciliation_queue
                SET attempt_count=%s,
                    last_attempt_at=%s,
                    next_attempt_at=%s,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (attempt_count, now, _next_backoff(attempt_count + 1), rq_id),
            )
            stats["requeued"] += 1

        conn.commit()

    logger.info(
        "reconciliation sweep pending=%d requeued=%d exhausted=%d",
        stats["pending"],
        stats["requeued"],
        stats["exhausted"],
    )
    return stats
