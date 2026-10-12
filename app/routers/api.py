"""
app/routers/api.py — REST API routes backed by PostgreSQL.

Routers:
  /api/samples/*      — Sample read API
  /api/bills/*        — Bill read API
  /api/labs/*         — Lab + queue read API
  /api/stats          — Dashboard metrics
  /api/notifications  — Audit log events (TAT/breach alerts)
  /api/tests/*        — EDOS test catalog (unchanged)
  /api/accession      — Legacy accession endpoint
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, Depends

from app import pg_database as pgdb
from app.core.auth import get_current_user, require_role, UserSession, get_signature
from app.edos_loader import get_all_records, lookup_test, search_records
from app.models import AccessionRequest, LoginRequest

logger = logging.getLogger("routers.api")


# ── Samples ───────────────────────────────────────────────────────────────────
samples_router = APIRouter(prefix="/api/samples", tags=["Samples"], dependencies=[Depends(get_current_user)])


@samples_router.get("")
async def list_samples(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit:  int           = Query(50, ge=1, le=500),
    offset: int           = Query(0, ge=0),
):
    samples = await pgdb.list_samples(status=status, limit=limit, offset=offset)
    return {"total": len(samples), "samples": samples}


@samples_router.get("/{sample_id}")
async def get_sample_detail(sample_id: str):
    # Try parsing as internal integer ID first
    internal_id: Optional[int] = None
    try:
        internal_id = int(sample_id)
    except ValueError:
        pass

    if internal_id is not None:
        sample = await pgdb.get_sample(internal_id)
    else:
        # If not an integer, lookup by accession number
        sample = await pgdb.get_sample_by_accession(sample_id)
    
    if not sample:
        raise HTTPException(404, f"Sample '{sample_id}' not found")

    actual_id = sample["id"]
    tests       = await pgdb.list_test_instances(actual_id)
    queue_entry = await pgdb.get_queue_entry_for_sample(actual_id)
    eta         = await pgdb.get_eta(actual_id)
    logs        = await pgdb.list_logs(actual_id, limit=20)

    return {
        "sample":      sample,
        "tests":       tests,
        "queue_entry": queue_entry,
        "eta":         eta,
        "recent_logs": logs,
    }



@samples_router.get("/{sample_id}/eta-history")
async def get_sample_eta_history(
    sample_id: str,
    user: UserSession = Depends(require_role(["admin", "doctor", "lab"])),
):
    """
    ETA version audit trail — all historical ETA snapshots for a sample.
    Source: tat_eta_history (snapshotted each time ETA is recalculated).
    RBAC: admin, doctor, lab.
    """
    internal_id: Optional[int] = None
    try:
        internal_id = int(sample_id)
    except ValueError:
        pass

    if internal_id is not None:
        sample = await pgdb.get_sample(internal_id)
    else:
        sample = await pgdb.get_sample_by_accession(sample_id)

    if not sample:
        raise HTTPException(404, f"Sample '{sample_id}' not found")

    actual_id = sample["id"]
    from app.pg_database import _pool
    rows = await _pool.fetch(
        """
        SELECT
            h.id,
            h.version,
            h.collection_time,
            h.arrival_time_at_lab,
            h.estimated_start_time,
            h.estimated_end_time,
            h.queue_wait_mins,
            h.lab_eta_mins,
            h.total_eta_mins,
            h.predefined_tat_mins,
            h.is_tat_breached,
            h.breach_by_mins,
            h.recalculation_reason,
            h.triggered_by,
            h.snapshotted_at
        FROM tat_eta_history h
        WHERE h.sample_id = $1
        ORDER BY h.version ASC, h.snapshotted_at ASC
        """,
        actual_id,
    )
    return {
        "sample_id": actual_id,
        "version_count": len(rows),
        "eta_history": [dict(r) for r in rows],
    }


@samples_router.get("/{sample_id}/report")
async def get_sample_report(
    sample_id: str,
    user: UserSession = Depends(require_role(["admin", "doctor", "lab"])),
):
    internal_id: Optional[int] = None
    try:
        internal_id = int(sample_id)
    except ValueError:
        pass

    sample = await pgdb.get_sample(internal_id) if internal_id is not None else await pgdb.get_sample_by_accession(sample_id)
    if not sample:
        raise HTTPException(404, f"Sample '{sample_id}' not found")

    if user.role == "lab" and user.lab_id and sample.get("assigned_lab_id") not in (None, user.lab_id):
        raise HTTPException(403, "Forbidden")

    actual_id = sample["id"]
    tests = await pgdb.list_test_instances(actual_id)
    eta = await pgdb.get_eta(actual_id)
    logs = await pgdb.list_logs(actual_id, limit=100)

    from app.pg_database import _pool
    pdf_rows = await _pool.fetch(
        """
        SELECT external_report_id, external_test_id, test_code, report_date,
               approval_date, is_signed, is_amended, storage_path
        FROM tat_report_pdf_raw
        WHERE sample_accession_no = $1
           OR external_report_id IN (
                SELECT external_report_id
                FROM tat_test_instance
                WHERE sample_id = $2 AND external_report_id IS NOT NULL
           )
        ORDER BY report_date DESC NULLS LAST, id DESC
        """,
        sample.get("accession_no"),
        actual_id,
    )

    return {
        "sample": sample,
        "tests": tests,
        "eta": eta,
        "timeline": logs,
        "pdf_reports": [dict(r) for r in pdf_rows],
    }


# ── Bills ─────────────────────────────────────────────────────────────────────
bills_router = APIRouter(prefix="/api/bills", tags=["Bills"], dependencies=[Depends(get_current_user)])


@bills_router.get("")
async def list_bills(
    limit:  int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    bills = await pgdb.list_bills(limit=limit, offset=offset)
    return {"total": len(bills), "bills": bills}


@bills_router.get("/external/{external_bill_id}")
async def get_bill_by_external(external_bill_id: int):
    bill = await pgdb.get_bill_by_external(external_bill_id)
    if not bill:
        raise HTTPException(404, f"Bill (external_id={external_bill_id}) not found")
    return bill


@bills_router.get("/{bill_id}")
async def get_bill(bill_id: int):
    bill = await pgdb.get_bill(bill_id)
    if not bill:
        raise HTTPException(404, f"Bill {bill_id} not found")
    return bill


# ── Labs ──────────────────────────────────────────────────────────────────────
labs_router = APIRouter(prefix="/api/labs", tags=["Labs"], dependencies=[Depends(get_current_user)])


@labs_router.get("")
async def list_labs():
    labs = await pgdb.get_all_labs()
    return {"total": len(labs), "labs": labs}


@labs_router.get("/{lab_id}")
async def get_lab(lab_id: int):
    lab = await pgdb.get_lab_with_queue_depth(lab_id)
    if not lab:
        raise HTTPException(404, f"Lab {lab_id} not found")
    return lab


@labs_router.get("/{lab_id}/queue")
async def get_lab_queue(
    lab_id: int,
    limit:  int = Query(50, ge=1, le=200),
):
    entries = await pgdb.get_lab_queue(lab_id, limit=limit)
    return {"lab_id": lab_id, "total": len(entries), "queue": entries}


# ── Stats ─────────────────────────────────────────────────────────────────────
stats_router = APIRouter(prefix="/api", tags=["Stats"], dependencies=[Depends(get_current_user)])


@stats_router.get("/stats")
async def get_stats():
    stats = await pgdb.get_dashboard_stats()
    return {
        **stats,
        # frontend-compatible aliases
        "sla_breaches":           stats.get("tat_breaches", 0),
        "completed":              stats.get("completed_samples", 0),
        "unread_notifications":   stats.get("tat_breaches", 0),   # drives the radar card
        "total_tests_in_catalog": len(get_all_records()),
    }


# ── Notifications (audit log alert events) ────────────────────────────────────
notif_router = APIRouter(prefix="/api/notifications", tags=["Notifications"], dependencies=[Depends(get_current_user)])


@notif_router.get("")
async def list_notifications(
    sample_id:   Optional[int] = Query(None),
    limit:       int           = Query(50, ge=1, le=200),
):
    """Returns recent TAT/breach/alert events from tat_log."""
    if sample_id:
        logs = await pgdb.list_logs(sample_id, limit=limit)
    else:
        # Global latest alert events
        from app.pg_database import _pool
        rows = await _pool.fetch(
            """SELECT * FROM tat_log
               WHERE event_type IN ('tat_breach_alert','lab_downtime_alert','sample_delayed','processing_error')
               ORDER BY created_at DESC LIMIT $1""",
            limit,
        )
        logs = [dict(r) for r in rows]
    return {"total": len(logs), "notifications": logs}


@notif_router.get("/all")
async def get_full_audit_log(
    limit:  int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Returns a full global audit log of all system events."""
    from app.pg_database import _pool
    rows = await _pool.fetch(
        """SELECT l.*, b.patient_name, b.external_bill_id 
           FROM tat_log l
           LEFT JOIN tat_bill b ON b.id = l.bill_id
           ORDER BY l.event_timestamp DESC 
           LIMIT $1 OFFSET $2""",
        limit, offset
    )
    # Get total count for pagination
    total = await _pool.fetchval("SELECT COUNT(*) FROM tat_log")
    logs = [dict(r) for r in rows]
    return {"total": total, "logs": logs}

