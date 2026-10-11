"""
app/services/kpi_service.py — KPI and outsource flow management.

Implements:
  1. Outsource flow tracking with vendor SLA management (PRD Section 20.3)
  2. Network-level KPI calculations (PRD Section 18.3)
  3. Lab-level KPI calculations (PRD Section 18.2)
  4. Customer KPI calculations (PRD Section 18.1)
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from app.core.pg_pool import pooled_connection
from app.utils.datetime_utils import get_naive_utc_now

logger = logging.getLogger("kpi_service")


def _pg():
    return pooled_connection()


def _now() -> datetime:
    return get_naive_utc_now()


# ── Outsource Flow Management ────────────────────────────────────────────────

def track_outsource_assignment(
    cur,
    test_instance_id: int,
    sample_id: int,
    bill_id: int,
    source_lab_id: Optional[int],
    destination_lab_id: Optional[int],
    vendor_name: str,
    predicted_eta: Optional[datetime] = None,
    outsource_buffer_mins: int = 0,
) -> int:
    """
    Create or update a processing assignment for outsourced test.
    
    Per PRD Section 20.3:
    - Assign outsource vendor
    - Add transport buffer to SLA
    - Track vendor SLA separately
    
    Returns processing_assignment_id.
    """
    now = _now()
    
    # Create processing assignment
    cur.execute("""
        INSERT INTO tat_processing_assignment
          (sample_id, bill_id, test_instance_id,
           source_lab_id, destination_lab_id, outsource_vendor_name,
           predicted_eta, route_reason, assignment_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'assigned')
        ON CONFLICT (test_instance_id) DO UPDATE
          SET destination_lab_id=EXCLUDED.destination_lab_id,
              outsource_vendor_name=EXCLUDED.outsource_vendor_name,
              predicted_eta=EXCLUDED.predicted_eta,
              assignment_status='assigned',
              updated_at=CURRENT_TIMESTAMP
        RETURNING id
    """, (sample_id, bill_id, test_instance_id, source_lab_id, destination_lab_id, vendor_name, predicted_eta, 'outsourced'))
    
    assignment_id = cur.fetchone()["id"]
    
    # Update test instance to mark as outsourced
    cur.execute("""
        UPDATE tat_test_instance SET is_outsourced=1, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (test_instance_id,))
    
    # Update SLA record with revised deadline including transport buffer
    if predicted_eta:
        revised_deadline = predicted_eta + timedelta(minutes=outsource_buffer_mins)
        cur.execute("""
            UPDATE tat_sla_record
            SET predicted_sla_deadline=%s,
                predicted_tat_mins=EXTRACT(EPOCH FROM (%s - collection_time)) / 60,
                revision_reason='Outsourced to ' || %s || ' with ' || %s || 'min buffer',
                updated_at=CURRENT_TIMESTAMP
            WHERE test_instance_id=%s
        """, (revised_deadline, revised_deadline, vendor_name, outsource_buffer_mins, test_instance_id))
    
    logger.info(
        "[OUTSOURCE] assignment_id=%d test_instance_id=%d vendor=%s eta=%s",
        assignment_id, test_instance_id, vendor_name, predicted_eta
    )
    
    return assignment_id


