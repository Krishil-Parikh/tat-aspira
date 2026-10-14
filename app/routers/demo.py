"""
app/routers/demo.py — One-call view of a bill's journey across labs.

GET /api/demo/journey/{external_bill_id} returns, per sample (tube) and per test, where
the test was collected, which lab processes it and why, when it arrived at that lab, and
its ETA — the multi-lab picture that is otherwise spread across bills, samples and queues.
Read-only; used to narrate live demos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import pg_database as pgdb
from app.core.auth import get_current_user

router = APIRouter(prefix="/api/demo", tags=["Demo"], dependencies=[Depends(get_current_user)])


def _ts(val):
    return val.isoformat() if val is not None else None


@router.get("/journey/{external_bill_id}")
async def bill_journey(external_bill_id: int):
    bill = await pgdb._pool.fetchrow("""
        SELECT b.id, b.external_bill_id, b.bill_status_type, b.patient_name,
               src.lab_code AS collected_at_lab, src.external_lab_id AS collected_at_lab_id
        FROM tat_bill b LEFT JOIN tat_lab src ON src.id = b.source_lab_id
        WHERE b.external_bill_id = $1
    """, external_bill_id)
    if not bill:
        raise HTTPException(404, f"No bill with CrelioHealth billId {external_bill_id}")

    samples = await pgdb._pool.fetch("""
        SELECT s.id, s.accession_no, s.status, s.cycle_number, s.collected_at, s.received_at,
               e.estimated_end_time, e.is_tat_breached, e.breach_by_mins
        FROM tat_sample s LEFT JOIN tat_eta e ON e.sample_id = s.id
        WHERE s.bill_id = $1 ORDER BY s.id
    """, bill["id"])
    tests = await pgdb._pool.fetch("""
        SELECT ti.sample_id, ti.test_code, ti.status, ti.cycle_number, ti.is_current_cycle,
               ti.external_report_id, l.lab_code AS processing_lab, ti.routing_reason,
               pa.assignment_status, pa.outsource_vendor_name,
               r.arrival_time_at_lab, r.estimated_start_time, r.estimated_end_time,
               r.is_tat_breached, r.breach_by_mins, ti.result_time
        FROM tat_test_instance ti
        LEFT JOIN tat_lab l ON l.id = ti.processing_lab_id
        LEFT JOIN tat_processing_assignment pa ON pa.test_instance_id = ti.id
        LEFT JOIN tat_eta_record r ON r.test_instance_id = ti.id
        WHERE ti.bill_id = $1
        ORDER BY ti.sample_id, ti.is_current_cycle DESC, ti.test_code
    """, bill["id"])

    by_sample = {s["id"]: [] for s in samples}
    for t in tests:
        by_sample.setdefault(t["sample_id"], []).append({
            "test": t["test_code"],
            "status": t["status"],
            "cycle": t["cycle_number"],
            "current_cycle": bool(t["is_current_cycle"]),
            "report_id": t["external_report_id"],
            "processing_lab": t["processing_lab"],
            "routing_reason": t["routing_reason"],
            "assignment": t["assignment_status"],
            "outsourced_to": t["outsource_vendor_name"],
            "arrived_at_lab": _ts(t["arrival_time_at_lab"]),
            "eta_start": _ts(t["estimated_start_time"]),
            "eta_end": _ts(t["estimated_end_time"]),
            "tat_breached": bool(t["is_tat_breached"]) if t["is_tat_breached"] is not None else None,
            "breach_by_mins": t["breach_by_mins"],
            "result_at": _ts(t["result_time"]),
        })

    return {
        "bill_id": bill["external_bill_id"],
        "bill_status": bill["bill_status_type"],
        "patient": bill["patient_name"],
        "collected_at_lab": bill["collected_at_lab"],
        "samples": [{
            "accession": s["accession_no"],
            "status": s["status"],
            "cycle": s["cycle_number"],
            "collected_at": _ts(s["collected_at"]),
            "first_received_at": _ts(s["received_at"]),
            "sample_eta_end": _ts(s["estimated_end_time"]),
            "sample_tat_breached": bool(s["is_tat_breached"]) if s["is_tat_breached"] is not None else None,
            "labs": sorted({t["processing_lab"] for t in by_sample[s["id"]]
                            if t["processing_lab"] and t["current_cycle"]}),
            "tests": by_sample[s["id"]],
        } for s in samples],
    }