# ── Test catalog (EDOS — unchanged) ──────────────────────────────────────────
tests_router = APIRouter(prefix="/api/tests", tags=["Tests"])
test_tracking_router = APIRouter(prefix="/api/v1/tests", tags=["Test Tracking"])


@tests_router.get("")
async def list_tests(
    q:     Optional[str] = Query(None),
    page:  int           = Query(1, ge=1),
    limit: int           = Query(25, ge=1, le=100),
):
    results = search_records(q) if q else get_all_records()
    total   = len(results)
    start   = (page - 1) * limit
    return {"total": total, "page": page, "limit": limit, "tests": results[start:start + limit]}


@tests_router.get("/{test_code}")
async def get_test(test_code: str):
    edos = lookup_test(test_code=test_code.upper())
    if not edos:
        raise HTTPException(404, f"Test '{test_code}' not found in EDOS catalog")
    # Also return DB config if available
    db_config = await pgdb.get_test_config(test_code.upper())
    return {"test": edos, "db_config": db_config}


@test_tracking_router.get("")
async def list_tracked_tests(
    user:   UserSession   = Depends(require_role(["admin", "lab", "doctor"])),
    q:      Optional[str] = Query(None, description="Search patient name, bill ID, or patient ID"),
    status: Optional[str] = Query(None, description="Filter by test status"),
    limit:  int           = Query(20, ge=1, le=100),
    offset: int           = Query(0, ge=0),
):
    # Lab users see only tests processed by their lab
    lab_id = user.lab_id if user.role == "lab" else None
    return await pgdb.list_tracked_tests(q=q, status=status, lab_id=lab_id, limit=limit, offset=offset)


