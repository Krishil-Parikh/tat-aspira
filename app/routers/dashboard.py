"""
app/routers/dashboard.py — Dashboard, timeline, and KPI endpoints.

All data is derived from tables written by the existing webhook processor.
No new webhook flows are created here.

Endpoints:
  GET /api/dashboard/admin            — Admin: system-wide stats, breaches, unassigned
  GET /api/dashboard/lab              — Lab user: own lab work queue + KPI
  GET /api/labs/{lab_id}/kpi          — Per-lab KPI metrics (RBAC enforced)
  GET /api/samples/{sample_id}/timeline — Chronological timeline from tat_log
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from app import pg_database as pgdb
from app.core.auth import get_current_user, require_role, UserSession

logger = logging.getLogger("routers.dashboard")

dashboard_router = APIRouter(prefix="/api", tags=["Dashboard"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Timeline ──────────────────────────────────────────────────────────────────

@dashboard_router.get("/samples/{sample_id}/timeline")
async def get_sample_timeline(
    sample_id: int,
    user: UserSession = Depends(require_role(["admin", "lab", "doctor", "logistics"])),
):
    """
    Chronological timeline of all webhook-generated events for a sample.
    Source: tat_log — written inside every webhook handler.

    RBAC: Lab users see only samples assigned to their lab.
    """
    # RBAC: lab users check that this sample belongs to their lab
    if user.role == "lab" and user.lab_id:
        sample = await pgdb.get_sample(sample_id)
        if not sample:
            raise HTTPException(404, f"Sample {sample_id} not found")
        if sample.get("assigned_lab_id") != user.lab_id:
            raise HTTPException(403, "Forbidden: This sample is not assigned to your lab")

    timeline = await pgdb.get_sample_timeline(sample_id)
    if not timeline:
        # May be valid (no events yet) or not found
        sample = await pgdb.get_sample(sample_id)
        if not sample:
            raise HTTPException(404, f"Sample {sample_id} not found")

    return {
        "sample_id": sample_id,
        "event_count": len(timeline),
        "timeline": timeline,
    }


# ── Lab KPI ───────────────────────────────────────────────────────────────────

@dashboard_router.get("/labs/{lab_id}/kpi")
async def get_lab_kpi(
    lab_id: int,
    user: UserSession = Depends(require_role(["admin", "lab"])),
):
    """
    KPI metrics for a specific lab.
    Metrics: total tests, completed, pending, cancelled, TAT breaches,
             avg actual TAT, avg expected TAT, SLA %, batch counts, queue depth.

    Source: tat_test_instance, tat_eta, tat_lab_batch_assignment, tat_lab_queue.
    All written by webhook processor.

    RBAC: Lab users can only see their own lab.
    """
    # RBAC: lab role can only see their own lab
    if user.role == "lab" and user.lab_id != lab_id:
        logger.warning("Lab user %s attempted to view KPI for lab %d", user.email, lab_id)
        raise HTTPException(403, "Forbidden: You can only view your assigned lab's KPI")

    kpi = await pgdb.get_lab_kpi(lab_id)
    if not kpi:
        raise HTTPException(404, f"Lab {lab_id} not found")

    return kpi


# ── Admin Dashboard ───────────────────────────────────────────────────────────

@dashboard_router.get("/dashboard/admin")
async def get_admin_dashboard(
    user: UserSession = Depends(require_role(["admin"])),
):
    """
    Admin-only dashboard. System-wide view built from webhook-generated data.

    Returns:
      - stats: total/active/completed/delayed samples + TAT breaches
      - labs: per-lab queue depth + batch status
      - sla_by_client: SLA breach rate by client type (walk_in/corporate)
      - recent_breaches: last 10 TAT breach events from tat_log
      - unassigned_samples: samples that failed routing
    """
    data = await pgdb.get_admin_dashboard()
    return data


# ── Lab Dashboard ─────────────────────────────────────────────────────────────

@dashboard_router.get("/dashboard/lab")
async def get_lab_dashboard(
    user: UserSession = Depends(require_role(["lab", "admin"])),
):
    """
    Lab-scoped dashboard. Shows only data for the authenticated user's lab.

    RBAC: Lab users see only their lab. Admin can specify ?lab_id=N
    via the /api/labs/{lab_id}/kpi endpoint instead.

    Returns:
      - kpi: lab KPI metrics
      - work_queue: active samples + tests pending in this lab
      - recent_completions: last 20 completed tests
    """
    # Derive lab_id from authenticated session (never from frontend)
    if user.role == "lab":
        if not user.lab_id:
            raise HTTPException(400, "Lab user session has no lab_id assigned. Contact admin.")
        lab_id = user.lab_id
    else:
        # Admin calling /dashboard/lab — show the first lab as a demo
        # Admin should use /api/labs/{lab_id}/kpi for specific lab
        raise HTTPException(
            400,
            "Admins should use GET /api/labs/{lab_id}/kpi for lab-specific data. "
            "Use GET /api/dashboard/admin for the full system view."
        )

    data = await pgdb.get_lab_dashboard(lab_id)
    return data


# ── Test-type SLA Analytics ───────────────────────────────────────────────────

@dashboard_router.get("/analytics/tests")
async def get_test_analytics(
    user: UserSession = Depends(require_role(["admin", "lab"])),
):
    """
    Per-test-type SLA analytics: avg TAT, SLA%, completed, delayed.
    Includes per-lab breakdown per test code.
    Source: tat_test_instance + tat_eta — all webhook-written.

    RBAC: Both admin and lab role can view (lab sees all test types as reference).
    """
    data = await pgdb.get_test_analytics()
    return data


@dashboard_router.get("/catalog/master")
async def get_master_catalog(
    user: UserSession = Depends(require_role(["admin", "lab"])),
):
    """
    Returns the full master test catalog (definitions).
    Unlike analytics, this shows every test in tat_test_type_config.
    """
    from app.pg_database import _pool
    rows = await _pool.fetch("""
        SELECT * FROM tat_test_type_config
        ORDER BY department_name, test_name
    """)
    return {"success": True, "tests": [dict(r) for r in rows]}


# ── Lab Management Dashboard KPIs (NEW) ───────────────────────────────────────

@dashboard_router.get("/dashboard/admin/lab-metrics")
async def get_lab_management_metrics(
    user: UserSession = Depends(require_role(["admin"])),
):
    """
    Overall system KPIs for lab management dashboard.
    Nine key metrics for operations control center:
    
    1. Total Active Labs - count of available labs
    2. Total Tests Today - tests created today
    3. Total In Progress - tests in pending/processing
    4. Total Completed - tests completed today
    5. Delayed Tests - tests with TAT breach
    6. SLA Compliance % - percentage of on-time completion
    7. Avg Processing TAT - average actual TAT in minutes
    8. Queue Load - active queue entries
    9. Avg Queue Wait - average wait time in queue
    
    All metrics are real-time, calculated from webhook-written tables.
    Admin-only endpoint (RBAC enforced).
    """
    metrics = await pgdb.get_lab_management_metrics()
    return {
        "success": True,
        "timestamp": _utcnow_iso(),
        "metrics": metrics,
    }


@dashboard_router.get("/dashboard/admin/labs")
async def get_labs_with_metrics(
    user: UserSession = Depends(require_role(["admin"])),
):
    """
    Enhanced lab list with per-lab metrics and status indicators.
    
    Per-lab data includes:
    - queue_size: active queue entries
    - avg_tat_mins: average actual turnaround time
    - sla_percent: SLA compliance percentage
    - delayed_tests: count of delayed tests
    - active_batches: pending batch assignments
    - utilization_percent: queue utilization vs capacity
    - status: 'healthy' | 'overloaded' | 'delayed' | 'at_risk'
    
    Status logic:
    - healthy: SLA > 90% AND queue size reasonable
    - overloaded: queue exceeds threshold OR utilization > 80%
    - delayed: has delayed tests
    - at_risk: SLA declining but not yet delayed
    
    Admin-only endpoint (RBAC enforced).
    """
    labs = await pgdb.get_labs_with_metrics()
    return {
        "success": True,
        "timestamp": _utcnow_iso(),
        "labs": labs,
        "total": len(labs),
    }


# ── Network KPI Endpoints (Per PRD Section 18) ────────────────────────────────

@dashboard_router.get("/analytics/network-kpis")
async def get_network_kpis(
    user: UserSession = Depends(require_role(["admin"])),
    period_days: int = 7,
):
    """
    Network-wide KPI calculations per PRD Section 18.3.
    
    Returns:
      - transport_efficiency: avg transport TAT vs expected
      - routing_efficiency: % of successful local routing
      - outsource_performance: vendor SLA compliance
      - sla_breach_distribution: breaches by type
    
    Admin-only (strategic operations view).
    """
    from app.services.kpi_service import calculate_network_kpis
    from app.core.pg_pool import pooled_connection

    def _sync():
        with pooled_connection() as conn:
            cur = conn.cursor()
            return calculate_network_kpis(cur, days_back=period_days)

    kpis = await asyncio.to_thread(_sync)

    return {
        "success": True,
        "period_days": period_days,
        "kpis": kpis,
    }


@dashboard_router.get("/analytics/customer-kpis")
async def get_customer_kpis(
    user: UserSession = Depends(require_role(["admin"])),
    org_id: int = None,
    period_days: int = 7,
):
    """
    Customer/org-level KPIs per PRD Section 18.1.
    
    If org_id is None, returns network-wide customer view.
    If org_id is specified, returns metrics for that organization.
    
    Returns:
      - sla_compliance_pct: % tests meeting SLA
      - avg_overall_tat_mins: end-to-end TAT
      - delayed_tests_count: number of breaches
      - early_completion_count: tests ahead of schedule
    """
    from app.services.kpi_service import calculate_customer_kpis
    from app.core.pg_pool import pooled_connection

    def _sync():
        with pooled_connection() as conn:
            cur = conn.cursor()
            return calculate_customer_kpis(cur, org_id=org_id, days_back=period_days)

    kpis = await asyncio.to_thread(_sync)

    return {
        "success": True,
        "org_id": org_id,
        "period_days": period_days,
        "kpis": kpis,
    }


@dashboard_router.get("/analytics/vendor-performance")
async def get_vendor_performance(
    user: UserSession = Depends(require_role(["admin"])),
    vendor_name: str = None,
    period_days: int = 30,
):
    """
    Outsource vendor performance tracking per PRD Section 20.3.
    
    If vendor_name is specified, returns metrics for that vendor.
    If None, returns all vendors' performance summary.
    
    Returns:
      - total_tests: tests routed to vendor
      - completed_tests: tests completed
      - avg_tat_mins: average turnaround
      - sla_compliance_pct: % meeting SLA
      - avg_delay_mins: average delay when breached
    """
    from app.services.kpi_service import get_vendor_performance
    from app.core.pg_pool import pooled_connection

    if vendor_name:
        def _sync_one():
            with pooled_connection() as conn:
                cur = conn.cursor()
                return get_vendor_performance(cur, vendor_name, days_back=period_days)

        perf = await asyncio.to_thread(_sync_one)
        return {
            "success": True,
            "vendor_name": vendor_name,
            "period_days": period_days,
            "performance": perf,
        }
    else:
        def _sync_all():
            with pooled_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT DISTINCT outsource_vendor_name
                    FROM tat_lab_edos
                    WHERE is_outsourced = 1 AND outsource_vendor_name IS NOT NULL
                    ORDER BY outsource_vendor_name
                """)
                vendors = [row[0] for row in cur.fetchall()]

            all_perf = {}
            for vendor in vendors:
                with pooled_connection() as conn2:
                    cur2 = conn2.cursor()
                    all_perf[vendor] = get_vendor_performance(cur2, vendor, days_back=period_days)
            return vendors, all_perf

        vendors, all_perf = await asyncio.to_thread(_sync_all)
        return {
            "success": True,
            "vendors": all_perf,
            "period_days": period_days,
            "vendor_count": len(vendors),
        }


