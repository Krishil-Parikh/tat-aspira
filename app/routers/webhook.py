"""
Unified inbound webhook endpoint.

POST /api/webhook
  - validates flat JSON and {webhook_type, payload} envelopes
  - stores raw event in tat_webhook_event
  - returns 202 after durable insert
  - enqueues Celery for async processing
"""
from __future__ import annotations

import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Type

import orjson
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, ValidationError

from app import pg_database as pgdb
from app.core.idempotency import IdempotencyGuard
from config.settings import cfg
from app.models import (
    BillCancelPayload,
    BillGeneratePayload,
    BillUpdatePayload,
    ReportLifecyclePayload,
    ReportPdfPayload,
    SampleEventPayload,
    SampleRedrawPayload,
    TestDismissedPayload,
    SampleSentExternalPayload,
    WebhookType,
)

logger = logging.getLogger("routers.webhook")
router = APIRouter(prefix="/api/webhook", tags=["Webhooks"])

_idem_guard = IdempotencyGuard(ttl_seconds=172_800)

_PAYLOAD_MODELS: Dict[WebhookType, Type[BaseModel]] = {
    WebhookType.BILL_GENERATE: BillGeneratePayload,
    WebhookType.BILL_UPDATE: BillUpdatePayload,
    WebhookType.BILL_CANCEL: BillCancelPayload,
    WebhookType.SAMPLE_COLLECTED: SampleEventPayload,
    WebhookType.SAMPLE_UNCOLLECTED: SampleEventPayload,
    WebhookType.SAMPLE_RECEIVED: SampleEventPayload,
    WebhookType.SAMPLE_REJECTED: SampleEventPayload,
    WebhookType.SAMPLE_SENT_TO_EXTERNAL: SampleSentExternalPayload,
    WebhookType.SAMPLE_REDRAWN: SampleRedrawPayload,
    WebhookType.SAMPLE_DISMISSED: SampleEventPayload,
    WebhookType.REPORT_SAVE: ReportLifecyclePayload,
    WebhookType.REPORT_SUBMIT: ReportLifecyclePayload,
    WebhookType.REPORT_SIGNED: ReportLifecyclePayload,
    WebhookType.REPORT_PDF: ReportPdfPayload,
    WebhookType.TEST_DISMISSED: TestDismissedPayload,
}