@test_tracking_router.get("/{test_id}")
async def get_tracked_test(test_id: int):
    test = await pgdb.get_tracked_test_detail(test_id)
    if not test:
        raise HTTPException(404, f"Test {test_id} not found")
    return test


# ── Accession (legacy manual entry) ──────────────────────────────────────────
accession_router = APIRouter(prefix="/api", tags=["Accession"], dependencies=[Depends(get_current_user)])


@accession_router.post("/accession")
async def create_accession(req: AccessionRequest):
    """
    Legacy manual sample registration (for direct API use).
    Validates against EDOS catalog but does NOT trigger the webhook pipeline.
    Use POST /api/webhook with BILL_UPDATE for production ingest.
    """
    edos = lookup_test(test_code=req.test_code)
    if not edos:
        raise HTTPException(400, f"Test code '{req.test_code}' not in EDOS catalog")
    return {
        "message": "Test code validated. Use POST /api/webhook with webhook_type=BILL_UPDATE for full TAT tracking.",
        "test":    edos,
    }


# ── Auth ─────────────────────────────────────────────────────────────────────

@accession_router.post("/login", tags=["Auth"])
async def login(req: LoginRequest, response: Response):
    """
    Backend-verified login.
    Hardcoded password for demo/v2 as per frontend logic.
    In v3, this will check hashed passwords in tat_user.
    """
    if req.password != "aspira123":
        raise HTTPException(401, "Invalid password")
    
    # Verify user exists
    from app.pg_database import _pool
    user = await _pool.fetchrow("SELECT email FROM tat_user WHERE email=$1 AND is_active=1", req.email)
    if not user:
        raise HTTPException(401, "User not found or inactive")
    
    # Set signed cookies
    sig = get_signature(req.email)
    response.set_cookie(key="aspira_email", value=req.email, httponly=True)
    response.set_cookie(key="aspira_sig",   value=sig,       httponly=True)
    response.set_cookie(key="aspira_auth",  value="true",     httponly=False) # for frontend compat
    
    return {"status": "success", "message": "Logged in successfully"}


# ── New endpoints ─────────────────────────────────────────────────────────────

@stats_router.get("/stats/labs")
async def get_lab_stats():
    """Per-lab queue depth and batch counts."""
    data = await pgdb.get_lab_stats()
    return {"labs": data}


@stats_router.get("/stats/sla")
async def get_sla_stats():
    """SLA breach rate by client type (walk_in / corporate / hospital)."""
    data = await pgdb.get_sla_stats()
    return {"sla_by_client_type": data}


@labs_router.get("/{lab_id}/batches")
async def get_lab_batches(
    lab_id: int,
    limit:  int = Query(50, ge=1, le=200),
):
    """Batch schedule + recent assignments for a lab."""
    schedule    = await pgdb.get_batch_schedule(lab_id)
    assignments = await pgdb.get_batch_assignments(lab_id, limit=limit)
    return {"lab_id": lab_id, "schedule": schedule, "assignments": assignments}

# ── Hot pipeline cache endpoint ───────────────────────────────────────────────

@stats_router.get("/pipeline/hot")
async def get_hot_pipeline(
    offset: int = Query(0,  ge=0),
    limit:  int = Query(50, ge=1, le=500),
):
    """
    Sub-millisecond read from Redis hot pipeline cache.
    Returns the most recent N sample records (newest first).
    Falls back to empty list if Redis is unavailable.
    """
    from app.core.hot_cache import get_page
    raw = get_page(offset=offset, limit=limit)
    return Response(content=raw, media_type="application/json")

# ── Export all routers ───────────────────────────────────────────────────────────
router = APIRouter()
router.include_router(samples_router)
router.include_router(bills_router)
router.include_router(labs_router)
router.include_router(stats_router)
router.include_router(notif_router)
router.include_router(tests_router)
router.include_router(test_tracking_router)
router.include_router(accession_router)

# Individual router exports for main.py
samples_router = samples_router
bills_router = bills_router
labs_router = labs_router
stats_router = stats_router
notif_router = notif_router
tests_router = tests_router
test_tracking_router = test_tracking_router
accession_router = accession_router