@dashboard_router.get("/analytics/bill-status/{bill_id}")
async def get_bill_status_detail(
    bill_id: int,
    user: UserSession = Depends(require_role(["admin", "lab", "doctor"])),
):
    """
    Computed bill status using dynamic aggregation view (v_bill_status).
    
    Per PRD Section 15.2:
      - PENDING: all tests pending
      - PARTIAL: some tests complete
      - COMPLETED: all tests complete
      - ACTION_REQUIRED: if redraw exists
    
    Also shows test completion breakdown and SLA compliance.
    """
    from app.core.pg_pool import pooled_connection

    def _sync():
        with pooled_connection() as conn:
            cur = conn.cursor()

            # Get bill basic info
            cur.execute("""
                SELECT id, external_bill_id, patient_name, bill_time, bill_status_type
                FROM tat_bill WHERE id = %s
            """, (bill_id,))
            bill = cur.fetchone()
            if not bill:
                return None, None, None

            # C1 FIX: v_bill_status view is commented out in schema (the redraw
            # column lives on tat_sample, not tat_test_instance).  Compute the
            # same result inline so the endpoint never touches the missing view.
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE ti.status NOT IN ('cancelled')
                    ) AS active_tests,
                    COUNT(*) FILTER (
                        WHERE ti.status = 'completed'
                    ) AS completed_tests,
                    -- redraw flag lives on tat_sample, join once
                    MAX(s.redraw::int) AS has_redraw,
                    CASE
                        WHEN MAX(s.redraw::int) > 0
                            THEN 'ACTION_REQUIRED'
                        WHEN COUNT(*) FILTER (
                                 WHERE ti.status NOT IN ('cancelled')
                             ) = 0
                            THEN 'PENDING'
                        WHEN COUNT(*) FILTER (WHERE ti.status = 'completed')
                             >= COUNT(*) FILTER (
                                    WHERE ti.status NOT IN ('cancelled')
                                )
                            THEN 'COMPLETED'
                        WHEN COUNT(*) FILTER (WHERE ti.status = 'completed') > 0
                            THEN 'PARTIAL'
                        ELSE 'PENDING'
                    END AS computed_status
                FROM tat_test_instance ti
                JOIN tat_sample s ON s.id = ti.sample_id
                WHERE ti.bill_id = %s
            """, (bill_id,))
            status = cur.fetchone()

            # Get test-level breakdown
            cur.execute("""
                SELECT
                  ti.id, ti.test_code, ti.test_name, ti.status,
                  sr.original_sla_deadline, sr.actual_completion_time,
                  sr.is_original_breached
                FROM tat_test_instance ti
                LEFT JOIN tat_sla_record sr ON ti.id = sr.test_instance_id
                WHERE ti.bill_id = %s AND ti.is_active = 1
                ORDER BY ti.cycle_number, ti.created_at
            """, (bill_id,))

            tests = []
            for row in cur.fetchall():
                tests.append({
                    "test_id": row["id"],
                    "test_code": row["test_code"],
                    "test_name": row["test_name"],
                    "status": row["status"],
                    "sla_deadline": str(row["original_sla_deadline"]) if row["original_sla_deadline"] else None,
                    "completed_at": str(row["actual_completion_time"]) if row["actual_completion_time"] else None,
                    "sla_breached": bool(row["is_original_breached"]),
                })
            return bill, status, tests

    bill, status, tests = await asyncio.to_thread(_sync)
    if bill is None:
        raise HTTPException(404, f"Bill {bill_id} not found")

    return {
        "success": True,
        "bill": {
            "id": bill["external_bill_id"],
            "patient_name": bill["patient_name"],
            "bill_time": str(bill["bill_time"]) if bill["bill_time"] else None,
            "stored_status": bill["bill_status_type"],
        },
        "computed_status": status["computed_status"] if status else "UNKNOWN",
        "breakdown": {
            "active_tests": status["active_tests"] if status else 0,
            "completed_tests": status["completed_tests"] if status else 0,
            "redraw_count": status["has_redraw"] if status else 0,
        },
        "tests": tests,
    }

