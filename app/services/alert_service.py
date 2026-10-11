"""
app/services/alert_service.py — Alert queueing and persistence.

REFACTORED: Alert dispatch is now async (queued to Redis).
Alert functions no longer send emails/webhooks directly.
Instead, they queue alert jobs for the alert processor worker to handle.

This prevents blocking webhook handlers.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytz

from config.settings import cfg

logger = logging.getLogger("alert_service")
_IST   = pytz.timezone(cfg.ZONE)



def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(d: Any) -> str:
    if not d:
        return "N/A"
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d.replace("Z", "+00:00"))
        except ValueError:
            return d
    if isinstance(d, datetime):
        if d.tzinfo is None:
            d = pytz.utc.localize(d)
        return d.astimezone(_IST).strftime("%d-%b-%Y %I:%M %p")
    return str(d)


def _log_alert(
    cur,
    event_type:       str,
    sample_id:        int,
    bill_id:          int,
    metadata:         Dict,
    notes:            Optional[str] = None,
    lab_id:           Optional[int] = None,
    webhook_event_id: Optional[int] = None,
) -> None:
    """Insert a row into tat_log for an alert event using the provided cursor."""
    cur.execute(
        """INSERT INTO tat_log
           (sample_id, bill_id, lab_id, event_type, event_timestamp,
            triggered_by, webhook_event_id, notes, metadata)
           VALUES (%s,%s,%s,%s,%s,'system',%s,%s,%s)""",
        (sample_id, bill_id, lab_id, event_type, _now(),
         webhook_event_id, notes, json.dumps(metadata))
    )


def _create_db_alert(
    cur,
    bill_id: Optional[int],
    sample_id: Optional[int],
    test_instance_id: Optional[int],
    lab_id: Optional[int],
    alert_type: str,
    severity: str,
    message: str,
) -> None:
    """Insert a row into tat_alert table."""
    cur.execute(
        """INSERT INTO tat_alert
           (bill_id, sample_id, test_instance_id, lab_id, alert_type, severity, message, is_acknowledged)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 0)""",
        (bill_id, sample_id, test_instance_id, lab_id, alert_type, severity, message)
    )


# ── Public alert functions (queue-based) ────────────────────────────────────

def alert_tat_breach(
    cur,
    sample_id:   int,
    bill_id:     int,
    lab_id:      int,
    sample_info: Dict,
    eta_info:    Dict,
) -> None:
    """
    Queue a TAT breach alert (NO email sent here).
    The alert processor worker will handle email/webhook dispatch.
    """
    meta = {
        "sample_id":          sample_id,
        "bill_id":            bill_id,
        "lab_id":             lab_id,
        "external_bill_id":   sample_info.get("external_bill_id"),
        "accession_no":       sample_info.get("accession_no"),
        "total_eta_mins":     eta_info.get("total_eta_mins"),
        "predefined_tat_mins":eta_info.get("predefined_tat_mins"),
        "breach_by_mins":     eta_info.get("breach_by_mins"),
        "estimated_end_time": _fmt(eta_info.get("estimated_end_time")),
    }
    logger.warning("[TAT_BREACH_QUEUED] sample_id=%d breach_by=%s min",
                   sample_id, eta_info.get("breach_by_mins"))
    
    # Log to database (synchronous)
    _log_alert(cur, "tat_breach_alert", sample_id, bill_id, meta,
               notes=f"TAT breached by {eta_info.get('breach_by_mins')} min",
               lab_id=lab_id)
    
    # Write alert record to database
    _create_db_alert(
        cur,
        bill_id=bill_id,
        sample_id=sample_id,
        test_instance_id=None,
        lab_id=lab_id,
        alert_type="sla_breached",
        severity="critical",
        message=f"Sample {sample_info.get('accession_no')} TAT breached by {eta_info.get('breach_by_mins')} minutes."
    )
    
    # Queue alert for async dispatch (do NOT send email here)
    from app.services.queue_service import enqueue_alert
    enqueue_alert({
        "alert_type": "tat_breach",
        "sample_id": sample_id,
        "bill_id": bill_id,
        "lab_id": lab_id,
        "metadata": meta,
    })


def alert_sample_delayed(
    cur,
    sample_id: int,
    bill_id:   int,
    lab_id:    int,
    queue_id:  int,
    overdue_mins: int,
) -> None:
    """Queue a sample delayed alert."""
    meta = {
        "sample_id":    sample_id,
        "bill_id":      bill_id,
        "lab_id":       lab_id,
        "queue_id":     queue_id,
        "overdue_mins": overdue_mins,
    }
    logger.warning("[SAMPLE_DELAYED_QUEUED] sample_id=%d overdue=%d min", sample_id, overdue_mins)
    _log_alert(cur, "sample_delayed", sample_id, bill_id, meta,
               notes=f"Sample overdue by {overdue_mins} min", lab_id=lab_id)
    
    # Write alert record to database
    _create_db_alert(
        cur,
        bill_id=bill_id,
        sample_id=sample_id,
        test_instance_id=None,
        lab_id=lab_id,
        alert_type="sla_at_risk",
        severity="high",
        message=f"Sample {sample_id} is overdue by {overdue_mins} minutes."
    )
    
    from app.services.queue_service import enqueue_alert
    enqueue_alert({
        "alert_type": "sample_delayed",
        "sample_id": sample_id,
        "bill_id": bill_id,
        "lab_id": lab_id,
        "overdue_mins": overdue_mins,
        "metadata": meta,
    })


def alert_sample_completed(
    cur,
    sample_id:          int,
    bill_id:            int,
    actual_eta_mins:    int,
    predefined_tat_mins: Optional[int],
    within_tat:         bool,
) -> None:
    """Queue a sample completion alert."""
    meta = {
        "sample_id":           sample_id,
        "bill_id":             bill_id,
        "actual_eta_mins":     actual_eta_mins,
        "predefined_tat_mins": predefined_tat_mins,
        "within_tat":          within_tat,
    }
    logger.info("[SAMPLE_COMPLETED_QUEUED] sample_id=%d actual_tat=%d within_tat=%s",
                sample_id, actual_eta_mins, within_tat)
    _log_alert(cur, "sample_completed", sample_id, bill_id, meta,
               notes=f"Completed in {actual_eta_mins} min. Within TAT: {within_tat}")
    
    from app.services.queue_service import enqueue_alert
    enqueue_alert({
        "alert_type": "sample_completed",
        "sample_id": sample_id,
        "bill_id": bill_id,
        "metadata": meta,
    })


def alert_processing_error(
    cur,
    sample_id: int,
    bill_id:   int,
    reason:    str,
    event_id:  Optional[int] = None,
) -> None:
    """Queue a processing error alert."""
    meta = {"sample_id": sample_id, "bill_id": bill_id, "reason": reason, "event_id": event_id}
    logger.error("[PROCESSING_ERROR_QUEUED] sample_id=%d reason=%s", sample_id, reason)
    _log_alert(cur, "processing_error", sample_id, bill_id, meta,
               notes=reason, webhook_event_id=event_id)
    
    # Write alert record to database
    _create_db_alert(
        cur,
        bill_id=bill_id,
        sample_id=sample_id,
        test_instance_id=None,
        lab_id=None,
        alert_type="processing_error",
        severity="medium",
        message=reason
    )
    
    from app.services.queue_service import enqueue_alert
    enqueue_alert({
        "alert_type": "processing_error",
        "sample_id": sample_id,
        "bill_id": bill_id,
        "reason": reason,
        "metadata": meta,
    })


def alert_missing_test_config(
    cur,
    sample_id: int,
    bill_id:   int,
    test_codes: list,
) -> None:
    """Queue a missing test config alert."""
    meta = {"sample_id": sample_id, "bill_id": bill_id, "missing_test_codes": test_codes}
    logger.warning("[MISSING_TEST_CONFIG_QUEUED] sample_id=%d codes=%s", sample_id, test_codes)
    _log_alert(cur, "processing_error", sample_id, bill_id, meta,
               notes=f"No config for test codes: {test_codes}. Using lab default.")
    
    # Write alert record to database
    _create_db_alert(
        cur,
        bill_id=bill_id,
        sample_id=sample_id,
        test_instance_id=None,
        lab_id=None,
        alert_type="missing_config",
        severity="medium",
        message=f"No config for test codes: {test_codes}. Using lab default."
    )
    
    from app.services.queue_service import enqueue_alert
    enqueue_alert({
        "alert_type": "missing_test_config",
        "sample_id": sample_id,
        "bill_id": bill_id,
        "test_codes": test_codes,
        "metadata": meta,
    })