def get_vendor_performance(cur, vendor_name: str, days_back: int = 30) -> Dict:
    """
    Calculate outsource vendor performance metrics.
    
    Returns dict with:
      - total_tests: number of tests outsourced
      - completed_tests: number completed on time
      - avg_tat_mins: average turnaround time
      - sla_compliance_pct: % meeting SLA
      - avg_delay_mins: average delay (if breached)
    """
    since = _now() - timedelta(days=days_back)
    
    cur.execute("""
        SELECT
          COUNT(*) as total_tests,
          COUNT(*) FILTER (WHERE sr.is_original_breached = 0) as on_time_tests,
          AVG(sr.actual_tat_mins) as avg_tat_mins,
          AVG(GREATEST(0, sr.actual_tat_mins - sr.original_tat_mins)) as avg_delay_mins
        FROM tat_processing_assignment pa
        JOIN tat_sla_record sr ON pa.test_instance_id = sr.test_instance_id
        WHERE pa.outsource_vendor_name = %s
          AND sr.actual_completion_time >= %s
          AND sr.actual_completion_time IS NOT NULL
    """, (vendor_name, since))
    
    row = cur.fetchone()
    if not row or row["total_tests"] == 0:
        return {
            "vendor_name": vendor_name,
            "total_tests": 0,
            "completed_tests": 0,
            "sla_compliance_pct": 0.0,
            "avg_tat_mins": None,
            "avg_delay_mins": None,
        }
    
    compliance_pct = (row["on_time_tests"] / row["total_tests"] * 100) if row["total_tests"] > 0 else 0
    
    return {
        "vendor_name": vendor_name,
        "total_tests": row["total_tests"],
        "completed_tests": row["on_time_tests"],
        "sla_compliance_pct": round(compliance_pct, 2),
        "avg_tat_mins": round(row["avg_tat_mins"], 2) if row["avg_tat_mins"] else None,
        "avg_delay_mins": round(row["avg_delay_mins"], 2) if row["avg_delay_mins"] else None,
    }


# ── Network-level KPI Calculations ───────────────────────────────────────────

