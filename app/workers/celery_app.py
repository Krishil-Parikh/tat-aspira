"""Celery app — task registration only. Logic in webhook_processor.py."""
from celery import Celery
from config.settings import cfg
import logging

celery_app = Celery("lab_tasks", broker=cfg.REDIS_URL, backend=cfg.REDIS_URL)
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone=cfg.ZONE, enable_utc=True,
    task_acks_late=True, worker_prefetch_multiplier=1, task_track_started=True,
    # SSL settings for Upstash / Managed Redis
    broker_use_ssl={"ssl_cert_reqs": "none"} if cfg.REDIS_URL.startswith("rediss://") else False,
    redis_backend_use_ssl={"ssl_cert_reqs": "none"} if cfg.REDIS_URL.startswith("rediss://") else False,
    broker_pool_limit=1,  # Upstash has connection limits
)
celery_app.conf.beat_schedule = {
    "sweep-delayed":        {"task": "sweep.delayed",        "schedule": 300.0},
    "refresh-proj":         {"task": "projection.refresh",   "schedule": 600.0},
    "reconciliation-sweep": {"task": "reconciliation.sweep", "schedule": 60.0},
    "sla-at-risk-check":    {"task": "sla.at_risk",          "schedule": 300.0},
    "redraw-overdue-check": {"task": "redraw.overdue",       "schedule": 1800.0},
    "lab-downtime-sync":    {"task": "lab.downtime_sync",    "schedule": 3600.0},
}


@celery_app.task(name="webhook.process", bind=True, max_retries=5,
                 default_retry_delay=10, queue=cfg.QUEUE_WEBHOOK)
def process_webhook_task(self, event_id: int):
    import logging
    from celery.exceptions import Retry
    logger = logging.getLogger("celery.webhook")
    logger.info("task start name=webhook.process event_id=%s", event_id)
    from app.workers.webhook_processor import handle_webhook
    try:
        result = handle_webhook(self, event_id)
        logger.info("task success name=webhook.process event_id=%s result=%s", event_id, result)
        return result
    except Retry:
        # Retry exception is expected for transient failures - don't log as fatal error
        raise
    except Exception as exc:
        logger.exception("task failure name=webhook.process event_id=%s error=%s", event_id, exc)
        raise


@celery_app.task(name="sweep.delayed", queue="projection")
def sweep_delayed_samples():
    from app.workers.webhook_processor import do_sweep_delayed
    do_sweep_delayed()


@celery_app.task(name="projection.refresh", queue="projection")
def refresh_projection():
    from app.workers.webhook_processor import do_refresh_projection
    do_refresh_projection()


@celery_app.task(name="reconciliation.sweep", queue="projection")
def sweep_reconciliation():
    from app.services.reconciliation import process_reconciliation_batch
    return process_reconciliation_batch(limit=100)


@celery_app.task(name="sla.at_risk", queue="projection")
def check_sla_at_risk():
    from app.workers.webhook_processor import do_sla_at_risk_check
    do_sla_at_risk_check()


@celery_app.task(name="redraw.overdue", queue="projection")
def check_redraw_overdue():
    from app.workers.webhook_processor import do_redraw_overdue_check
    do_redraw_overdue_check()


@celery_app.task(name="lab.downtime_sync", queue="projection")
def sync_lab_downtime():
    from app.workers.webhook_processor import do_lab_downtime_sync
    do_lab_downtime_sync()


@celery_app.task(name="alert.process", bind=True, queue=cfg.QUEUE_ALERT, max_retries=3, default_retry_delay=5)
def process_alert_task(self, alert_job: dict):
    """Process queued alert — send email/webhook without blocking webhook handlers."""
    import logging
    import smtplib
    import httpx
    from email.mime.text import MIMEText
    
    logger = logging.getLogger("celery.alert")
    alert_type = alert_job.get("alert_type")
    sample_id = alert_job.get("sample_id")
    metadata = alert_job.get("metadata", {})
    
    logger.info("Alert processing: alert_type=%s sample_id=%s", alert_type, sample_id)
    
    try:
        if alert_type == "tat_breach":
            _send_breach_alert(metadata)
        elif alert_type == "sample_delayed":
            _send_delayed_alert(metadata, alert_job.get("overdue_mins", 0))
        elif alert_type == "sample_completed":
            _send_completion_alert(metadata)
        elif alert_type == "processing_error":
            _send_error_alert(metadata, alert_job.get("reason", "Unknown"))
        else:
            logger.warning("Unknown alert type: %s", alert_type)
    except Exception as exc:
        logger.error("Alert send failed: %s", exc)
        # Retry up to max_retries
        raise self.retry(exc=exc)


def _send_breach_alert(metadata: dict) -> None:
    """Send TAT breach email."""
    if not (cfg.SMTP_HOST and cfg.SMTP_USER and cfg.ALERT_EMAIL_TO):
        return
    
    subject = f"TAT BREACH — Sample {metadata.get('sample_id')} (bill {metadata.get('bill_id')})"
    body = (
        f"Sample {metadata.get('sample_id')} TAT breached by {metadata.get('breach_by_mins')} minutes.\n"
        f"Estimated end: {metadata.get('estimated_end_time')}\n"
        f"Predefined TAT: {metadata.get('predefined_tat_mins')} min\n"
        f"Accession: {metadata.get('accession_no')}"
    )
    _send_email(subject, body)


def _send_delayed_alert(metadata: dict, overdue_mins: int) -> None:
    """Send sample delayed email."""
    if not (cfg.SMTP_HOST and cfg.SMTP_USER and cfg.ALERT_EMAIL_TO):
        return
    
    subject = f"SAMPLE DELAYED — Sample {metadata.get('sample_id')}"
    body = f"Sample {metadata.get('sample_id')} is overdue by {overdue_mins} minutes."
    _send_email(subject, body)


def _send_completion_alert(metadata: dict) -> None:
    """Send sample completion webhook and optional email."""
    # Webhook dispatch
    if cfg.WEBHOOK_RESULTS_URL:
        _webhook_dispatch(metadata)


def _send_error_alert(metadata: dict, reason: str) -> None:
    """Log error (already logged to tat_log, no external dispatch needed)."""
    pass


def _send_email(subject: str, body: str) -> None:
    """Send email via SMTP with timeout."""
    import smtplib
    from email.mime.text import MIMEText
    
    logger = logging.getLogger("celery.alert")
    
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg.ALERT_EMAIL_FROM
        msg["To"] = cfg.ALERT_EMAIL_TO
        
        with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=5) as s:
            if cfg.SMTP_PORT == 587:
                s.starttls()
            s.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            s.send_message(msg)
        logger.info("[EMAIL_SENT] %s", subject)
    except Exception as exc:
        logger.error("[EMAIL_FAILED] %s", exc)
        raise  # Will trigger retry


def _webhook_dispatch(payload: dict) -> None:
    """Send webhook with timeout."""
    import httpx
    
    logger = logging.getLogger("celery.alert")
    
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(cfg.WEBHOOK_RESULTS_URL, json=payload)
            resp.raise_for_status()
            logger.info("[WEBHOOK_DISPATCH_OK]")
    except Exception as exc:
        logger.error("[WEBHOOK_DISPATCH_FAILED] %s", exc)
        raise  # Will trigger retry