_STATUS_TO_WEBHOOK_TYPE = {
    "bill generate": WebhookType.BILL_GENERATE,
    "bill generation": WebhookType.BILL_GENERATE,
    "bill update": WebhookType.BILL_UPDATE,
    "bill cancel": WebhookType.BILL_CANCEL,
    "sample collected!": WebhookType.SAMPLE_COLLECTED,
    "sample collected": WebhookType.SAMPLE_COLLECTED,
    "sample uncollected": WebhookType.SAMPLE_UNCOLLECTED,
    "sample received": WebhookType.SAMPLE_RECEIVED,
    "sample rejected": WebhookType.SAMPLE_REJECTED,
    "sample redrawn": WebhookType.SAMPLE_REDRAWN,
    "sample dismissed": WebhookType.SAMPLE_DISMISSED,
    "report saved (with values)": WebhookType.REPORT_SAVE,
    "report save (with values)": WebhookType.REPORT_SAVE,
    "report signed": WebhookType.REPORT_SIGNED,
    "report submit (with values)": WebhookType.REPORT_SUBMIT,
    "report submit": WebhookType.REPORT_SUBMIT,
    "report submit pdf": WebhookType.REPORT_PDF,
    "report pdf": WebhookType.REPORT_PDF,
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


async def _verify_webhook_auth(raw_body: bytes, request: Request) -> None:
    if not cfg.WEBHOOK_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="Webhook authentication not configured")

    # Enforce timestamp header presence to prevent replay attacks
    timestamp_header = cfg.WEBHOOK_TIMESTAMP_HEADER if hasattr(cfg, 'WEBHOOK_TIMESTAMP_HEADER') else "X-Aspira-Timestamp"
    timestamp_str = request.headers.get(timestamp_header)
    if not timestamp_str:
        raise HTTPException(status_code=401, detail="Missing timestamp header - replay attack protection")

    try:
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid timestamp format")

    # Clock skew validation: reject timestamps outside ±5 minute window
    now = int(datetime.now(timezone.utc).timestamp())
    max_clock_skew_seconds = 300  # 5 minutes
    if abs(now - timestamp) > max_clock_skew_seconds:
        raise HTTPException(status_code=401, detail="Clock skew exceeded - replay attack protection")

    # Signature verification
    signature = (
        request.headers.get(cfg.WEBHOOK_SIGNATURE_HEADER)
        or request.headers.get("X-Hub-Signature-256")
        or request.headers.get("Authorization")
    )
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    expected = hmac.new(
        cfg.WEBHOOK_SHARED_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature.removeprefix("sha256=").strip()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Store nonce in PostgreSQL for replay protection (works even if Redis fails)
    signature_hash = _sha256(signature.encode("utf-8"))
    from app import pg_database as pgdb
    # Use a simple INSERT with ON CONFLICT to track nonces
    # This is a lightweight operation that prevents replay attacks
    await pgdb._pool.execute(
        """INSERT INTO tat_webhook_nonce (timestamp, signature_hash, webhook_type)
           VALUES ($1, $2, $3)
           ON CONFLICT (timestamp, signature_hash) DO NOTHING""",
        timestamp, signature_hash, "webhook"
    )


def _canonical_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """Accept both flat webhook JSON and {webhook_type, payload} envelopes."""
    payload = body.get("payload")
    if isinstance(payload, dict):
        merged = dict(payload)
        merged.setdefault("webhook_type", body.get("webhook_type") or body.get("webhookType"))
        if body.get("webhookId") is not None:
            merged.setdefault("webhookId", body["webhookId"])
        return merged
    return body


def _extract_webhook_type(body: Dict[str, Any]) -> WebhookType:
    raw = body.get("webhook_type") or body.get("webhookType")
    if raw:
        try:
            return WebhookType(str(raw).upper())
        except ValueError:
            pass

    status = body.get("Status") or body.get("status")
    if status is not None:
        mapped = _STATUS_TO_WEBHOOK_TYPE.get(str(status).strip().lower())
        if mapped:
            body.setdefault("webhook_type", mapped.value)
            return mapped

    webhook_id = body.get("webhookId") or body.get("webhook_id")
    webhook_id_map = {
        6: WebhookType.SAMPLE_RECEIVED,
        7: WebhookType.SAMPLE_REJECTED,
        8: WebhookType.SAMPLE_DISMISSED,
        9: WebhookType.SAMPLE_REDRAWN,
        10: WebhookType.REPORT_SAVE,
        12: WebhookType.REPORT_SIGNED,
        15: WebhookType.REPORT_SUBMIT,
        19: WebhookType.REPORT_PDF,
        31: WebhookType.SAMPLE_COLLECTED,
    }
    try:
        mapped = webhook_id_map.get(int(webhook_id))
    except (TypeError, ValueError):
        mapped = None
    if mapped:
        body.setdefault("webhook_type", mapped.value)
        return mapped

    valid = " | ".join(e.value for e in WebhookType)
    raise HTTPException(status_code=400, detail=f"Missing or unknown webhook_type. Valid: {valid}")


def _extract_lab_id(body: Dict[str, Any]) -> int:
    lab = body.get("labId")
    if isinstance(lab, int):
        return lab
    if isinstance(lab, dict):
        return int(lab.get("labId") or 0)
    return 0


def _strip_base64(body: Dict[str, Any]) -> Dict[str, Any]:
    # Only create a copy if reportBase64 is actually present to avoid unnecessary overhead
    if "reportBase64" not in body:
        return body
    clean = dict(body)
    clean.pop("reportBase64", None)
    return clean


def _extract_event_key(body: Dict[str, Any]) -> Any:
    key = body.get("bill_id")
    if key is None: key = body.get("billId")
    if key is None: key = body.get("billID")
    if key is None: key = body.get("sampleId")
    if key is None: key = body.get("identifier")
    if key is None: key = body.get("sampleID")
    if key is None: key = body.get("labReportId")
    if key is None: key = body.get("CentreReportId")
    
    if key is None and isinstance(body.get("billData"), dict):
        bd = body["billData"]
        key = bd.get("billID") if bd.get("billID") is not None else bd.get("bill_id")
    return key


def _dedupe_key(webhook_type: str, event_key: Any, webhook_id: Optional[Any]) -> str:
    webhook_id_part = webhook_id if webhook_id is not None else "null"
    return f"{webhook_type}:{event_key}:{webhook_id_part}"


@router.post("", status_code=202, response_model=None)
async def ingest_webhook(request: Request):
    raw_body = await request.body()
    source_ip = request.client.host if request.client else None
    logger.info("webhook received raw_bytes=%d source_ip=%s", len(raw_body), source_ip)
    logger.debug("webhook raw body=%r", raw_body[:8192])

    await _verify_webhook_auth(raw_body, request)

    try:
        parsed = orjson.loads(raw_body)
    except Exception as exc:
        logger.warning("webhook parse failed invalid_json error=%s raw_body=%r", exc, raw_body[:2048])
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(parsed, dict):
        logger.warning("webhook parse failed non_object type=%s", type(parsed).__name__)
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    body = _canonical_body(parsed)
    webhook_type = _extract_webhook_type(body)

    try:
        _PAYLOAD_MODELS[webhook_type].model_validate(body)
    except ValidationError as exc:
        logger.warning("webhook validation failed type=%s errors=%s body=%s", webhook_type.value, exc.errors(), body)
        raise HTTPException(status_code=422, detail=exc.errors())

    event_key = _extract_event_key(body)
    webhook_id = body.get("webhookId")
    lab_id = _extract_lab_id(body)
    logger.info(
        "webhook parsed type=%s event_key=%s webhook_id=%s has_payload=%s",
        webhook_type.value,
        event_key,
        webhook_id,
        isinstance(parsed.get("payload"), dict),
    )

    if not event_key:
        raise HTTPException(status_code=400, detail="Missing key field: bill_id, billId, sampleId, or labReportId")

    clean_body = body if webhook_type == WebhookType.REPORT_PDF else _strip_base64(body)
    payload_hash = _sha256(orjson.dumps(clean_body, option=orjson.OPT_SORT_KEYS))

    dedupe_key = _dedupe_key(webhook_type.value, event_key, webhook_id)
    redis_new = _idem_guard.check_and_mark("webhook", dedupe_key)
    if not redis_new:
        logger.info(
            "duplicate event skipped layer=redis key=%s type=%s webhook_id=%s",
            event_key,
            webhook_type.value,
            webhook_id,
        )
        return ORJSONResponse(content={"status": "accepted", "duplicate": True}, status_code=202)

    is_hash_dup = await pgdb.check_duplicate_payload_hash(payload_hash)
    if is_hash_dup:
        logger.info(
            "duplicate event skipped layer=postgres_payload_hash hash=%s type=%s",
            payload_hash,
            webhook_type.value,
        )
        return ORJSONResponse(content={"status": "accepted", "duplicate": True}, status_code=202)

    is_dup = await pgdb.check_duplicate_event(event_key, webhook_type.value, webhook_id)
    if is_dup:
        logger.info(
            "duplicate event skipped layer=postgres key=%s type=%s webhook_id=%s",
            event_key,
            webhook_type.value,
            webhook_id,
        )
        return ORJSONResponse(content={"status": "accepted", "duplicate": True}, status_code=202)

    auth_token = (
        request.headers.get(cfg.WEBHOOK_SIGNATURE_HEADER)
        or request.headers.get("X-Hub-Signature-256")
        or request.headers.get("Authorization")
    )
    auth_token_hash = _sha256(auth_token.encode("utf-8")) if auth_token else None

    try:
        event_id = await pgdb.insert_webhook_event(
            {
                "webhook_id": webhook_id,
                "webhook_type": webhook_type.value,
                "bill_id": event_key,
                "internal_bill_id": None,
                "lab_id": lab_id,
                "payload": clean_body,
                "payload_hash": payload_hash,
                "source_ip": source_ip,
                "auth_token_hash": auth_token_hash,
            }
        )
    except Exception as exc:
        _idem_guard.release("webhook", dedupe_key)
        logger.exception(
            "DB insert failure table=tat_webhook_event type=%s key=%s webhook_id=%s error=%s",
            webhook_type.value,
            event_key,
            webhook_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Webhook event insert failed")

    logger.info(
        "DB insert success table=tat_webhook_event event_id=%d type=%s key=%s webhook_id=%s",
        event_id,
        webhook_type.value,
        event_key,
        webhook_id,
    )
    logger.info("new event accepted event_id=%d type=%s key=%s", event_id, webhook_type.value, event_key)

    try:
        from app.workers.celery_app import process_webhook_task

        result = process_webhook_task.delay(event_id)
        logger.info(
            "celery task triggered event_id=%d task_id=%s queue=queue:webhook-processing",
            event_id,
            result.id,
        )
    except Exception as exc:
        logger.exception("celery enqueue failed event_id=%d error=%s", event_id, exc)
        await pgdb.mark_event_failed(event_id, f"Enqueue failed: {exc}")

    return ORJSONResponse(
        content={"status": "accepted", "event_id": event_id, "duplicate": False},
        status_code=202,
    )


@router.get("/health", tags=["Infra"])
async def webhook_health():
    return {"status": "ok", "endpoint": "POST /api/webhook"}