def calculate_network_kpis(cur, days_back: int = 7) -> Dict:
    """
    Calculate network-wide KPIs per PRD Section 18.3.
    
    Returns dict with:
      - transport_efficiency: avg transport TAT vs expected
      - routing_efficiency: % tests routed successfully on first attempt
      - outsource_performance: % of outsourced tests meeting SLA
      - sla_breach_distribution: breaches by status/reason
    """
    since = _now() - timedelta(days=days_back)
    
    # Transport efficiency: actual transport time vs bill-to-accession time
    cur.execute("""
        SELECT
          AVG(EXTRACT(EPOCH FROM (s.arrived_at_lab - b.bill_time)) / 60) as avg_transport_mins,
          COUNT(*) FILTER (WHERE s.arrived_at_lab IS NOT NULL) as samples_with_transport
        FROM tat_sample s
        JOIN tat_bill b ON s.bill_id = b.id
        WHERE s.arrived_at_lab >= %s AND b.bill_time >= %s
    """, (since, since))
    
    transport_row = cur.fetchone()
    avg_transport = transport_row["avg_transport_mins"] if transport_row else None
    
    # Routing efficiency: tests that required no rerouting
    cur.execute("""
        SELECT
          COUNT(DISTINCT ti.id) as total_tests,
          COUNT(DISTINCT ti.id) FILTER (WHERE ti.routing_reason = 'capability_match') as routed_optimally
        FROM tat_test_instance ti
        JOIN tat_bill b ON ti.bill_id = b.id
        WHERE ti.created_at >= %s
    """, (since,))
    
    routing_row = cur.fetchone()
    routing_pct = 0
    if routing_row and routing_row["total_tests"] > 0:
        routing_pct = (routing_row["routed_optimally"] / routing_row["total_tests"] * 100)
    
    # Outsource performance
    cur.execute("""
        SELECT
          COUNT(DISTINCT pa.test_instance_id) as total_outsourced,
          COUNT(DISTINCT pa.test_instance_id) FILTER (WHERE sr.is_original_breached = 0) as on_time_outsourced
        FROM tat_processing_assignment pa
        JOIN tat_sla_record sr ON pa.test_instance_id = sr.test_instance_id
        WHERE pa.updated_at >= %s AND sr.actual_completion_time IS NOT NULL
    """, (since,))
    
    outsource_row = cur.fetchone()
    outsource_pct = 0
    if outsource_row and outsource_row["total_outsourced"] > 0:
        outsource_pct = (outsource_row["on_time_outsourced"] / outsource_row["total_outsourced"] * 100)
    
    # SLA breach distribution
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE sr.is_original_breached = 1) as total_breaches,
          COUNT(*) FILTER (WHERE sr.is_original_breached = 1 AND pa.outsource_vendor_name IS NOT NULL) as outsource_breaches,
          AVG(sr.breach_by_mins) FILTER (WHERE sr.is_original_breached = 1) as avg_breach_mins
        FROM tat_sla_record sr
        LEFT JOIN tat_processing_assignment pa ON sr.test_instance_id = pa.test_instance_id
        WHERE sr.actual_completion_time >= %s
    """, (since,))
    
    breach_row = cur.fetchone()
    
    return {
        "period_days": days_back,
        "transport_efficiency": {
            "avg_transport_mins": round(avg_transport, 2) if avg_transport else None,
            "samples_analyzed": transport_row["samples_with_transport"] if transport_row else 0,
        },
        "routing_efficiency_pct": round(routing_pct, 2),
        "outsource_sla_compliance_pct": round(outsource_pct, 2),
        "sla_breach_distribution": {
            "total_breaches": breach_row["total_breaches"] if breach_row else 0,
            "outsource_breaches": breach_row["outsource_breaches"] if breach_row else 0,
            "avg_breach_mins": round(breach_row["avg_breach_mins"], 2) if breach_row and breach_row["avg_breach_mins"] else None,
        }
    }


# ── Lab-level KPI Calculations ───────────────────────────────────────────────

def calculate_lab_kpis(cur, lab_id: int, days_back: int = 7) -> Dict:
    """
    Calculate lab-specific KPIs per PRD Section 18.2.
    
    Returns dict with:
      - avg_lab_tat_mins: average lab turnaround time
      - edos_variance_pct: actual vs expected EDOS
      - processing_efficiency: tests completed within batch window
      - queue_pressure: samples waiting vs completed
    """
    since = _now() - timedelta(days=days_back)
    
    # Average lab TAT
    cur.execute("""
        SELECT
          AVG(sr.actual_tat_mins) as avg_tat,
          COUNT(*) as completed_tests
        FROM tat_sla_record sr
        JOIN tat_test_instance ti ON sr.test_instance_id = ti.id
        WHERE ti.processing_lab_id = %s
          AND sr.actual_completion_time >= %s
          AND sr.actual_completion_time IS NOT NULL
    """, (lab_id, since))
    
    tat_row = cur.fetchone()
    
    # EDOS variance
    cur.execute("""
        SELECT
          le.committed_tat_hours,
          AVG(EXTRACT(EPOCH FROM (ti.report_date - s.arrived_at_lab)) / 3600) as actual_tat_hours,
          COUNT(*) as test_count
        FROM tat_lab_edos le
        JOIN tat_test_instance ti ON le.test_code = ti.test_code
        JOIN tat_sample s ON ti.sample_id = s.id
        WHERE le.lab_id = %s
          AND ti.report_date >= %s
          AND ti.processing_lab_id = %s
        GROUP BY le.test_code, le.committed_tat_hours
    """, (lab_id, since, lab_id))
    
    edos_variance_rows = cur.fetchall()
    total_variance = 0
    variance_count = 0
    for row in edos_variance_rows:
        if row["committed_tat_hours"] and row["actual_tat_hours"]:
            variance = ((row["actual_tat_hours"] - row["committed_tat_hours"]) / row["committed_tat_hours"] * 100)
            total_variance += variance
            variance_count += 1
    
    avg_variance = (total_variance / variance_count) if variance_count > 0 else 0
    
    # Queue pressure
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE lq.status NOT IN ('completed', 'skipped')) as pending_items,
          COUNT(*) FILTER (WHERE lq.status IN ('completed', 'skipped')) as completed_items
        FROM tat_lab_queue lq
        WHERE lq.lab_id = %s AND lq.created_at >= %s
    """, (lab_id, since))
    
    queue_row = cur.fetchone()
    
    return {
        "lab_id": lab_id,
        "period_days": days_back,
        "avg_lab_tat_mins": round(tat_row["avg_tat"], 2) if tat_row and tat_row["avg_tat"] else None,
        "completed_tests": tat_row["completed_tests"] if tat_row else 0,
        "edos_variance_pct": round(avg_variance, 2),
        "queue_metrics": {
            "pending_items": queue_row["pending_items"] if queue_row else 0,
            "completed_items": queue_row["completed_items"] if queue_row else 0,
        }
    }


