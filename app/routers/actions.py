"""
app/routers/actions.py — Role-specific action endpoints.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.workers.celery_app import process_webhook_task
from app.core.auth import require_role, UserSession

logger = logging.getLogger("routers.actions")

actions_router = APIRouter(prefix="/api", tags=["Actions"])

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _insert_internal_webhook_event(conn, *, webhook_id: int, webhook_type: str, bill_id: int, lab_id: int, payload: dict) -> tuple[int, bool]:
    row = await conn.fetchrow(
        """
        WITH ins AS (
            INSERT INTO tat_webhook_event (webhook_id, webhook_type, bill_id, lab_id, payload, status)
            VALUES ($1, $2, $3, $4, $5, 'received')
            ON CONFLICT (bill_id, webhook_type, webhook_id) DO NOTHING
            RETURNING id, FALSE AS duplicate
        )
        SELECT id, duplicate FROM ins
        UNION ALL
        SELECT id, TRUE AS duplicate
        FROM tat_webhook_event
        WHERE bill_id = $3 AND webhook_type = $2 AND webhook_id = $1
        LIMIT 1
        """,
        webhook_id,
        webhook_type,
        bill_id,
        lab_id,
        json.dumps(payload),
    )
    if not row:
        raise HTTPException(500, "Webhook event insert failed")
    return row["id"], row["duplicate"]

# ── Logistics ─────────────────────────────────────────────────────────────────

@actions_router.get("/logistics/pickup-queue")
async def get_pickup_queue(user: UserSession = Depends(require_role(['logistics', 'admin']))):
    from app.pg_database import _pool
    rows = await _pool.fetch("""
        SELECT s.id, s.accession_no, s.priority, s.status,
               s.collected_at, s.assigned_lab_id,
               b.patient_name, b.external_bill_id, b.org_name AS pickup_location,
               l.lab_name AS drop_location,
               COALESCE(e.total_eta_mins, 0) AS total_eta_mins,
               COALESCE(e.is_tat_breached, 0) AS is_tat_breached
        FROM tat_sample s
        JOIN tat_bill b ON b.id = s.bill_id
        LEFT JOIN tat_lab l ON l.id = s.assigned_lab_id
        LEFT JOIN tat_eta e ON e.sample_id = s.id
        WHERE s.status IN ('routed', 'pending', 'in_transit', 'arrived')
        ORDER BY s.priority DESC, s.collected_at ASC NULLS LAST
        LIMIT 100
    """)
    return {"queue": [dict(r) for r in rows], "total": len(rows)}

class PickupRequest(BaseModel):
    sample_id: int

@actions_router.post("/logistics/confirm-pickup")
async def confirm_pickup(req: PickupRequest, user: UserSession = Depends(require_role(['logistics', 'admin']))):
    from app.pg_database import _pool
    now = _now()
    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("SELECT id, bill_id FROM tat_sample WHERE id=$1", req.sample_id)
        if not sample: raise HTTPException(404, "Sample not found")
        async with conn.transaction():
            await conn.execute("UPDATE tat_sample SET status='in_transit', updated_at=$1 WHERE id=$2", now, req.sample_id)
            await conn.execute("INSERT INTO tat_log (sample_id, bill_id, event_type, triggered_by, notes) VALUES ($1, $2, 'sample_picked_up', 'logistics_user', 'Picked up')", req.sample_id, sample["bill_id"])
    return {"message": "Pickup confirmed"}

class DeliveryRequest(BaseModel):
    sample_id: int
    lab_id: int

@actions_router.post("/logistics/confirm-delivery")
async def confirm_delivery(req: DeliveryRequest, user: UserSession = Depends(require_role(['logistics', 'admin']))):
    from app.pg_database import _pool
    now = _now()
    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("""
            SELECT s.id, s.accession_no, s.external_sample_id,
                   b.id AS internal_bill_id, b.external_bill_id
            FROM tat_sample s JOIN tat_bill b ON b.id = s.bill_id
            WHERE s.id = $1
        """, req.sample_id)
        if not sample:
            raise HTTPException(404, "Sample not found")

        ext_bill_id = sample["external_bill_id"] or sample["internal_bill_id"]
        payload = {
            "webhook_type": "SAMPLE_RECEIVED",
            "bill_id": ext_bill_id,
            "sampleId": sample["external_sample_id"],
            "accessionNo": sample["accession_no"],
            "labId": req.lab_id,
            "receivedTime": now.isoformat(),
        }
        event_id, duplicate = await _insert_internal_webhook_event(
            conn,
            webhook_id=req.sample_id,
            webhook_type="SAMPLE_RECEIVED",
            bill_id=ext_bill_id,
            lab_id=req.lab_id,
            payload=payload,
        )
        if not duplicate:
            process_webhook_task.delay(event_id)
        logger.info("[DELIVERY] sample_id=%d lab_id=%d event_id=%d", req.sample_id, req.lab_id, event_id)
    return {"message": "Delivery confirmed", "event_id": event_id, "duplicate": duplicate}

@actions_router.get("/logistics/delivery-status")
async def get_delivery_status(user: UserSession = Depends(require_role(['logistics', 'admin']))):
    from app.pg_database import _pool
    rows = await _pool.fetch("SELECT s.id, s.accession_no, s.status, b.patient_name, l.lab_name FROM tat_sample s JOIN tat_bill b ON b.id = s.bill_id LEFT JOIN tat_lab l ON l.id = s.assigned_lab_id WHERE s.status IN ('in_transit', 'arrived', 'routed') ORDER BY s.updated_at DESC LIMIT 100")
    return {"samples": [dict(r) for r in rows]}

# ── Lab User ──────────────────────────────────────────────────────────────────

@actions_router.get("/lab/{lab_id}/work-queue")
async def get_lab_work_queue(lab_id: int, user: UserSession = Depends(require_role(['lab', 'admin']))):
    if user.role == 'lab' and user.lab_id != lab_id: raise HTTPException(403, "Forbidden")
    from app.pg_database import _pool
    rows = await _pool.fetch("""
        SELECT s.id AS sample_id, s.accession_no, s.priority, s.status AS sample_status, b.patient_name,
               ti.id AS test_instance_id, ti.test_code, ti.test_name, ti.status AS test_status,
               e.estimated_end_time, e.is_tat_breached
        FROM tat_sample s
        JOIN tat_bill b ON b.id = s.bill_id
        JOIN tat_test_instance ti ON ti.sample_id = s.id
        LEFT JOIN tat_eta e ON e.sample_id = s.id
        WHERE ti.processing_lab_id = $1 AND ti.status NOT IN ('completed', 'cancelled')
        ORDER BY s.priority DESC, e.estimated_end_time ASC LIMIT 200
    """, lab_id)
    return {"lab_id": lab_id, "work_items": [dict(r) for r in rows]}

class LabReceiptRequest(BaseModel):
    sample_id: int
    lab_id: int

@actions_router.post("/lab/confirm-receipt")
async def lab_confirm_receipt(req: LabReceiptRequest, user: UserSession = Depends(require_role(['lab', 'admin']))):
    from app.pg_database import _pool
    now = _now()
    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("""
            SELECT s.id, s.accession_no, s.external_sample_id,
                   b.id AS internal_bill_id, b.external_bill_id
            FROM tat_sample s JOIN tat_bill b ON b.id = s.bill_id
            WHERE s.id = $1
        """, req.sample_id)
        if not sample:
            raise HTTPException(404, "Sample not found")

        ext_bill_id = sample["external_bill_id"] or sample["internal_bill_id"]
        payload = {
            "webhook_type": "SAMPLE_RECEIVED",
            "bill_id": ext_bill_id,
            "sampleId": sample["external_sample_id"],
            "accessionNo": sample["accession_no"],
            "labId": req.lab_id,
            "receivedTime": now.isoformat(),
        }
        event_id, duplicate = await _insert_internal_webhook_event(
            conn,
            webhook_id=req.sample_id,
            webhook_type="SAMPLE_RECEIVED",
            bill_id=ext_bill_id,
            lab_id=req.lab_id,
            payload=payload,
        )
        await conn.execute(
            "UPDATE tat_sample SET arrived_at_lab=$1, status='arrived', updated_at=$1 WHERE id=$2",
            now, req.sample_id
        )
        if not duplicate:
            process_webhook_task.delay(event_id)
        logger.info("[LAB_RECEIPT] sample_id=%d lab_id=%d event_id=%d", req.sample_id, req.lab_id, event_id)
    return {"message": "Receipt confirmed", "event_id": event_id, "duplicate": duplicate}

class TestStatusRequest(BaseModel):
    test_instance_id: int
    status: str

@actions_router.post("/lab/test-status")
async def update_test_status(req: TestStatusRequest, user: UserSession = Depends(require_role(['lab', 'admin']))):
    from app.pg_database import _pool
    status_map = {"in_queue": "processing", "processing": "processing", "completed": "completed", "cancelled": "cancelled"}
    db_status = status_map.get(req.status.lower(), "pending")
    await _pool.execute("UPDATE tat_test_instance SET status=$1, updated_at=CURRENT_TIMESTAMP WHERE id=$2", db_status, req.test_instance_id)
    return {"message": "Status updated"}

class SubmitResultRequest(BaseModel):
    test_instance_id: int
    sample_id: int
    result: str

@actions_router.post("/lab/submit-result")
async def submit_test_result(req: SubmitResultRequest, user: UserSession = Depends(require_role(['lab', 'admin']))):
    from app.pg_database import _pool
    now = _now()
    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("SELECT bill_id FROM tat_sample WHERE id=$1", req.sample_id)
        if not sample:
            raise HTTPException(404, "Sample not found")
        test = await conn.fetchrow("SELECT test_code, processing_lab_id FROM tat_test_instance WHERE id=$1", req.test_instance_id)
        if not test:
            raise HTTPException(404, "Test instance not found")
        payload = {"webhook_type": "REPORT_SUBMIT", "bill_id": sample["bill_id"], "labId": test["processing_lab_id"], "testID": req.test_instance_id, "testCode": test["test_code"], "result": req.result, "reportDate": now.isoformat()}
        event_id, duplicate = await _insert_internal_webhook_event(
            conn,
            webhook_id=req.test_instance_id,
            webhook_type="REPORT_SUBMIT",
            bill_id=sample["bill_id"],
            lab_id=test["processing_lab_id"],
            payload=payload,
        )
        if not duplicate:
            process_webhook_task.delay(event_id)
    return {"message": "Result submitted", "event_id": event_id, "duplicate": duplicate}

# ── Lab EDOS Management ────────────────────────────────────────────────────────

class LabEdosUpdateRequest(BaseModel):
    test_code: str
    processing_time_mins: int
    committed_tat_hours: Optional[float] = None
    is_active: Optional[int] = 1

@actions_router.get("/lab/edos")
async def get_lab_edos(user: UserSession = Depends(require_role(['lab', 'admin']))):
    from app.pg_database import _pool
    lab_id = user.lab_id
    if not lab_id:
        row = await _pool.fetchrow("SELECT id FROM tat_lab ORDER BY id LIMIT 1")
        lab_id = row['id'] if row else None
    if not lab_id: return {"success": True, "edos": []}
    rows = await _pool.fetch("SELECT e.*, c.test_name as global_name, c.department_name FROM tat_lab_edos e JOIN tat_test_type_config c ON c.test_code = e.test_code WHERE e.lab_id = $1 ORDER BY e.test_code", lab_id)
    return {"lab_id": lab_id, "edos": [dict(r) for r in rows]}

@actions_router.post("/lab/edos/update")
async def update_lab_edos(req: LabEdosUpdateRequest, user: UserSession = Depends(require_role(['lab', 'admin']))):
    from app.pg_database import _pool
    lab_id = user.lab_id
    if not lab_id:
        row = await _pool.fetchrow("SELECT id FROM tat_lab ORDER BY id LIMIT 1")
        lab_id = row['id'] if row else None
    async with _pool.acquire() as conn:
        await conn.execute("UPDATE tat_lab_edos SET processing_time_mins=$1, committed_tat_hours=$2, is_active=$3, updated_at=CURRENT_TIMESTAMP WHERE lab_id=$4 AND test_code=$5", req.processing_time_mins, req.committed_tat_hours, req.is_active, lab_id, req.test_code)
    return {"success": True}

# ── Admin Extensions ──────────────────────────────────────────────────────────

@actions_router.get("/admin/unassigned")
async def get_unassigned_samples(user: UserSession = Depends(require_role(['admin']))):
    from app.pg_database import _pool
    rows = await _pool.fetch("""
        SELECT s.id, s.accession_no, s.priority, s.routing_reason,
               b.patient_name, b.external_bill_id
        FROM tat_sample s JOIN tat_bill b ON b.id = s.bill_id
        WHERE s.status = 'unassigned'
        ORDER BY s.created_at DESC
        LIMIT 100
    """)
    return {"unassigned": [dict(r) for r in rows]}


# ── Admin Priority Override ——————————————————————————————————————————————

class PriorityOverrideRequest(BaseModel):
    sample_id: int
    priority: str   # "URGENT" | "HIGH" | "NORMAL"
    reason: str


@actions_router.post("/override/priority")
async def admin_change_priority(
    req: PriorityOverrideRequest,
    user: UserSession = Depends(require_role(['admin'])),
):
    """
    BUG-H2 FIX: This endpoint was called by adminChangePriority() in api.ts
    but did not exist, returning 404.
    """
    from app.pg_database import _pool
    priority_map = {"URGENT": 1, "HIGH": 3, "NORMAL": 5}
    p_val = priority_map.get(req.priority.upper(), 5)
    is_urgent = 1 if req.priority.upper() == "URGENT" else 0

    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("SELECT id, bill_id FROM tat_sample WHERE id=$1", req.sample_id)
        if not sample:
            raise HTTPException(404, f"Sample {req.sample_id} not found")

        async with conn.transaction():
            await conn.execute(
                "UPDATE tat_sample SET priority=$1, is_urgent=$2, updated_at=CURRENT_TIMESTAMP WHERE id=$3",
                p_val, is_urgent, req.sample_id
            )
            # Also update queue entry priority
            await conn.execute(
                "UPDATE tat_lab_queue SET priority=$1, updated_at=CURRENT_TIMESTAMP WHERE sample_id=$2",
                p_val, req.sample_id
            )
            # Audit log
            await conn.execute(
                """INSERT INTO tat_log
                   (sample_id, bill_id, event_type, triggered_by, notes, event_timestamp)
                   VALUES ($1, $2, 'priority_override', $3, $4, CURRENT_TIMESTAMP)""",
                req.sample_id, sample["bill_id"],
                user.email,
                f"Priority changed to {req.priority}: {req.reason}",
            )

    logger.info(
        "[OVERRIDE] priority sample_id=%d new_priority=%s by=%s reason=%s",
        req.sample_id, req.priority, user.email, req.reason
    )
    return {"success": True, "sample_id": req.sample_id, "new_priority": req.priority}


# ── Admin Routing Override —————————————————————————————————————————————

class RoutingOverrideRequest(BaseModel):
    sample_id: int
    new_lab_id: int
    reason: str
    test_code: Optional[str] = None  # If None, reroute all tests; if set, reroute specific test


@actions_router.post("/override/routing")
async def admin_override_routing(
    req: RoutingOverrideRequest,
    user: UserSession = Depends(require_role(['admin'])),
):
    """
    BUG-H2 FIX: This endpoint was called by adminOverrideRouting() in api.ts
    but did not exist, returning 404.
    Reroutes a sample (or specific test) to a different lab and re-enqueues.
    """
    from app.pg_database import _pool
    now = _now()

    async with _pool.acquire() as conn:
        sample = await conn.fetchrow("""
            SELECT s.id, s.bill_id, s.accession_no,
                   b.external_bill_id
            FROM tat_sample s JOIN tat_bill b ON b.id = s.bill_id
            WHERE s.id = $1
        """, req.sample_id)
        if not sample:
            raise HTTPException(404, f"Sample {req.sample_id} not found")

        # Verify target lab exists and is active
        lab = await conn.fetchrow(
            "SELECT id, lab_name FROM tat_lab WHERE id=$1 AND is_active=1",
            req.new_lab_id
        )
        if not lab:
            raise HTTPException(400, f"Lab {req.new_lab_id} not found or inactive")

        async with conn.transaction():
            if req.test_code:
                # Reroute specific test only
                await conn.execute(
                    """UPDATE tat_test_instance
                       SET processing_lab_id=$1, routing_reason=$2, updated_at=CURRENT_TIMESTAMP
                       WHERE sample_id=$3 AND test_code=$4 AND status NOT IN ('completed','cancelled')""",
                    req.new_lab_id, f"Admin override: {req.reason}",
                    req.sample_id, req.test_code
                )
            else:
                # Reroute entire sample + all tests
                await conn.execute(
                    """UPDATE tat_sample
                       SET assigned_lab_id=$1, routing_reason=$2, updated_at=CURRENT_TIMESTAMP
                       WHERE id=$3""",
                    req.new_lab_id, f"Admin override: {req.reason}", req.sample_id
                )
                await conn.execute(
                    """UPDATE tat_test_instance
                       SET processing_lab_id=$1, routing_reason=$2, updated_at=CURRENT_TIMESTAMP
                       WHERE sample_id=$3 AND status NOT IN ('completed','cancelled')""",
                    req.new_lab_id, f"Admin override: {req.reason}", req.sample_id
                )
                # Update queue entry
                await conn.execute(
                    "UPDATE tat_lab_queue SET lab_id=$1, updated_at=CURRENT_TIMESTAMP WHERE sample_id=$2 AND status NOT IN ('completed','cancelled')",
                    req.new_lab_id, req.sample_id
                )

            # Audit log
            await conn.execute(
                """INSERT INTO tat_log
                   (sample_id, bill_id, event_type, triggered_by, notes, event_timestamp)
                   VALUES ($1, $2, 'routing_override', $3, $4, CURRENT_TIMESTAMP)""",
                req.sample_id, sample["bill_id"],
                user.email,
                f"Rerouted to Lab {req.new_lab_id} ({lab['lab_name']}): {req.reason}"
                + (f" [test: {req.test_code}]" if req.test_code else " [all tests]")
            )

    logger.info(
        "[OVERRIDE] routing sample_id=%d new_lab_id=%d test_code=%s by=%s",
        req.sample_id, req.new_lab_id, req.test_code, user.email
    )
    return {
        "success": True,
        "sample_id": req.sample_id,
        "new_lab_id": req.new_lab_id,
        "lab_name": lab["lab_name"],
        "test_code": req.test_code,
    }


# ── Admin Retry Failed Processing —————————————————————————————————————

class RetryRequest(BaseModel):
    sample_id: int
    reason: str


@actions_router.post("/override/retry")
async def retry_processing(
    req: RetryRequest,
    user: UserSession = Depends(require_role(['admin'])),
):
    """
    BUG-H3 FIX: Was returning 'not implemented'. Now re-enqueues the most recent
    failed webhook event for a sample so Celery retries processing it.
    """
    from app.pg_database import _pool

    # Find the most recent failed event for this sample
    row = await _pool.fetchrow("""
        SELECT e.id FROM tat_webhook_event e
        JOIN tat_sample s ON s.bill_id = e.internal_bill_id
        WHERE s.id = $1 AND e.status = 'failed'
        ORDER BY e.created_at DESC
        LIMIT 1
    """, req.sample_id)

    if not row:
        # Try finding any event linked by bill
        row = await _pool.fetchrow("""
            SELECT e.id FROM tat_webhook_event e
            JOIN tat_bill b ON b.id = e.internal_bill_id
            JOIN tat_sample s ON s.bill_id = b.id
            WHERE s.id = $1
            ORDER BY e.created_at DESC
            LIMIT 1
        """, req.sample_id)

    if not row:
        raise HTTPException(404, f"No processable webhook event found for sample {req.sample_id}")

    event_id = row["id"]

    # Reset event to receivable state and re-enqueue
    await _pool.execute(
        "UPDATE tat_webhook_event SET status='received', error_message=NULL, retry_count=0 WHERE id=$1",
        event_id
    )

    task = process_webhook_task.delay(event_id)
    logger.info(
        "[RETRY] sample_id=%d event_id=%d task_id=%s by=%s reason=%s",
        req.sample_id, event_id, task.id, user.email, req.reason
    )

    return {
        "success": True,
        "sample_id": req.sample_id,
        "event_id": event_id,
        "task_id": task.id,
        "message": "Event re-queued for processing",
    }


router = actions_router