# ── Customer KPI Calculations ────────────────────────────────────────────────

def calculate_customer_kpis(cur, org_id: Optional[int] = None, days_back: int = 7) -> Dict:
    """
    Calculate customer/org-level KPIs per PRD Section 18.1.
    
    If org_id is None, calculates network-wide customer KPIs.
    
    Returns dict with:
      - sla_compliance_pct: % tests meeting original SLA
      - avg_overall_tat_mins: average end-to-end TAT
      - delayed_reports_count: number of breached SLAs
      - early_completion_count: completed ahead of schedule
    """
    since = _now() - timedelta(days=days_back)
    
    where_org = ""
    params = [since]
    if org_id:
        where_org = "AND b.org_id = %s"
        params.append(org_id)
    
    cur.execute(f"""
        SELECT
          COUNT(*) as total_tests,
          COUNT(*) FILTER (WHERE sr.is_original_breached = 0) as on_time_tests,
          AVG(sr.actual_tat_mins) as avg_tat,
          COUNT(*) FILTER (WHERE sr.actual_tat_mins < sr.original_tat_mins) as early_completion
        FROM tat_sla_record sr
        JOIN tat_test_instance ti ON sr.test_instance_id = ti.id
        JOIN tat_bill b ON sr.bill_id = b.id
        WHERE sr.actual_completion_time >= %s {where_org}
          AND sr.actual_completion_time IS NOT NULL
    """, params)
    
    kpi_row = cur.fetchone()
    
    compliance_pct = 0
    if kpi_row and kpi_row["total_tests"] > 0:
        compliance_pct = (kpi_row["on_time_tests"] / kpi_row["total_tests"] * 100)
    
    return {
        "org_id": org_id,
        "period_days": days_back,
        "sla_compliance_pct": round(compliance_pct, 2),
        "avg_overall_tat_mins": round(kpi_row["avg_tat"], 2) if kpi_row and kpi_row["avg_tat"] else None,
        "delayed_tests_count": (kpi_row["total_tests"] - kpi_row["on_time_tests"]) if kpi_row else 0,
        "early_completion_count": kpi_row["early_completion"] if kpi_row else 0,
    }


# ── Batch KPI Metrics ────────────────────────────────────────────────────────

def calculate_batch_metrics(cur, lab_id: int, batch_date: datetime) -> Dict:
    """
    Calculate batch-specific metrics for a lab on a given date.
    
    Useful for post-batch analysis and performance tracking.
    """
    cur.execute("""
        SELECT
          COUNT(*) as total_samples,
          COUNT(*) FILTER (WHERE lba.status = 'processed') as processed_samples,
          COUNT(*) FILTER (WHERE lba.status = 'missed') as missed_samples,
          COUNT(*) FILTER (WHERE lba.status = 'reassigned') as reassigned_samples,
          COUNT(DISTINCT ti.test_code) as unique_tests
        FROM tat_lab_batch_assignment lba
        LEFT JOIN tat_sample s ON lba.sample_id = s.id
        LEFT JOIN tat_test_instance ti ON s.id = ti.sample_id
        WHERE lba.lab_id = %s AND DATE(lba.batch_time) = %s
    """, (lab_id, batch_date))
    
    batch_row = cur.fetchone()
    
    return {
        "lab_id": lab_id,
        "batch_date": str(batch_date.date()),
        "total_samples": batch_row["total_samples"] if batch_row else 0,
        "processed": batch_row["processed_samples"] if batch_row else 0,
        "missed": batch_row["missed_samples"] if batch_row else 0,
        "reassigned": batch_row["reassigned_samples"] if batch_row else 0,
        "unique_tests": batch_row["unique_tests"] if batch_row else 0,
    }
