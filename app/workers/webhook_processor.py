"""
app/workers/webhook_processor.py
Celery task handler — dispatches each webhook event to the correct handler.
Uses psycopg2 (sync) within Celery workers.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import psycopg2
import psycopg2.extras
from app.core.pg_pool import pooled_connection
from config.settings import cfg
from app.services.scheduler import (
    assign_batch_slot, resolve_test_routing, resolve_processing_times, detect_tat_breach,
    route_sample_to_lab,
)
from app.services.alert_service import (
    alert_tat_breach, alert_sample_delayed, alert_sample_completed,
    alert_processing_error, alert_missing_test_config,
    _log_alert, _create_db_alert,
)
from app.services.state_machine import (
    validate_sample_transition, validate_test_transition,
    check_and_log_transition,
)
from app.services.queue_prioritizer import recalculate_sample_priority
from app.core.engine import push_sample_to_cache
from app.services.kpi_service import track_outsource_assignment
from app.services.queue_service import enqueue_sample, enqueue_result, enqueue_alert
from app.services.reconciliation import enqueue_reconciliation
from app.utils.datetime_utils import get_naive_utc_now
logger = logging.getLogger("webhook_processor")
def _pg():
    return pooled_connection()
def _now() -> datetime:
    return get_naive_utc_now()
def _parse_dt(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None
def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
def _as_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
def _first(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = payload.get(key)
        if val is not None:
            return val
    return None
def _report_id(payload: Dict[str, Any]) -> Any:
    return _first(payload, "labReportId", "CentreReportId", "Report Id", "reportID")
def _report_date(payload: Dict[str, Any]) -> Optional[datetime]:
    return _parse_dt(_first(payload, "reportDate", "Report Date", "Report_Date"))
def _approval_date(payload: Dict[str, Any]) -> Optional[datetime]:
    return _parse_dt(_first(payload, "approvalDate", "Approval Date", "Approval_Date"))
def _sample_accession(payload: Dict[str, Any]) -> Any:
    return _first(payload, "accessionNo", "sampleID", "sampleId", "identifier")
def _enqueue_reconciliation_if_needed(
    cur,
    *,
    event: Dict,
    prerequisite_type: str,
    prerequisite_detail: Optional[Dict[str, Any]] = None,
    external_bill_id: Optional[int] = None,
) -> None:
    enqueue_reconciliation(
        cur,
        webhook_event_id=event["id"],
        webhook_type=event.get("webhook_type", "UNKNOWN"),
        prerequisite_type=prerequisite_type,
        prerequisite_detail=prerequisite_detail,
        external_bill_id=external_bill_id,
    )
#bill generation webhook
def _bill_generate_samples(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Normalize supported BILL_GENERATE shapes to samples[{sample fields, reports[]}]."""
    samples = payload.get("samples")
    if isinstance(samples, list) and samples:
        return samples
    sample = payload.get("collectedSampleId") or payload.get("sampleId") or {}
    if not isinstance(sample, dict):
        sample = {"sampleId": sample}
    reports = payload.get("labReportDetails") or payload.get("testDetails") or []
    return [{
        "sampleId": sample.get("id") or sample.get("sampleId") or payload.get("sampleId") or payload.get("bill_id") or payload.get("billId"),
        "accessionNo": sample.get("accessionNo") or payload.get("accessionNo"),
        "collectedAt": sample.get("collectionTime") or payload.get("collectionTime") or payload.get("sampleDate"),
        "type": sample.get("type"),
        "name": sample.get("name"),
        "toBatchProcessing": sample.get("toBatchProcessing", False),
        "priority": payload.get("priority", 5),
        "reports": reports,
    }]
def _log(cur, data: Dict) -> None:
    meta = data.get("metadata")
    if meta and not isinstance(meta, str):
        meta = json.dumps(meta)
    cur.execute("""
        INSERT INTO tat_log
          (sample_id,bill_id,test_instance_id,lab_id,event_type,
           event_timestamp,triggered_by,webhook_event_id,notes,metadata)
        VALUES (%s,%s,%s,%s,%s,%s,'webhook_processor',%s,%s,%s)
    """, (
        data["sample_id"], data["bill_id"],
        data.get("test_instance_id"), data.get("lab_id"),
        data["event_type"], data.get("ts", _now()),
        data.get("webhook_event_id"), data.get("notes"), meta,
    ))
def _get_routing_context(dept_ids: list[int], test_codes: list[str], cur) -> Dict:
    """Pre-fetch all routing rules for a sample to avoid N+1 queries."""
    ctx = {
        "capabilities": {},
        "test_routing": {},
        "dept_routing": {},
        "fallback_lab_id": None,
    }
    # 1. Capabilities
    if dept_ids:
        cur.execute("""
            SELECT lc.department_id, lc.lab_id
            FROM tat_lab_capability lc
            JOIN tat_lab l ON l.id = lc.lab_id
            WHERE lc.department_id = ANY(%s) AND lc.is_active = 1
              AND l.is_active = 1 AND l.is_available = 1 AND l.is_fallback = 0
            ORDER BY l.id
        """, (dept_ids,))
        for r in cur.fetchall():
            if r["department_id"] not in ctx["capabilities"]:
                ctx["capabilities"][r["department_id"]] = r["lab_id"]
    # 2. Test overrides
    if test_codes:
        cur.execute("""
            SELECT test_code, processing_lab_id FROM tat_test_routing
            WHERE test_code = ANY(%s) AND is_active=1
        """, (test_codes,))
        for r in cur.fetchall():
            ctx["test_routing"][r["test_code"]] = r["processing_lab_id"]
    # 3. Dept overrides
    if dept_ids:
        cur.execute("""
            SELECT department_id, processing_lab_id FROM tat_test_routing
            WHERE department_id = ANY(%s) AND test_code IS NULL AND is_active=1
        """, (dept_ids,))
        for r in cur.fetchall():
            ctx["dept_routing"][r["department_id"]] = r["processing_lab_id"]
    # 4. Fallback lab
    cur.execute("SELECT id FROM tat_lab WHERE is_fallback=1 AND is_active=1 AND is_available=1 LIMIT 1")
    row = cur.fetchone()
    if row:
        ctx["fallback_lab_id"] = row["id"]
    return ctx
#tat calculation
def _calculate_three_tier_tat(cur, ti_id: int, sample_id: int, bill_id: int,
                               report_date: Optional[datetime]) -> Dict[str, Optional[int]]:

    if not report_date:
        return {"overall_tat_mins": None, "lab_tat_mins": None, "transport_tat_mins": None}
    # Fetch bill time and sample arrival time
    cur.execute("SELECT bill_time FROM tat_bill WHERE id=%s", (bill_id,))
    bill_row = cur.fetchone()
    bill_time = bill_row["bill_time"] if bill_row else None
    cur.execute("SELECT arrived_at_lab FROM tat_sample WHERE id=%s", (sample_id,))
    smp_row = cur.fetchone()
    processing_accession = smp_row["arrived_at_lab"] if smp_row else None
    # Calculate TAT metrics
    overall_tat_mins = None
    lab_tat_mins = None
    transport_tat_mins = None
    if bill_time and report_date:
        overall_tat_mins = int((report_date - bill_time).total_seconds() / 60)
    if processing_accession and report_date:
        lab_tat_mins = int((report_date - processing_accession).total_seconds() / 60)
    if bill_time and processing_accession:
        transport_tat_mins = int((processing_accession - bill_time).total_seconds() / 60)
    # Store in tat_eta_record for the test instance (if exists)
    if overall_tat_mins is not None:
        cur.execute("""
            UPDATE tat_eta_record
            SET actual_end_time=%s, version=version+1, updated_at=CURRENT_TIMESTAMP
            WHERE test_instance_id=%s
        """, (report_date, ti_id))
    return {
        "overall_tat_mins": overall_tat_mins,
        "lab_tat_mins": lab_tat_mins,
        "transport_tat_mins": transport_tat_mins,
    }
def _process_test_completion(cur, event_id: int, ti_id: int, sample_id: int, bill_id: int,
                             report_date: Optional[datetime], approval_date: Optional[datetime],
                             accession_date: Optional[datetime], is_signed: int, is_amended: int,
                             result_val: Optional[str], external_report_id: Optional[int] = None) -> None:
    """
    Centralized helper to mark a test instance completed, log, enqueue result, and check sample completion.
    Reused by both REPORT_SUBMIT and REPORT_PDF handlers to avoid duplication.
    Now includes three-tier TAT calculation per PRD Section 10.
    """
    now = _now()
    cur.execute("""
        UPDATE tat_test_instance
        SET status='completed', completion_webhook_id=%s,
            report_date=%s, approval_date=%s, result=%s, result_time=%s,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (event_id, report_date, approval_date, result_val, now, ti_id))
    # Calculate three-tier TAT
    tat_metrics = _calculate_three_tier_tat(cur, ti_id, sample_id, bill_id, report_date or now)
    # Update SLA record with actual TAT metrics
    if report_date or now:
        actual_completion = report_date or now
        cur.execute("""
            UPDATE tat_sla_record
            SET actual_completion_time=%s,
                actual_tat_mins=%s,
                is_original_breached=CASE
                  WHEN original_sla_deadline < %s THEN 1
                  ELSE 0
                END,
                breach_by_mins=CASE
                  WHEN original_sla_deadline < %s
                  THEN EXTRACT(EPOCH FROM (%s - original_sla_deadline))/60
                  ELSE NULL
                END,
                updated_at=CURRENT_TIMESTAMP
            WHERE test_instance_id=%s
        """, (actual_completion, tat_metrics["overall_tat_mins"], actual_completion, actual_completion, actual_completion, ti_id))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id, "test_instance_id": ti_id,
        "event_type": "test_completed", "ts": now,
        "webhook_event_id": event_id,
        "notes": f"Report processed for test instance {ti_id}",
        "metadata": {
            "overall_tat_mins": tat_metrics["overall_tat_mins"],
            "lab_tat_mins": tat_metrics["lab_tat_mins"],
            "transport_tat_mins": tat_metrics["transport_tat_mins"],
        }
    })
    enqueue_result({
        "sample_id":       sample_id,
        "bill_id":         bill_id,
        "test_instance_id": ti_id,
        "external_report_id": external_report_id,
        "report_date":     str(report_date) if report_date else None,
        "event_id":        event_id,
        "tat_metrics":     tat_metrics,
    })
    _check_sample_completion(cur, sample_id, bill_id, event_id)
# ─────────────────────────────────────────────────────────────────────────────
# BILL_GENERATE handler
# ─────────────────────────────────────────────────────────────────────────────
def _handle_bill_generate(cur, event: dict, payload: dict) -> None:
    event_id     = event["id"]
    ext_bill_id  = payload.get("bill_id") or payload.get("billId")
    lab_id_raw   = payload.get("labId")
    ext_lab_id   = lab_id_raw["labId"] if isinstance(lab_id_raw, dict) else (lab_id_raw or 0)
    org_raw      = payload.get("orgId")
    org_id       = org_raw["orgId"] if isinstance(org_raw, dict) else org_raw
    org_name     = payload.get("orgName")  # Direct field in manual webhooks
    if not org_name and isinstance(org_raw, dict):
        org_name = org_raw.get("orgFullName")

    # Upsert tat_org and fetch internal id + default priority (Section 7.2.2)
    org_internal_id = None
    org_priority = None
    if org_id:
        cur.execute("""
            INSERT INTO tat_org (external_org_id, org_name, is_active)
            VALUES (%s, %s, 1)
            ON CONFLICT (external_org_id) DO UPDATE
              SET org_name = EXCLUDED.org_name, updated_at = CURRENT_TIMESTAMP
            RETURNING id, default_priority
        """, (org_id, org_name or f"Org {org_id}"))
        org_row = cur.fetchone()
        if org_row:
            org_internal_id = org_row["id"]
            org_priority    = org_row["default_priority"]

    # Upsert tat_patient and fetch internal id (Section 10.1)
    patient_id     = payload.get("patientId")
    patient_name   = payload.get("patientName")
    patient_gender = payload.get("patientGender")
    patient_age    = payload.get("patientAge")
    patient_internal_id = None
    if patient_id:
        cur.execute("""
            INSERT INTO tat_patient
              (external_patient_id, patient_name, patient_gender, patient_age_str, is_active)
            VALUES (%s, %s, %s, %s, 1)
            ON CONFLICT (external_patient_id) DO UPDATE
              SET patient_name     = EXCLUDED.patient_name,
                  patient_gender   = EXCLUDED.patient_gender,
                  patient_age_str  = EXCLUDED.patient_age_str,
                  updated_at       = CURRENT_TIMESTAMP
            RETURNING id
        """, (patient_id, patient_name or f"Patient {patient_id}",
               patient_gender, patient_age))
        pat_row = cur.fetchone()
        if pat_row:
            patient_internal_id = pat_row["id"]

    client_type = "walk_in" if not org_id else "corporate"
    # Note: _bill_generate_samples is defined elsewhere.
    samples_raw = _bill_generate_samples(payload)
    logger.info(
        "handler execution type=BILL_GENERATE event_id=%s external_bill_id=%s samples=%d",
        event_id, ext_bill_id, len(samples_raw),
    )

    # Resolve source_lab with FOR UPDATE lock to prevent race conditions
    source_lab_id = None
    if ext_lab_id:
        cur.execute("SELECT id FROM tat_lab WHERE external_lab_id=%s LIMIT 1 FOR UPDATE", (ext_lab_id,))
        r = cur.fetchone()
        if r:
            source_lab_id = r["id"]

    cur.execute("""
        INSERT INTO tat_bill
          (webhook_event_id, external_bill_id, external_lab_id,
           bill_status_type, bill_time, bill_total_amount, due_amount, bill_advance,
           org_id, org_name, client_type, source_lab_id, org_internal_id,
           patient_id, patient_name, patient_gender, patient_age, patient_internal_id)
        VALUES (%s,%s,%s,'preview',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (external_bill_id) DO UPDATE
          SET external_lab_id     = EXCLUDED.external_lab_id,
              org_internal_id     = EXCLUDED.org_internal_id,
              patient_internal_id = EXCLUDED.patient_internal_id,
              updated_at          = CURRENT_TIMESTAMP
        RETURNING id
    """, (
        event_id, ext_bill_id, ext_lab_id,
        _parse_dt(payload.get("billTime")) or _parse_dt(payload.get("collectionTime")) or _now(),
        payload.get("totalAmount"), payload.get("dueAmount"), payload.get("billAdvance"),
        org_id, org_name, client_type, source_lab_id, org_internal_id,
        patient_id, patient_name, patient_gender, patient_age, patient_internal_id,
    ))
    bill_id = cur.fetchone()["id"]
    cur.execute(
        "UPDATE tat_bill SET total_samples=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
        (len(samples_raw), bill_id),
    )
    cur.execute("UPDATE tat_webhook_event SET internal_bill_id=%s WHERE id=%s", (bill_id, event_id))
    logger.info("DB insert success table=tat_bill bill_id=%s external_bill_id=%s event_id=%s", bill_id, ext_bill_id, event_id)
    # ── Iterate over each sample in the payload ───────────────────────────────
    for sample_raw in samples_raw:
        ext_smp_id   = sample_raw.get("sampleId") or ext_bill_id
        collected_at = _parse_dt(sample_raw.get("collectedAt"))
        reports      = sample_raw.get("reports", [])
        # Extract department IDs for routing
        dept_ids = []
        for rpt in reports:
            dept = rpt.get("departmentId") or {}
            d_id = dept.get("id") if isinstance(dept, dict) else dept
            if d_id:
                dept_ids.append(int(d_id))
        # Determine assigned lab immediately
        try:
            assigned_lab_id, routing_reason = route_sample_to_lab(dept_ids, cur)
        except ValueError:
            assigned_lab_id, routing_reason = None, "no_fallback_lab"
        # Priority mapping: Use org default if available, otherwise payload
        if org_priority is not None:
            priority = org_priority
        else:
            p_val = _as_int(sample_raw.get("priority"), 5)
            priority = 1 if p_val >= 10 else (3 if p_val >= 7 else 5)
        is_urgent = 1 if priority <= 3 else 0
        sample_status = 'pending' if assigned_lab_id else 'unassigned'
        # Get current status (default to 'draft' for new samples)
        cur.execute("SELECT status FROM tat_sample WHERE bill_id=%s AND external_sample_id=%s", (bill_id, ext_smp_id))
        existing = cur.fetchone()
        current_status = existing["status"] if existing else 'draft'
        is_valid, error_msg = validate_sample_transition(current_status, sample_status, context={'is_rerouted': True})
        if not is_valid:
            logger.warning("[STATE_MACHINE] Invalid sample transition in BILL_GENERATE: %s", error_msg)
            # Still allow the transition for now, but log it (could be made strict later)
        cur.execute("""
            INSERT INTO tat_sample
              (bill_id, webhook_event_id, external_sample_id, accession_no,
               primary_sample_type, primary_sample_name, collected_at, total_tests,
               status, assigned_lab_id, routing_reason, priority, is_urgent, is_batch)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (bill_id, external_sample_id) DO UPDATE
              SET status=%s, assigned_lab_id=EXCLUDED.assigned_lab_id,
                  routing_reason=EXCLUDED.routing_reason, priority=EXCLUDED.priority,
                  is_urgent=EXCLUDED.is_urgent, is_batch=EXCLUDED.is_batch,
                  updated_at=CURRENT_TIMESTAMP
            RETURNING id
        """, (
            bill_id, event_id, ext_smp_id,
            sample_raw.get("accessionNo"),
            sample_raw.get("type"), sample_raw.get("name"),
            collected_at, len(reports),
            sample_status, assigned_lab_id, routing_reason,
            priority, is_urgent, 1 if sample_raw.get("toBatchProcessing") else 0,
            sample_status
        ))
        sample_id = cur.fetchone()["id"]
        logger.info("DB insert success table=tat_sample sample_id=%s external_sample_id=%s bill_id=%s", sample_id, ext_smp_id, bill_id)
        # Upsert test instances
        for idx, rpt in enumerate(reports):
            dept = rpt.get("departmentId") or {}
            smp  = rpt.get("sampleId") or rpt.get("collectedSampleId") or {}
            # Per-test routing: check if webhook explicitly assigned a lab
            t_lab_raw = rpt.get("labId")
            ext_t_lab_id = t_lab_raw["labId"] if isinstance(t_lab_raw, dict) else (t_lab_raw or 0)
            t_lab_id = None
            t_reason = None
            if ext_t_lab_id:
                cur.execute("SELECT id FROM tat_lab WHERE external_lab_id=%s LIMIT 1 FOR UPDATE", (ext_t_lab_id,))
                lr = cur.fetchone()
                if lr:
                    t_lab_id = lr["id"]
                    t_reason = "webhook_assigned"
            t_dept_id = dept.get("id") if isinstance(dept, dict) else dept
            if not t_lab_id:
                t_lab_id, t_reason = resolve_test_routing(t_dept_id, rpt.get("testCode"), cur)
            # Fallback for external_report_id if missing (must be numeric for BIGINT column)
            ext_rpt_id = rpt.get("labReportId") or rpt.get("testID")
            if ext_rpt_id is None:
                import zlib
                seed = f"{ext_bill_id}_{rpt.get('testCode')}_{idx}"
                ext_rpt_id = zlib.crc32(seed.encode())
            # Determine processing time with fallbacks
            proc_mins = None
            used_override = False
            config_row = None
            if t_lab_id:
                cur.execute("""
                    SELECT processing_time_mins FROM tat_lab_test_override
                    WHERE lab_id=%s AND test_code=%s AND is_active=1
                    LIMIT 1
                """, (t_lab_id, rpt.get("testCode")))
                override_row = cur.fetchone()
                if override_row:
                    proc_mins = override_row["processing_time_mins"]
                    used_override = True
            if not proc_mins:
                cur.execute("""
                    SELECT processing_time_mins FROM tat_test_type_config
                    WHERE test_code=%s AND is_active=1
                    LIMIT 1
                """, (rpt.get("testCode"),))
                config_row = cur.fetchone()
                if config_row:
                    proc_mins = config_row["processing_time_mins"]
            if not proc_mins and t_lab_id:
                cur.execute("SELECT default_processing_mins FROM tat_lab WHERE id=%s", (t_lab_id,))
                lab_row = cur.fetchone()
                if lab_row:
                    proc_mins = lab_row["default_processing_mins"]
            if not proc_mins:
                proc_mins = cfg.DEFAULT_PROCESSING_TIME_MINS
                logger.warning(
                    "[BILL_GENERATE] No processing time config for test %s, using default %d mins",
                    rpt.get("testCode"), proc_mins
                )
            processing_time_is_default = 1 if not used_override and config_row is None else 0
            cur.execute("""
                INSERT INTO tat_test_instance
                  (sample_id, bill_id, webhook_event_id, external_report_id,
                   external_test_id, external_dict_id, lab_report_index,
                   test_code, test_name, test_category,
                   department_id, department_name,
                   sample_type, sample_name, test_amount,
                   is_radiology, is_outsourced, processing_time_mins,
                   processing_time_is_default, sample_date, status,
                   processing_lab_id, routing_reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
                ON CONFLICT (external_report_id) DO UPDATE
                  SET status='pending', processing_lab_id=EXCLUDED.processing_lab_id,
                      updated_at=CURRENT_TIMESTAMP
                RETURNING id
            """, (
                sample_id, bill_id, event_id,
                ext_rpt_id, rpt.get("testID"), rpt.get("dictionaryId"),
                rpt.get("labReportIndex"), rpt.get("testCode"), rpt.get("testName"),
                rpt.get("testCategory"),
                t_dept_id,
                dept.get("name") if isinstance(dept, dict) else None,
                smp.get("type") if isinstance(smp, dict) else None,
                smp.get("name") if isinstance(smp, dict) else None,
                rpt.get("testAmount"),
                1 if rpt.get("isRadiology") else 0,
                1 if rpt.get("isOutsourced") else 0,
                proc_mins,
                processing_time_is_default,
                _parse_dt(rpt.get("sampleDate")),
                t_lab_id, t_reason
            ))
            test_instance_id = cur.fetchone()["id"]
            # Create SLA record for the test instance (if not present)
            cur.execute("""
                SELECT CAST(predefined_tat_hours * 60 AS INT) as tat_mins
                FROM tat_test_type_config
                WHERE test_code=%s AND is_active=1
                LIMIT 1
            """, (rpt.get("testCode"),))
            ttc_row = cur.fetchone()
            original_tat_mins = ttc_row["tat_mins"] if ttc_row else None
            if not original_tat_mins:
                original_tat_mins = 8 * 60
            collected_time = collected_at # C-7 FIX: do NOT create SLA record if collected_at is None
            if collected_time:
                original_sla_deadline = collected_time + timedelta(minutes=original_tat_mins)
                cur.execute("""
                    INSERT INTO tat_sla_record
                      (test_instance_id, sample_id, bill_id,
                       original_sla_deadline, original_tat_mins)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (test_instance_id) DO NOTHING
                """, (test_instance_id, sample_id, bill_id, original_sla_deadline, original_tat_mins))
                logger.debug(
                    "[BILL_GENERATE] created SLA record test_id=%s tat_mins=%d deadline=%s",
                    test_instance_id, original_tat_mins, original_sla_deadline.isoformat()
                )
        # Log activation
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id,
            "event_type": "sample_activated", "ts": _now(),
            "webhook_event_id": event_id,
            "notes": f"Sample auto-routed to Lab {assigned_lab_id} ({routing_reason})",
        })
        # Push to cache for real-time dashboard visibility
        push_sample_to_cache(cur, sample_id)
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id,
            "event_type": "sample_created", "ts": _now(),
            "webhook_event_id": event_id,
            "notes": f"Bill {ext_bill_id} generated with {len(reports)} tests",
        })
        logger.info("[BILL_GENERATE] bill_id=%d sample_id=%d tests=%d", bill_id, sample_id, len(reports))
# ─────────────────────────────────────────────────────────────────────────────
# BILL_UPDATE handler  (activates bill/tests — NO scheduling)
# ─────────────────────────────────────────────────────────────────────────────
def _handle_bill_update(cur, event: Dict, payload: Dict) -> None:
    event_id    = event["id"]
    ext_bill_id = payload.get("bill_id") or payload.get("billId")
    cur.execute("SELECT id FROM tat_bill WHERE external_bill_id=%s", (ext_bill_id,))
    row = cur.fetchone()
    if not row:
        logger.warning("[BILL_UPDATE] bill not found ext=%s", ext_bill_id)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="bill_exists",
            prerequisite_detail={"external_bill_id": ext_bill_id},
            external_bill_id=_as_int(ext_bill_id, 0) or None,
        )
        return
    bill_id = row["id"]
    # Ensure the bill metadata and tests are up to date with the incoming payload.
    _handle_bill_generate(cur, event, payload)
    cur.execute("""
        UPDATE tat_bill SET bill_status_type='active', bill_update_time=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (bill_id,))
    cur.execute("""
        UPDATE tat_test_instance SET status='pending', updated_at=CURRENT_TIMESTAMP
        WHERE bill_id=%s AND status='draft'
    """, (bill_id,))
    cur.execute("""
        UPDATE tat_sample SET status='pending', updated_at=CURRENT_TIMESTAMP
        WHERE bill_id=%s AND status='draft'
    """, (bill_id,))
    cur.execute("SELECT id FROM tat_sample WHERE bill_id=%s LIMIT 1", (bill_id,))
    srow = cur.fetchone()
    if srow:
        _log(cur, {
            "sample_id": srow["id"], "bill_id": bill_id,
            "event_type": "sample_activated", "ts": _now(),
            "webhook_event_id": event_id,
            "notes": "Bill activated — awaiting sample receipt for scheduling",
        })
    logger.info("[BILL_UPDATE] bill_id=%d activated", bill_id)
def _handle_bill_cancel(cur, event: Dict, payload: Dict) -> None:
    event_id = event["id"]
    ext_bill_id = payload.get("bill_id") or payload.get("billId") or payload.get("billID")
    reason = payload.get("billComment") or payload.get("bill_comment") or "Bill cancelled"
    cur.execute("SELECT id FROM tat_bill WHERE external_bill_id=%s", (ext_bill_id,))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="bill_exists",
            prerequisite_detail={"external_bill_id": ext_bill_id},
            external_bill_id=_as_int(ext_bill_id, 0) or None,
        )
        return
    bill_id = row["id"]
    cur.execute("""
        UPDATE tat_bill
        SET bill_status_type='cancelled', is_active=0, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (bill_id,))
    cur.execute("""
        UPDATE tat_sample
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE bill_id=%s AND status <> 'completed'
    """, (bill_id,))
    cur.execute("SELECT id FROM tat_sample WHERE bill_id=%s LIMIT 1", (bill_id,))
    srow = cur.fetchone()
    if srow:
        sample_id = srow["id"]
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id,
            "event_type": "sample_cancelled", "ts": _now(),
            "webhook_event_id": event_id, "notes": reason,
        })
        # Queue unexpected dismissal alert
        from app.services.alert_service import _log_alert, _create_db_alert
        alert_type = "unexpected_dismissal"
        severity = "high"
        message = f"Sample {sample_id} dismissed: {reason}"
        _log_alert(cur, alert_type, sample_id, bill_id, {"reason": reason}, notes=reason)
        _create_db_alert(cur, bill_id=bill_id, sample_id=sample_id, test_instance_id=None, lab_id=None, alert_type=alert_type, severity=severity, message=message)
        push_sample_to_cache(cur, sample_id)
    cur.execute("""
        UPDATE tat_test_instance
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE bill_id=%s AND status <> 'completed'
    """, (bill_id,))
    cur.execute("""
        UPDATE tat_lab_queue
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE bill_id=%s AND status NOT IN ('completed','cancelled','skipped')
    """, (bill_id,))
    cur.execute("SELECT id FROM tat_sample WHERE bill_id=%s LIMIT 1", (bill_id,))
    srow = cur.fetchone()
    if srow:
        _log(cur, {
            "sample_id": srow["id"], "bill_id": bill_id,
            "event_type": "sample_cancelled", "ts": _now(),
            "webhook_event_id": event_id, "notes": reason,
        })
        push_sample_to_cache(cur, srow["id"])
    logger.info("[BILL_CANCEL] bill_id=%d", bill_id)
# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE_COLLECTED handler
# ─────────────────────────────────────────────────────────────────────────────
def _handle_sample_collected(cur, event: Dict, payload: Dict) -> None:
    event_id     = event["id"]
    acc_no       = _sample_accession(payload)
    ext_smp_id   = payload.get("sampleId")
    collected_at = _parse_dt(payload.get("collectionTime")) or _now()
    cur.execute("""
        SELECT s.id, s.bill_id, s.status FROM tat_sample s
        WHERE s.accession_no=%s OR s.external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        logger.warning("[SAMPLE_COLLECTED] sample not found acc=%s ext=%s", acc_no, ext_smp_id)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id, bill_id = row["id"], row["bill_id"]
    # BUG-C5 FIX: status is now in the SELECT — was always defaulting to 'draft' before
    current_status = row["status"] if row["status"] else "draft"
    is_valid, error_msg = validate_sample_transition(current_status, "pending")
    if not is_valid:
        logger.warning("[STATE_MACHINE] Invalid sample transition in SAMPLE_COLLECTED: %s", error_msg)
    cur.execute("""
        UPDATE tat_sample SET collected_at=%s, status='pending', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (collected_at, sample_id))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_collected", "ts": collected_at,
        "webhook_event_id": event_id, "notes": f"Collected at {collected_at}",
    })
    logger.info("[SAMPLE_COLLECTED] sample_id=%d", sample_id)
def _handle_sample_uncollected(cur, event: Dict, payload: Dict) -> None:
    event_id = event["id"]
    acc_no = _sample_accession(payload)
    ext_smp_id = payload.get("sampleId")
    cur.execute("""
        SELECT id, bill_id FROM tat_sample
        WHERE accession_no=%s OR external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    cur.execute("""
        UPDATE tat_sample
        SET collected_at=NULL, status='pending', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (row["id"],))
    _log(cur, {
        "sample_id": row["id"], "bill_id": row["bill_id"],
        "event_type": "sample_uncollected", "ts": _now(),
        "webhook_event_id": event_id, "notes": "Sample collection reset by LIS",
    })
    push_sample_to_cache(cur, row["id"])
# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE_RECEIVED handler  ← THE SCHEDULING TRIGGER
# ─────────────────────────────────────────────────────────────────────────────
def _handle_sample_received(cur, event: Dict, payload: Dict) -> None:
    event_id      = event["id"]
    acc_no        = _sample_accession(payload)
    ext_smp_id    = payload.get("sampleId")
    received_time = _parse_dt(_first(payload, "receivedTime", "accessionDate", "Accession Date")) or _now()
    cur.execute("""
        SELECT s.id, s.bill_id, s.collected_at, s.priority, s.is_urgent, s.status
        FROM tat_sample s
        WHERE s.accession_no=%s OR s.external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        logger.warning("[SAMPLE_RECEIVED] sample not found acc=%s ext=%s", acc_no, ext_smp_id)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id    = row["id"]
    bill_id      = row["bill_id"]
    collected_at = row["collected_at"] or received_time
    priority     = row["priority"] or 5
    current_status = row.get("status", "draft")
    is_valid, error_msg = validate_sample_transition(current_status, "arrived")
    if not is_valid:
        logger.warning("[STATE_MACHINE] Invalid sample transition in SAMPLE_RECEIVED: %s", error_msg)
    cur.execute("""
        UPDATE tat_sample
        SET received_at=%s, arrived_at_lab=%s, status='arrived', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (received_time, received_time, sample_id))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_received", "ts": received_time,
        "webhook_event_id": event_id, "notes": f"Sample arrived at lab: {acc_no}",
    })
    # C-7 FIX: Create SLA records if they were skipped in BILL_GENERATE due to missing collected_at
    cur.execute("""
        SELECT ti.id, ti.test_code
        FROM tat_test_instance ti
        LEFT JOIN tat_sla_record sr ON sr.test_instance_id = ti.id
        WHERE ti.sample_id = %s AND sr.id IS NULL
    """, (sample_id,))
    missing_sla = cur.fetchall()
    for m in missing_sla:
        cur.execute("""
            SELECT CAST(predefined_tat_hours * 60 AS INT) as tat_mins
            FROM tat_test_type_config WHERE test_code=%s AND is_active=1
            LIMIT 1
        """, (m["test_code"],))
        ttc = cur.fetchone()
        tat_mins = ttc["tat_mins"] if ttc else 480
        deadline = collected_at + timedelta(minutes=tat_mins)
        cur.execute("""
            INSERT INTO tat_sla_record (test_instance_id, sample_id, bill_id, original_sla_deadline, original_tat_mins)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (test_instance_id) DO NOTHING
        """, (m["id"], sample_id, bill_id, deadline, tat_mins))
        logger.info("[SAMPLE_RECEIVED] Created missing SLA for test_id=%d", m["id"])
    # ── Per-test routing ──────────────────────────────────────────────────────
    cur.execute("""
        SELECT id, department_id, test_code, processing_time_mins
        FROM tat_test_instance
        WHERE sample_id=%s AND status != 'cancelled'
    """, (sample_id,))
    tests = cur.fetchall()
    # Optimization: pre-fetch routing context
    dept_ids = [t["department_id"] for t in tests if t["department_id"]]
    test_codes = [t["test_code"] for t in tests if t["test_code"]]
    routing_ctx = _get_routing_context(dept_ids, test_codes, cur)
    # Check if this reception event explicitly specifies the destination lab
    webhook_lab_raw = payload.get("labId")
    ext_webhook_lab_id = webhook_lab_raw["labId"] if isinstance(webhook_lab_raw, dict) else (webhook_lab_raw or 0)
    webhook_lab_id = None
    if ext_webhook_lab_id:
        cur.execute("SELECT id FROM tat_lab WHERE external_lab_id=%s LIMIT 1", (ext_webhook_lab_id,))
        lr = cur.fetchone()
        if lr:
            webhook_lab_id = lr["id"]
    lab_groups: Dict[int, list] = {}
    any_unassigned = False
    for t in tests:
        # Priority 1: Lab from SAMPLE_RECEIVED webhook
        # Priority 2: Automatic routing logic
        if webhook_lab_id:
            lab_id = webhook_lab_id
            reason = "webhook_received_at"
        else:
            lab_id, reason = resolve_test_routing(
                t["department_id"], t["test_code"], cur, context=routing_ctx
            )
        status = 'pending' if lab_id else 'unassigned'
        if not lab_id: any_unassigned = True
        cur.execute("""
            UPDATE tat_test_instance
            SET processing_lab_id=%s, routing_reason=%s,
                status=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (lab_id, reason, status, t["id"]))
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id,
            "test_instance_id": t["id"], "lab_id": lab_id,
            "event_type": "routing_assigned" if lab_id else "routing_failed",
            "ts": _now(),
            "webhook_event_id": event_id,
            "notes": f"Test {t['test_code']} → lab {lab_id} ({reason})" if lab_id else f"Test {t['test_code']} unassigned: {reason}",
        })
        if lab_id:
            lab_groups.setdefault(lab_id, []).append(t)
            # This fixes the multi-lab issue where different tests arrive at different labs
            cur.execute("""
                INSERT INTO tat_processing_assignment
                  (sample_id, bill_id, test_instance_id, destination_lab_id,
                   route_reason, assignment_status, actual_processing_start)
                VALUES (%s, %s, %s, %s, %s, 'assigned', %s)
                ON CONFLICT (test_instance_id) DO UPDATE
                  SET destination_lab_id = EXCLUDED.destination_lab_id,
                      route_reason = EXCLUDED.route_reason,
                      assignment_status = 'assigned',
                      actual_processing_start = EXCLUDED.actual_processing_start,
                      updated_at = CURRENT_TIMESTAMP
            """, (sample_id, bill_id, t["id"], lab_id, reason, received_time))
            logger.debug(
                "[SAMPLE_RECEIVED] created processing assignment test_id=%s lab=%d",
                t["id"], lab_id
            )
            # L-7 FIX: Track outsource assignment if the reason is 'outsource_vendor'
            if reason.startswith("outsource_vendor:"):
                vendor_name = reason.split(":", 1)[1]
                track_outsource_assignment(
                    cur, t["id"], sample_id, bill_id,
                    None, # source_lab_id: currently unknown or irrelevant for initial routing
                    lab_id,
                    vendor_name,
                    predicted_eta=None # will be updated by batch logic if needed
                )
    if any_unassigned:
        cur.execute("UPDATE tat_sample SET status='unassigned' WHERE id=%s", (sample_id,))
        logger.warning("[ROUTING] Sample %d has unassigned tests", sample_id)
    else:
        # L-2 FIX: Only set arrived if all tests were assigned
        cur.execute("UPDATE tat_sample SET status='arrived' WHERE id=%s", (sample_id,))
    # ── Per-lab batch slot + ETA ──────────────────────────────────────────────
    for lab_id, lab_tests in lab_groups.items():
        test_codes = [t["test_code"] for t in lab_tests if t["test_code"]]
        t_sum, t_max, active_mins = resolve_processing_times(test_codes, lab_id, cur)
        # the slot via a capacity-guarded CTE (no separate INSERT needed below).
        slot = assign_batch_slot(lab_id, received_time, cur, active_mins, sample_id)
        batch_time: datetime = _naive_utc(slot["batch_time"])
        batch_date            = slot["batch_date"]
        sched_id              = slot["batch_schedule_id"]
        # Upsert queue entry
        cur.execute("""
            INSERT INTO tat_lab_queue
              (sample_id, lab_id, bill_id, priority,
               processing_time_sum_mins, processing_time_max_mins, processing_time_mins,
               arrival_time, estimated_start_time, estimated_end_time, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled')
            ON CONFLICT (sample_id, lab_id) DO UPDATE
              SET estimated_start_time=EXCLUDED.estimated_start_time,
                  estimated_end_time=EXCLUDED.estimated_end_time,
                  priority=EXCLUDED.priority,
                  updated_at=CURRENT_TIMESTAMP
            RETURNING id
        """, (
            sample_id, lab_id, bill_id, priority,
            t_sum, t_max, active_mins,
            received_time, batch_time,
            batch_time + timedelta(minutes=active_mins),
        ))
        queue_id = cur.fetchone()["id"]
        estimated_end = batch_time + timedelta(minutes=active_mins)
        # Get predefined TAT from test configs
        cur.execute("""
            SELECT MAX(predefined_tat_hours) AS max_tat
            FROM tat_test_type_config
            WHERE test_code = ANY(%s) AND is_active=1
        """, (test_codes,))
        tat_row = cur.fetchone()
        pred_tat_hrs = tat_row["max_tat"] if tat_row else None
        is_breached, pred_mins, breach_by = detect_tat_breach(
            collected_at, estimated_end, pred_tat_hrs
        )
        queue_wait = int((batch_time - received_time).total_seconds() / 60)
        total_eta  = int((estimated_end - collected_at).total_seconds() / 60)
        # Sample-level ETA is deprecated in favor of per-test-instance ETA tracking
        # for multi-lab processing accuracy. Keeping tat_eta for backward compatibility
        # but not populating it in new code.
        #
        # Insert or update sample-level ETA (tat_eta) - DEPRECATED
        # This is kept for backward compatibility with existing queries
        cur.execute("""
            INSERT INTO tat_eta
              (sample_id, queue_entry_id, bill_id,
               collection_time, arrival_time_at_lab,
               estimated_start_time, estimated_end_time,
               queue_wait_mins, lab_processing_mins, lab_eta_mins, total_eta_mins,
               predefined_tat_mins, is_tat_breached, breach_by_mins, version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
            ON CONFLICT (sample_id) DO UPDATE
              SET queue_entry_id        = EXCLUDED.queue_entry_id,
                  estimated_end_time    = EXCLUDED.estimated_end_time,
                  total_eta_mins        = EXCLUDED.total_eta_mins,
                  is_tat_breached       = EXCLUDED.is_tat_breached,
                  breach_by_mins        = EXCLUDED.breach_by_mins,
                  version               = tat_eta.version + 1,
                  updated_at            = CURRENT_TIMESTAMP
        """, (
            sample_id, queue_id, bill_id,
            collected_at, received_time,
            batch_time, estimated_end,
            queue_wait, active_mins, active_mins, total_eta,
            pred_mins, 1 if is_breached else 0, breach_by,
        ))
        # Retrieve newly-upserted ETA id for audit/history and per-test records
        cur.execute("SELECT id FROM tat_eta WHERE sample_id=%s", (sample_id,))
        eta_row = cur.fetchone()
        eta_id = eta_row["id"] if eta_row else None
        # ✅ CREATE ETA_RECORDS for per-test tracking (one per test_instance)
        for lab_test in lab_tests:
            test_instance_id = lab_test["id"]
            # Get test-specific predefined TAT (hours) if available
            cur.execute("""
                SELECT predefined_tat_hours
                FROM tat_test_type_config
                WHERE test_code=%s AND is_active=1
                LIMIT 1
            """, (lab_test.get("test_code"),))
            ttc_row = cur.fetchone()
            test_pred_tat_hrs = ttc_row["predefined_tat_hours"] if ttc_row else pred_tat_hrs
            test_is_breached, test_pred_mins, test_breach_by = detect_tat_breach(
                collected_at, estimated_end, test_pred_tat_hrs
            )
            cur.execute("""
                INSERT INTO tat_eta_record
                  (test_instance_id, queue_entry_id, sample_id, bill_id, lab_id,
                   collection_time, arrival_time_at_lab,
                   estimated_start_time, estimated_end_time,
                   queue_wait_mins, lab_processing_mins, total_eta_mins,
                   predefined_tat_mins, is_tat_breached, breach_by_mins, version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                ON CONFLICT (test_instance_id) DO UPDATE
                  SET queue_entry_id = EXCLUDED.queue_entry_id,
                      estimated_end_time = EXCLUDED.estimated_end_time,
                      is_tat_breached = EXCLUDED.is_tat_breached,
                      breach_by_mins = EXCLUDED.breach_by_mins,
                      version = tat_eta_record.version + 1,
                      updated_at = CURRENT_TIMESTAMP
            """, (
                test_instance_id, queue_id, sample_id, bill_id, lab_id,
                collected_at, received_time,
                batch_time, estimated_end,
                queue_wait, active_mins, total_eta,
                test_pred_mins, 1 if test_is_breached else 0, test_breach_by
            ))
            logger.debug(
                "[SAMPLE_RECEIVED] created ETA record test_id=%s lab=%d breach=%s",
                test_instance_id, lab_id, test_is_breached
            )
        # Batch assignment is now handled atomically inside assign_batch_slot
        # via a capacity-guarded CTE (H1 fix). No separate INSERT needed here.
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id, "lab_id": lab_id,
            "event_type": "batch_assigned", "ts": _now(),
            "webhook_event_id": event_id,
            "notes": f"Batch slot {batch_time.isoformat()} lab={lab_id}",
            "eta_minutes_remaining": total_eta,
            "metadata": {"batch_time": batch_time.isoformat(), "is_fallback": slot["is_fallback"]},
        })
        if is_breached:
            cur.execute("SELECT * FROM tat_bill WHERE id=%s", (bill_id,))
            bill_row = dict(cur.fetchone())
            cur.execute("SELECT accession_no FROM tat_sample WHERE id=%s", (sample_id,))
            smp_row = dict(cur.fetchone())
            alert_tat_breach(
                cur,
                sample_id, bill_id, lab_id,
                {**bill_row, **smp_row},
                {"total_eta_mins": total_eta, "predefined_tat_mins": pred_mins,
                 "breach_by_mins": breach_by, "estimated_end_time": estimated_end},
            )
    # cur.execute("UPDATE tat_sample SET status='arrived' WHERE id=%s", (sample_id,)) # REMOVED (fixed above in L-2)
    # This ensures samples near SLA breach are prioritized
    for lab_id in lab_groups.keys():
        try:
            from app.services.queue_prioritizer import recalculate_lab_queue_priorities
            recalculate_lab_queue_priorities(lab_id, cur)
        except Exception as e:
            logger.warning("[QUEUE_PRIORITIZER] Failed to recalculate priorities for lab_id=%d: %s", lab_id, e)
    # Push to hot pipeline cache (sub-ms Dashboard reads)
    push_sample_to_cache(cur, sample_id)
    # Enqueue sample job on Redis priority queue for downstream workers
    priority_label = "URGENT" if row.get("is_urgent") else ("HIGH" if priority <= 3 else "NORMAL")
    enqueue_sample({
        "sample_id":    sample_id,
        "bill_id":      bill_id,
        "accession_no": acc_no,
        "received_at":  received_time.isoformat(),
        "lab_groups":   list(lab_groups.keys()),
        "priority":     priority_label,
    })
    logger.info("[SAMPLE_RECEIVED] sample_id=%d labs=%s", sample_id, list(lab_groups.keys()))
# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE_REJECTED handler
# ─────────────────────────────────────────────────────────────────────────────
def _handle_sample_sent_to_external(cur, event: Dict, payload: Dict) -> None:
    event_id        = event["id"]
    acc_no          = _sample_accession(payload)
    ext_smp_id      = payload.get("sampleId")
    sent_time       = _parse_dt(payload.get("sentTime")) or _now()
    external_lab    = payload.get("externalLabName") or "external"
    cur.execute("""
        SELECT id, bill_id, status
        FROM tat_sample
        WHERE accession_no=%s OR external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        logger.warning("[SAMPLE_SENT_TO_EXTERNAL] sample not found acc=%s ext=%s", acc_no, ext_smp_id)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id, bill_id, current_status = row["id"], row["bill_id"], row["status"]
    is_valid, error_msg = validate_sample_transition(current_status, "in_transit")
    if not is_valid:
        logger.warning("[STATE_MACHINE] Invalid sample transition in SAMPLE_SENT_TO_EXTERNAL: %s", error_msg)
    cur.execute("""
        UPDATE tat_sample
        SET status='in_transit', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (sample_id,))
    cur.execute("""
        UPDATE tat_test_instance
        SET is_outsourced=1, routing_reason=%s, updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND is_current_cycle=1
    """, (f"sent_to_external:{external_lab}", sample_id))
    # Cancel any existing internal queue or assignment entries for this sample
    cur.execute("""
        UPDATE tat_lab_queue
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND status NOT IN ('completed','cancelled','skipped')
    """, (sample_id,))
    cur.execute("""
        UPDATE tat_processing_assignment
        SET assignment_status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND assignment_status='assigned'
    """, (sample_id,))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_in_transit", "ts": sent_time,
        "webhook_event_id": event_id,
        "notes": f"Sample forwarded to external lab: {external_lab}",
    })
    logger.info("[SAMPLE_SENT_TO_EXTERNAL] sample_id=%d external_lab=%s", sample_id, external_lab)
def _handle_sample_rejected(cur, event: Dict, payload: Dict) -> None:
    event_id   = event["id"]
    acc_no     = _sample_accession(payload)
    ext_smp_id = payload.get("sampleId")
    reason     = payload.get("rejectionReason") or payload.get("reason") or "No reason provided"
    cur.execute("""
        SELECT id, bill_id FROM tat_sample
        WHERE accession_no=%s OR external_sample_id=%s LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id, bill_id = row["id"], row["bill_id"]
    cur.execute("""
        UPDATE tat_sample SET is_rejected=1, status='rejected', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (sample_id,))
    cur.execute("""
        UPDATE tat_sla_record
        SET is_suspended=1, suspended_at=CURRENT_TIMESTAMP,
            suspension_reason=%s, updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND actual_completion_time IS NULL
    """, (reason[:128], sample_id))
    cur.execute("""
        UPDATE tat_test_instance SET status='invalidated', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND is_current_cycle=1
    """, (sample_id,))
    cur.execute("""
        UPDATE tat_lab_queue SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND status NOT IN ('completed', 'cancelled')
    """, (sample_id,))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_rejected", "ts": _now(),
        "webhook_event_id": event_id, "notes": reason,
    })
    cur.execute("""
        INSERT INTO tat_alert (bill_id, sample_id, alert_type, severity, message)
        VALUES (%s,%s,'sample_rejected','medium',%s)
    """, (bill_id, sample_id, reason))
    logger.info("[SAMPLE_REJECTED] sample_id=%d reason=%s", sample_id, reason)
def _handle_sample_dismissed(cur, event: Dict, payload: Dict) -> None:
    event_id = event["id"]
    acc_no = _sample_accession(payload)
    ext_smp_id = payload.get("sampleId")
    reason = payload.get("dismissReason") or payload.get("reason") or "Sample dismissed"
    cur.execute("""
        SELECT id, bill_id FROM tat_sample
        WHERE accession_no=%s OR external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id, bill_id = row["id"], row["bill_id"]
    cur.execute("UPDATE tat_sample SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE id=%s", (sample_id,))
    cur.execute("UPDATE tat_test_instance SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE sample_id=%s", (sample_id,))
    cur.execute("""
        UPDATE tat_lab_queue
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND status NOT IN ('completed','cancelled','skipped')
    """, (sample_id,))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_cancelled", "ts": _now(),
        "webhook_event_id": event_id, "notes": reason,
    })
    _check_sample_completion(cur, sample_id, bill_id, event_id)
# ─────────────────────────────────────────────────────────────────────────────
# REPORT_SUBMIT handler  (test completion trigger)
# ─────────────────────────────────────────────────────────────────────────────
def _handle_report_submit(cur, event: Dict, payload: Dict) -> None:
    event_id        = event["id"]
    ext_report_id   = _report_id(payload)
    report_date     = _report_date(payload)
    approval_date   = _approval_date(payload)
    # Try lookup by external_report_id first, then fallback to internal test id (testID)
    # Added fallback for bill_id + test_code lookup
    test_id_payload = payload.get("testID")
    ext_bill_id     = payload.get("bill_id") or payload.get("billId")
    test_code       = payload.get("testCode")
    cur.execute("""
        SELECT ti.id, ti.sample_id, ti.bill_id
        FROM tat_test_instance ti
        JOIN tat_bill b ON b.id = ti.bill_id
        WHERE (ti.external_report_id = %s AND %s IS NOT NULL)
           OR (ti.id = %s AND %s IS NOT NULL)
           OR (b.external_bill_id = %s AND ti.test_code = %s)
        LIMIT 1
    """, (ext_report_id, ext_report_id, test_id_payload, test_id_payload, ext_bill_id, test_code))
    row = cur.fetchone()
    if not row:
        logger.warning("[REPORT_SUBMIT] test instance not found report_id=%s testID=%s", ext_report_id, test_id_payload)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="test_exists",
            prerequisite_detail={"external_report_id": ext_report_id, "test_id": test_id_payload},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    ti_id, sample_id, bill_id = row["id"], row["sample_id"], row["bill_id"]
    result_val = payload.get("result")
    if isinstance(result_val, (dict, list)):
        import json
        result_val = json.dumps(result_val)
    # Reuse centralized completion helper
    _process_test_completion(
        cur, event_id, ti_id, sample_id, bill_id,
        report_date, approval_date, None,
        1 if payload.get("isSigned") else 0,
        1 if payload.get("is_amended") else 0,
        result_val, ext_report_id
    )
    logger.info("[REPORT_SUBMIT] ti_id=%d sample_id=%d", ti_id, sample_id)
def _handle_report_save(cur, event: Dict, payload: Dict) -> None:
    event_id = event["id"]
    ext_report_id = _report_id(payload)
    report_date = _report_date(payload) or _now()
    test_id_payload = payload.get("testID")
    ext_bill_id = payload.get("bill_id") or payload.get("billId")
    test_code = payload.get("testCode")
    cur.execute("""
        SELECT ti.id, ti.sample_id, ti.bill_id
        FROM tat_test_instance ti
        LEFT JOIN tat_bill b ON b.id = ti.bill_id
        WHERE (ti.external_report_id = %s AND %s IS NOT NULL)
           OR (ti.id = %s AND %s IS NOT NULL)
           OR (b.external_bill_id = %s AND ti.test_code = %s)
        LIMIT 1
    """, (ext_report_id, ext_report_id, test_id_payload, test_id_payload, ext_bill_id, test_code))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="test_exists",
            prerequisite_detail={"external_report_id": ext_report_id, "test_id": test_id_payload},
            external_bill_id=_as_int(ext_bill_id, 0) or None,
        )
        return
    result_val = payload.get("result") or payload.get("reportFormatAndValues")
    if isinstance(result_val, (dict, list)):
        result_val = json.dumps(result_val)
    ti_id, sample_id, bill_id = row["id"], row["sample_id"], row["bill_id"]
    cur.execute("""
        UPDATE tat_test_instance
        SET status='result_saved', result=%s, result_time=%s, updated_at=CURRENT_TIMESTAMP
        WHERE id=%s AND status <> 'completed'
    """, (result_val, report_date, ti_id))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id, "test_instance_id": ti_id,
        "event_type": "report_saved", "ts": report_date,
        "webhook_event_id": event_id,
    })
    logger.info("[REPORT_SAVE] ti_id=%d", ti_id)
# ─────────────────────────────────────────────────────────────────────────────
# REPORT_SIGNED handler
# ─────────────────────────────────────────────────────────────────────────────
def _handle_report_signed(cur, event: Dict, payload: Dict) -> None:
    event_id        = event["id"]
    ext_report_id   = _report_id(payload)
    approval_date   = _approval_date(payload) or _report_date(payload) or _now()
    test_id_payload = payload.get("testID")
    ext_bill_id     = payload.get("bill_id") or payload.get("billId")
    test_code       = payload.get("testCode")
    result_val      = payload.get("result")
    if isinstance(result_val, (dict, list)):
        import json
        result_val = json.dumps(result_val)
    cur.execute("""
        SELECT ti.id, ti.sample_id, ti.bill_id, ti.status, ti.result
        FROM tat_test_instance ti
        LEFT JOIN tat_bill b ON b.id = ti.bill_id
        WHERE (ti.external_report_id = %s AND %s IS NOT NULL)
           OR (ti.id = %s AND %s IS NOT NULL)
           OR (b.external_bill_id = %s AND ti.test_code = %s)
        LIMIT 1
    """, (ext_report_id, ext_report_id, test_id_payload, test_id_payload, ext_bill_id, test_code))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="test_exists",
            prerequisite_detail={
                "external_report_id": ext_report_id,
                "test_id": test_id_payload,
                "test_code": test_code,
            },
            external_bill_id=_as_int(ext_bill_id, 0) or None,
        )
        return
    ti_id = row["id"]
    sample_id = row["sample_id"]
    bill_id = row["bill_id"]
    current_status = row["status"]
    existing_result = row["result"]
    if current_status != "completed":
        if result_val is None:
            result_val = existing_result
        _process_test_completion(
            cur, event_id, ti_id, sample_id, bill_id,
            approval_date, approval_date, None,
            1,
            1 if payload.get("is_amended") else 0,
            result_val, ext_report_id
        )
        cur.execute("""
            UPDATE tat_test_instance
            SET is_signed=1
            WHERE id=%s
        """, (ti_id,))
    else:
        cur.execute("""
            UPDATE tat_test_instance
            SET is_signed=1, approval_date=%s, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (approval_date, ti_id))
        now = _now()
        actual_completion = approval_date or now
        tat_metrics = _calculate_three_tier_tat(cur, ti_id, sample_id, bill_id, actual_completion)
        cur.execute("""
            UPDATE tat_sla_record
            SET actual_completion_time=%s,
                actual_tat_mins=%s,
                is_original_breached=CASE WHEN original_sla_deadline < %s THEN 1 ELSE 0 END,
                breach_by_mins=CASE WHEN original_sla_deadline < %s
                    THEN EXTRACT(EPOCH FROM (%s - original_sla_deadline))/60
                    ELSE NULL END,
                updated_at=CURRENT_TIMESTAMP
            WHERE test_instance_id=%s
        """, (actual_completion, tat_metrics["overall_tat_mins"], actual_completion, actual_completion, actual_completion, ti_id))
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id, "test_instance_id": ti_id,
            "event_type": "test_signed", "ts": now,
            "webhook_event_id": event_id,
        })
        _check_sample_completion(cur, sample_id, bill_id, event_id)
    logger.info("[REPORT_SIGNED] ti_id=%d", ti_id)
# ─────────────────────────────────────────────────────────────────────────────
# REPORT_PDF handler  (storage only)
# ─────────────────────────────────────────────────────────────────────────────
def _handle_report_pdf(cur, event: Dict, payload: Dict) -> None:
    event_id = event["id"]
    cur.execute("""
        INSERT INTO tat_report_pdf_raw
          (webhook_event_id, external_report_id, external_test_id, test_code,
           sample_accession_no, report_date, approval_date, is_signed, is_amended,
           report_base64, storage_path)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)
        ON CONFLICT (external_report_id) DO UPDATE
          SET report_date=EXCLUDED.report_date, is_signed=EXCLUDED.is_signed,
              is_amended=EXCLUDED.is_amended
    """, (
        event_id, _report_id(payload), payload.get("testID"),
        payload.get("testCode"), _sample_accession(payload),
        _report_date(payload), _approval_date(payload),
        1 if payload.get("isSigned") else 0,
        1 if payload.get("is_amended") else 0,
        payload.get("reportBase64"),
    ))
    logger.info("[REPORT_PDF] stored report_id=%s", _report_id(payload))
    # If PDF appears to be final report, attempt to mark test completed using same completion helper
    ext_report_id = _report_id(payload)
    report_date = _report_date(payload)
    approval_date = _approval_date(payload)
    accession_date = _parse_dt(payload.get("accessionDate"))
    is_signed = 1 if payload.get("isSigned") else 0
    is_amended = 1 if payload.get("is_amended") else 0
    if ext_report_id:
        cur.execute("""
            SELECT ti.id, ti.sample_id, ti.bill_id
            FROM tat_test_instance ti
            WHERE ti.external_report_id=%s LIMIT 1
        """, (ext_report_id,))
        row = cur.fetchone()
        if row:
            ti_id, sample_id, bill_id = row["id"], row["sample_id"], row["bill_id"]
            # to avoid double-counting in sample completion logic
            cur.execute("""
                SELECT status FROM tat_test_instance WHERE id=%s
            """, (ti_id,))
            ti_row = cur.fetchone()
            if ti_row and ti_row["status"] == "completed":
                logger.info(
                    "[REPORT_PDF] test_instance id=%d already completed, skipping duplicate completion",
                    ti_id
                )
            else:
                # L-5 FIX: Remove the _process_test_completion call from the PDF handler.
                # Completion must come exclusively from REPORT_SIGNED / REPORT_SUBMIT.
                logger.info("[REPORT_PDF] PDF received for test_id=%d, status=%s", ti_id, ti_row["status"] if ti_row else "unknown")
# ─────────────────────────────────────────────────────────────────────────────
# TEST_DISMISSED handler
# ─────────────────────────────────────────────────────────────────────────────
def _handle_test_dismissed(cur, event: Dict, payload: Dict) -> None:
    event_id      = event["id"]
    ext_report_id = _report_id(payload)
    ext_test_id   = payload.get("testID")
    cur.execute("""
        SELECT ti.id, ti.sample_id, ti.bill_id
        FROM tat_test_instance ti
        WHERE ti.external_report_id=%s OR ti.external_test_id=%s LIMIT 1
    """, (ext_report_id, ext_test_id))
    row = cur.fetchone()
    if not row:
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="test_exists",
            prerequisite_detail={"external_report_id": ext_report_id, "external_test_id": ext_test_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    ti_id, sample_id, bill_id = row["id"], row["sample_id"], row["bill_id"]
    cur.execute("""
        UPDATE tat_test_instance SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (ti_id,))
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id, "test_instance_id": ti_id,
        "event_type": "test_dismissed", "ts": _now(),
        "webhook_event_id": event_id,
        "notes": payload.get("dismissReason"),
    })
    _check_sample_completion(cur, sample_id, bill_id, event_id)
    logger.info("[TEST_DISMISSED] ti_id=%d", ti_id)
# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE_REDRAWN handler — creates new redraw cycle
# ─────────────────────────────────────────────────────────────────────────────
def _handle_sample_redrawn(cur, event: Dict, payload: Dict) -> None:
    """
    SAMPLE_REDRAWN event handler — invalidates prior execution cycle and creates a new one.
    Per PRD Section 12.5 and database_architecture.md Section 2.3:
    - Marks current cycle test instances as is_current_cycle = 0, status = 'invalidated'
    - Creates new test instances with cycle_number = 2, is_current_cycle = 1, parent_instance_id
    - Creates revised SLA records
    - Preserves original SLA audit trail (immutable)
    - Resets queue/batch assignments for new cycle
    """
    event_id         = event["id"]
    acc_no           = _sample_accession(payload)
    ext_smp_id       = payload.get("sampleId")
    redraw_reason    = payload.get("redrawReason", "Specimen redraw")
    new_collection   = _parse_dt(payload.get("newCollectionTime")) or _now()
    expected_sla_str = payload.get("expectedSLA")
    # ── Find existing sample ──────────────────────────────────────────────────
    cur.execute("""
        SELECT s.id, s.bill_id, s.collected_at, s.priority, s.is_urgent
        FROM tat_sample s
        WHERE s.accession_no=%s OR s.external_sample_id=%s
        LIMIT 1
    """, (acc_no, ext_smp_id))
    row = cur.fetchone()
    if not row:
        logger.warning("[SAMPLE_REDRAWN] sample not found acc=%s ext=%s", acc_no, ext_smp_id)
        _enqueue_reconciliation_if_needed(
            cur,
            event=event,
            prerequisite_type="sample_exists",
            prerequisite_detail={"accession_no": acc_no, "external_sample_id": ext_smp_id},
            external_bill_id=_as_int(payload.get("bill_id") or payload.get("billId"), 0) or None,
        )
        return
    sample_id = row["id"]
    bill_id = row["bill_id"]
    original_collected_at = row["collected_at"]
    priority = row["priority"] or 5
    # C-4 FIX: Get current cycle number first
    cur.execute("SELECT MAX(cycle_number) AS current_cycle FROM tat_test_instance WHERE sample_id=%s", (sample_id,))
    cycle_row = cur.fetchone()
    current_cycle = (cycle_row["current_cycle"] or 1) if cycle_row else 1
    new_cycle = current_cycle + 1
    # ── Mark current cycle as invalidated ──────────────────────────────────────
    cur.execute("""
        UPDATE tat_test_instance
        SET is_current_cycle=0, status='invalidated', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND is_current_cycle=1
    """, (sample_id,))
    # Cancel tat_lab_queue entries for the old cycle to prevent processing
    cur.execute("""
        UPDATE tat_lab_queue
        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
        WHERE sample_id=%s AND status NOT IN ('completed', 'cancelled', 'skipped')
    """, (sample_id,))
    logger.info("[SAMPLE_REDRAWN] cancelled queue entries for sample_id=%d", sample_id)
    # ── Fetch the invalidated test instances to copy ──────────────────────────
    cur.execute("""
        SELECT id, bill_id, webhook_event_id, external_report_id,
               external_test_id, external_dict_id, lab_report_index,
               test_code, test_name, test_category,
               department_id, department_name,
               sample_type, sample_name, test_amount,
               is_radiology, processing_time_mins
        FROM tat_test_instance
        WHERE sample_id=%s AND cycle_number=%s AND is_current_cycle=0
    """, (sample_id, current_cycle))
    old_tests = cur.fetchall()
    new_test_ids = []
    for old_test in old_tests:
        # Create new test instance (Cycle 2)
        cur.execute("""
            INSERT INTO tat_test_instance
              (sample_id, bill_id, webhook_event_id, parent_instance_id,
               cycle_number, is_current_cycle,
               external_report_id, external_test_id, external_dict_id, lab_report_index,
               test_code, test_name, test_category,
               department_id, department_name,
               sample_type, sample_name, test_amount,
               is_radiology, processing_time_mins, status)
            VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            RETURNING id
        """, (
            sample_id, bill_id, event_id, old_test["id"],
            new_cycle,
            old_test["external_report_id"], old_test["external_test_id"],
            old_test["external_dict_id"], old_test["lab_report_index"],
            old_test["test_code"], old_test["test_name"], old_test["test_category"],
            old_test["department_id"], old_test["department_name"],
            old_test["sample_type"], old_test["sample_name"], old_test["test_amount"],
            old_test["is_radiology"], old_test["processing_time_mins"],
        ))
        new_ti_id = cur.fetchone()["id"]
        new_test_ids.append(new_ti_id)
        # Create revised SLA record (preserving original SLA from previous cycle)
        # Find original SLA
        cur.execute("""
            SELECT original_sla_deadline, original_tat_mins, is_original_breached
            FROM tat_sla_record
            WHERE test_instance_id=%s
            LIMIT 1
        """, (old_test["id"],))
        orig_sla = cur.fetchone()
        # Calculate revised SLA deadline (same as original: new_collection_time + original_tat_mins)
        original_tat_mins = orig_sla["original_tat_mins"] if orig_sla else None
        if not original_tat_mins and old_test.get("test_code"):
            cur.execute("""
                SELECT CAST(predefined_tat_hours * 60 AS INT) as tat_mins
                FROM tat_test_type_config WHERE test_code=%s LIMIT 1
            """, (old_test["test_code"],))
            ttc_row = cur.fetchone()
            original_tat_mins = ttc_row["tat_mins"] if ttc_row else None
        revised_sla_deadline = None
        if original_tat_mins:
            revised_sla_deadline = new_collection + timedelta(minutes=original_tat_mins)
        cur.execute("""
            INSERT INTO tat_sla_record
              (test_instance_id, sample_id, bill_id,
               original_sla_deadline, predicted_sla_deadline, revised_sla_deadline,
               original_tat_mins, revised_tat_mins, revision_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (test_instance_id) DO UPDATE
              SET revised_sla_deadline=EXCLUDED.revised_sla_deadline,
                  revised_tat_mins=EXCLUDED.revised_tat_mins,
                  revision_reason=EXCLUDED.revision_reason,
                  updated_at=CURRENT_TIMESTAMP
        """, (
            new_ti_id, sample_id, bill_id,
            orig_sla["original_sla_deadline"] if orig_sla else new_collection + timedelta(minutes=original_tat_mins or 120),
            None, revised_sla_deadline,
            original_tat_mins, original_tat_mins,
            f"Redraw: {redraw_reason}",
        ))
    # ── Update sample: mark as redraw, reset completion tracking ───────────────
    cur.execute("""
        UPDATE tat_sample
        SET cycle_number=%s, redraw=1, collected_at=%s,
            completed_tests=0, status='pending',
            updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
    """, (new_cycle, new_collection, sample_id))
    # ── Log redraw event ──────────────────────────────────────────────────────
    _log(cur, {
        "sample_id": sample_id, "bill_id": bill_id,
        "event_type": "sample_redraw", "ts": _now(),
        "webhook_event_id": event_id,
        "notes": f"Redraw initiated: {redraw_reason}. Original cycle invalidated. New cycle {new_cycle} created.",
        "metadata": {
            "redraw_reason": redraw_reason,
            "original_collection_time": str(original_collected_at),
            "new_collection_time": str(new_collection),
            "old_test_instance_count": len(old_tests),
            "new_test_instance_count": len(new_test_ids),
        }
    })
    # ── Reset bill completion counter (may need to un-complete if this was last test) ──
    cur.execute("""
        SELECT COUNT(*) as total_tests,
               COUNT(*) FILTER (WHERE cycle_number=%s) as redraw_cycle_tests
        FROM tat_test_instance WHERE bill_id=%s AND is_active=1
    """, (new_cycle, bill_id))
    test_counts = cur.fetchone()
    if test_counts["redraw_cycle_tests"] > 0:
        # There are now redraw tests - may need to reset bill to ACTIVE if completed
        cur.execute("""
            UPDATE tat_bill
            SET bill_status_type=CASE
              WHEN bill_status_type='completed' THEN 'active'
              ELSE bill_status_type
            END,
            updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (bill_id,))
    # Push updated state to cache
    push_sample_to_cache(cur, sample_id)
    logger.info(
        "[SAMPLE_REDRAWN] sample_id=%d bill_id=%d old_tests=%d new_tests=%d",
        sample_id, bill_id, len(old_tests), len(new_test_ids)
    )
# ─────────────────────────────────────────────────────────────────────────────
# Helper: check if all tests done → mark sample/bill complete
# ─────────────────────────────────────────────────────────────────────────────
def _check_sample_completion(cur, sample_id: int, bill_id: int, event_id: int) -> None:
    """
    Atomically check if all tests are complete and mark sample complete if so.
    FIX: Use single SQL statement to ensure atomicity.
    Previous pattern (SELECT + UPDATE) had race window where another thread could
    INSERT new test between SELECT and UPDATE.
        # LOCK: Acquire row lock BEFORE counting to prevent race
        cur.execute("SELECT id FROM tat_sample WHERE id=%s FOR UPDATE", (sample_id,))
    """
    now = _now()
    cur.execute("""
        WITH counts AS (
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelled') AS active_count,
                COUNT(*) FILTER (WHERE status IN ('completed', 'cancelled')) AS done_count,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed_count
            FROM tat_test_instance
            WHERE sample_id=%s
        )
        UPDATE tat_sample s
        SET completed_tests = (SELECT completed_count FROM counts),
            status = CASE
                WHEN (SELECT active_count FROM counts) = (SELECT done_count FROM counts)
                    THEN 'completed'
                ELSE 'partially_complete'
            END::sample_status_t,
            updated_at = %s
        WHERE s.id = %s
        RETURNING status
    """, (sample_id, now, sample_id))
    row = cur.fetchone()
    if row and row.get("status") == "completed":
        # Sample was marked complete (all tests done)
        cur.execute("""
            UPDATE tat_bill
            SET completed_samples = completed_samples + 1,
                bill_status_type = CASE
                  WHEN completed_samples + 1 >= total_samples THEN 'completed'
                  ELSE bill_status_type END,
                updated_at=%s
            WHERE id=%s
        """, (now, bill_id))
        _log(cur, {
            "sample_id": sample_id, "bill_id": bill_id,
            "event_type": "sample_completed", "ts": now,
            "webhook_event_id": event_id,
            "notes": "All tests completed",
        })
        # Update actual ETA
        cur.execute("SELECT * FROM tat_eta WHERE sample_id=%s", (sample_id,))
        eta_row = cur.fetchone()
        if eta_row:
            ct = eta_row["collection_time"]
            if ct is not None and hasattr(ct, "tzinfo") and ct.tzinfo is not None:
                ct = ct.replace(tzinfo=None)
            actual_mins = int((now - ct).total_seconds() / 60) if ct else None
            cur.execute("""
                UPDATE tat_eta SET actual_end_time=%s, actual_total_eta_mins=%s,
                  actual_tat_breached=CASE WHEN %s > predefined_tat_mins THEN 1 ELSE 0 END,
                  updated_at=%s
                WHERE id=%s
            """, (now, actual_mins, actual_mins, now, eta_row["id"]))
        # Push final state to hot cache
        push_sample_to_cache(cur, sample_id)
    else:
        # Push partial state to hot cache
        push_sample_to_cache(cur, sample_id)
# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table + main entry point
# ─────────────────────────────────────────────────────────────────────────────
_HANDLERS = {
    "BILL_GENERATE":    _handle_bill_generate,
    "BILL_UPDATE":      _handle_bill_update,
    "BILL_CANCEL":      _handle_bill_cancel,
    "SAMPLE_COLLECTED": _handle_sample_collected,
    "SAMPLE_UNCOLLECTED": _handle_sample_uncollected,
    "SAMPLE_RECEIVED":  _handle_sample_received,
    "SAMPLE_REJECTED":  _handle_sample_rejected,
    "SAMPLE_SENT_TO_EXTERNAL": _handle_sample_sent_to_external,
    "SAMPLE_REDRAWN":   _handle_sample_redrawn,
    "SAMPLE_DISMISSED": _handle_sample_dismissed,
    "REPORT_SAVE":      _handle_report_save,
    "REPORT_SUBMIT":    _handle_report_submit,
    "REPORT_SIGNED":    _handle_report_signed,
    "REPORT_PDF":       _handle_report_pdf,
    "TEST_DISMISSED":   _handle_test_dismissed,
    # lab_confirm_receipt().  It carries the same payload shape as SAMPLE_RECEIVED
    # (accessionNo / receivedTime), so we reuse that handler.  Without this mapping
    # the Celery worker silently returned {"status": "no_handler"} and delivery
    # confirmations never triggered the scheduling engine.
    "LAB_RECEIVED":     _handle_sample_received,
}
def handle_webhook(task, event_id: int) -> Dict:
    """Entry point called by Celery process_webhook_task."""
    try:
        with _pg() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tat_webhook_event WHERE id=%s", (event_id,))
            event = cur.fetchone()
            if not event:
                logger.error("[HANDLE] event_id=%d not found", event_id)
                return {"status": "not_found"}
            wtype   = event["webhook_type"]
            payload = event["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            logger.info("task execution event_id=%s webhook_type=%s status=%s", event_id, wtype, event.get("status"))
            cur.execute("UPDATE tat_webhook_event SET status='processing' WHERE id=%s", (event_id,))
            handler = _HANDLERS.get(wtype)
            if not handler:
                logger.error("[HANDLE] No handler for type=%s", wtype)
                cur.execute(
                    "UPDATE tat_webhook_event SET status='failed', error_message=%s WHERE id=%s",
                    (f"No handler for webhook_type={wtype}", event_id),
                )
                return {"status": "no_handler"}
            logger.info("handler execution type=%s event_id=%s", wtype, event_id)
            handler(cur, event, payload)
            processed_at = _now()
            cur.execute("""
                UPDATE tat_webhook_event
                SET status='processed', processed_at=%s
                WHERE id=%s AND status='processing'
            """, (processed_at, event_id))
            # Handlers may defer processing by updating status (for example, failed + queued for reconciliation).
            # In that case, do not overwrite the handler-set status with processed.
            if cur.rowcount == 0:
                cur.execute("SELECT status FROM tat_webhook_event WHERE id=%s", (event_id,))
                status_row = cur.fetchone()
                current_status = status_row["status"] if status_row else "unknown"
                conn.commit()
                logger.info(
                    "task deferred event_id=%s webhook_type=%s status=%s",
                    event_id,
                    wtype,
                    current_status,
                )
                return {"status": current_status, "event_id": event_id, "type": wtype}
            if cfg.MIGRATION_RECONCILIATION_ENABLED:
                cur.execute("""
                    UPDATE tat_reconciliation_queue
                    SET status='resolved', resolved_at=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE webhook_event_id=%s AND status IN ('pending','manual_review','exhausted')
                """, (processed_at, event_id))
            conn.commit()
            logger.info("task success event_id=%s webhook_type=%s", event_id, wtype)
            return {"status": "processed", "event_id": event_id, "type": wtype}
    except Exception as exc:
        logger.exception(
            "task failure event_id=%d error=%s\n  type=%s",
            event_id, exc, type(exc).__name__
        )
        # finally block calls rollback(), silently discarding the status='failed' update.
        try:
            with _pg() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tat_webhook_event
                    SET status='failed',
                        error_message=%s,
                        retry_count = retry_count + 1
                    WHERE id=%s
                """, (str(exc)[:500], event_id))
                conn.commit()  # ← CRITICAL: was missing — rollback ate the update
                logger.info(
                    "task marked failed event_id=%d retry=%s",
                    event_id, task.request.retries
                )
        except Exception as db_exc:
            logger.error(
                "task failure DB update also failed event_id=%d db_error=%s",
                event_id, db_exc
            )
        raise task.retry(exc=exc)
def do_sweep_delayed() -> None:
    """
    Runs every 5 min (Celery beat).
    1. Marks missed batch assignments → reassigns to next slot.
    2. Marks overdue queue entries → fires delay alert.
    """
    try:
        with _pg() as conn:
            cur  = conn.cursor()
            now  = _now()
            # Find batch assignments that passed their batch_time but are still 'assigned'
            cur.execute("""
                SELECT ba.id, ba.sample_id, ba.lab_id, ba.batch_time,
                       s.bill_id, s.priority
                FROM tat_lab_batch_assignment ba
                JOIN tat_sample s ON s.id = ba.sample_id
                WHERE ba.status = 'assigned' AND ba.batch_time < %s
                  AND s.status NOT IN ('completed','cancelled')
            """, (now,))
            missed = cur.fetchall()
            if missed:
                # 1. Batch Snapshot into tat_eta_history (immutable audit trail)
                # This replaces the N+1 SELECT/INSERT pattern previously inside the loop.
                missed_sample_ids = [m["sample_id"] for m in missed]
                cur.execute("""
                    INSERT INTO tat_eta_history
                      (sample_id, eta_id, version, collection_time, arrival_time_at_lab,
                       estimated_start_time, estimated_end_time, queue_wait_mins,
                       lab_eta_mins, total_eta_mins, predefined_tat_mins,
                       is_tat_breached, breach_by_mins, recalculation_reason, triggered_by)
                    SELECT sample_id, id, version, collection_time, arrival_time_at_lab,
                           estimated_start_time, estimated_end_time, queue_wait_mins,
                           lab_eta_mins, total_eta_mins, predefined_tat_mins,
                           is_tat_breached, breach_by_mins, 'Batch missed (sweep)', 'sweep_task'
                    FROM tat_eta WHERE sample_id = ANY(%s)
                """, (missed_sample_ids,))
            for m in missed:
                # Fetch processing mins from queue if present to reserve correct slot length
                cur.execute("""
                    SELECT q.id, q.processing_time_mins FROM tat_lab_queue q
                    WHERE q.sample_id=%s AND q.lab_id=%s LIMIT 1
                """, (m["sample_id"], m["lab_id"]))
                q = cur.fetchone()
                processing_mins = q["processing_time_mins"] if q else None
                # Find next batch slot, reserving lab capacity for the processing duration
                slot = assign_batch_slot(m["lab_id"], now, cur, processing_mins)
                new_batch = slot["batch_time"]
                cur.execute("""
                    UPDATE tat_lab_batch_assignment
                    SET status='missed', missed_at=%s, reassigned_to=%s, updated_at=%s
                    WHERE id=%s
                """, (now, new_batch, now, m["id"]))
                # Insert new assignment
                cur.execute("""
                    INSERT INTO tat_lab_batch_assignment
                      (lab_id, sample_id, batch_date, batch_time, batch_schedule_id, status)
                    VALUES (%s,%s,%s,%s,%s,'assigned')
                    ON CONFLICT (sample_id, lab_id) DO UPDATE
                      SET batch_time=%s, status='assigned', updated_at=%s
                """, (
                    m["lab_id"], m["sample_id"], slot["batch_date"],
                    new_batch, slot["batch_schedule_id"],
                    new_batch, now,
                ))
                if q:
                    new_end = new_batch + timedelta(minutes=q["processing_time_mins"])
                    # Fetch current ETA to calculate new totals
                    cur.execute("SELECT * FROM tat_eta WHERE sample_id=%s", (m["sample_id"],))
                    eta_snap = cur.fetchone()
                    # 3. Update queue row
                    cur.execute("""
                        UPDATE tat_lab_queue
                        SET estimated_start_time=%s, estimated_end_time=%s, updated_at=%s
                        WHERE id=%s
                    """, (new_batch, new_end, now, q["id"]))
                    # 4. Recalculate totals for updated ETA row
                    if eta_snap:
                        # new_batch comes from _now() which is also naive — but if tz stripping
                        # is inconsistent, strip tzinfo defensively before arithmetic.
                        nb = new_batch.replace(tzinfo=None) if new_batch.tzinfo else new_batch
                        ne = new_end.replace(tzinfo=None) if new_end.tzinfo else new_end
                        arr = eta_snap["arrival_time_at_lab"]
                        col = eta_snap["collection_time"]
                        # Strip tzinfo from DB values too if they somehow have it
                        if arr and arr.tzinfo:
                            arr = arr.replace(tzinfo=None)
                        if col and col.tzinfo:
                            col = col.replace(tzinfo=None)
                        new_queue_wait = int(
                            (nb - arr).total_seconds() / 60
                        ) if arr else eta_snap["queue_wait_mins"]
                        new_total_eta = int(
                            (ne - col).total_seconds() / 60
                        ) if col else eta_snap["total_eta_mins"]
                        pred_mins = eta_snap.get("predefined_tat_mins")
                        new_breach = (new_total_eta > pred_mins) if pred_mins else False
                        new_breach_by = (new_total_eta - pred_mins) if (pred_mins and new_breach) else None
                    else:
                        new_queue_wait = 0
                        new_total_eta  = q["processing_time_mins"]
                        new_breach     = False
                        new_breach_by  = None
                    # 5. Update tat_eta with new values + bump version
                    cur.execute("""
                        UPDATE tat_eta
                        SET estimated_start_time=%s, estimated_end_time=%s,
                            queue_wait_mins=%s, total_eta_mins=%s,
                            is_tat_breached=%s, breach_by_mins=%s,
                            version=version+1, updated_at=%s
                        WHERE sample_id=%s
                    """, (
                        new_batch, new_end,
                        new_queue_wait, new_total_eta,
                        1 if new_breach else 0, new_breach_by,
                        now, m["sample_id"],
                    ))
                _log(cur, {
                    "sample_id": m["sample_id"], "bill_id": m["bill_id"],
                    "lab_id": m["lab_id"],
                    "event_type": "batch_missed", "ts": now,
                    "notes": f"Batch missed, reassigned to {new_batch.isoformat()}",
                })
                alert_sample_delayed(
                    cur, m["sample_id"], m["bill_id"], m["lab_id"],
                    q["id"] if q else 0,  # A-3 FIX: use actual queue id
                    int((now - m["batch_time"]).total_seconds() / 60),
                )
                logger.warning("[SWEEP] Missed batch sample_id=%d reassigned to %s",
                               m["sample_id"], new_batch)
            conn.commit()
    except Exception as exc:
        logger.exception("[SWEEP] Error: %s", exc)
def do_refresh_projection() -> None:
    """Recalculate ETA projections for active samples from the current queue state."""
    try:
        with _pg() as conn:
            cur = conn.cursor()
            now = _now()
            cur.execute("""
                SELECT
                    s.id AS sample_id,
                    s.bill_id,
                    s.status AS sample_status,
                    s.accession_no,
                    e.id AS eta_id,
                    e.collection_time,
                    e.arrival_time_at_lab,
                    e.estimated_start_time AS eta_start,
                    e.estimated_end_time AS eta_end,
                    e.queue_wait_mins,
                    e.lab_eta_mins,
                    e.total_eta_mins,
                    e.predefined_tat_mins,
                    e.is_tat_breached,
                    e.breach_by_mins,
                    q.id AS queue_id,
                    q.lab_id,
                    q.arrival_time AS queue_arrival_time,
                    q.estimated_start_time AS queue_start,
                    q.estimated_end_time AS queue_end,
                    q.processing_time_mins AS queue_processing_mins
                FROM tat_sample s
                JOIN tat_eta e ON e.sample_id = s.id
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM tat_lab_queue q
                    WHERE q.sample_id = s.id AND q.status NOT IN ('completed', 'skipped')
                    ORDER BY q.updated_at DESC, q.id DESC
                    LIMIT 1
                ) q ON TRUE
                WHERE s.status NOT IN ('completed', 'cancelled')
            """)
            rows = cur.fetchall()
            refreshed = 0
            for row in rows:
                if not row.get("queue_id"):
                    continue
                queue_start = row["queue_start"] or row["eta_start"]
                queue_end = row["queue_end"] or row["eta_end"]
                queue_arrival = row["queue_arrival_time"] or row["arrival_time_at_lab"] or row["collection_time"]
                queue_processing_mins = row["queue_processing_mins"] or row["lab_eta_mins"]
                if not queue_start or not queue_end or not queue_arrival:
                    continue
                new_queue_wait = int((queue_start - queue_arrival).total_seconds() / 60)
                new_total_eta = int((queue_end - row["collection_time"]).total_seconds() / 60) if row["collection_time"] else row["total_eta_mins"]
                pred_mins = row["predefined_tat_mins"]
                new_breach = 1 if (pred_mins is not None and new_total_eta > pred_mins) else 0
                new_breach_by = (new_total_eta - pred_mins) if (pred_mins is not None and new_total_eta > pred_mins) else None
                if (
                    row["eta_start"] == queue_start
                    and row["eta_end"] == queue_end
                    and row["queue_wait_mins"] == new_queue_wait
                    and row["total_eta_mins"] == new_total_eta
                    and row["is_tat_breached"] == new_breach
                    and row["breach_by_mins"] == new_breach_by
                ):
                    continue
                cur.execute("""
                    INSERT INTO tat_eta_history
                      (sample_id, eta_id, version, collection_time, arrival_time_at_lab,
                       estimated_start_time, estimated_end_time, queue_wait_mins,
                       lab_eta_mins, total_eta_mins, predefined_tat_mins,
                       is_tat_breached, breach_by_mins, recalculation_reason, triggered_by)
                    SELECT sample_id, id, version, collection_time, arrival_time_at_lab,
                           estimated_start_time, estimated_end_time, queue_wait_mins,
                           lab_eta_mins, total_eta_mins, predefined_tat_mins,
                           is_tat_breached, breach_by_mins, 'Projection refresh', 'projection_task'
                    FROM tat_eta WHERE sample_id=%s
                """, (row["sample_id"],))
                cur.execute("""
                    UPDATE tat_eta
                    SET arrival_time_at_lab=%s,
                        estimated_start_time=%s,
                        estimated_end_time=%s,
                        queue_wait_mins=%s,
                        lab_eta_mins=%s,
                        total_eta_mins=%s,
                        is_tat_breached=%s,
                        breach_by_mins=%s,
                        updated_at=%s,
                        version = version + 1
                    WHERE sample_id=%s
                """, (
                    queue_arrival,
                    queue_start,
                    queue_end,
                    new_queue_wait,
                    queue_processing_mins,
                    new_total_eta,
                    new_breach,
                    new_breach_by,
                    now,
                    row["sample_id"],
                ))
                _log(cur, {
                    "sample_id": row["sample_id"],
                    "bill_id": row["bill_id"],
                    "event_type": "eta_updated",
                    "ts": now,
                    "notes": "Projection refreshed from current queue state",
                })
                push_sample_to_cache(cur, row["sample_id"])
                refreshed += 1
            logger.info("[PROJECTION_REFRESH] refreshed=%d scanned=%d", refreshed, len(rows))
            conn.commit()
    except Exception as exc:
        logger.exception("[PROJECTION_REFRESH] failed: %s", exc)
def do_sla_at_risk_check() -> None:
    """Periodically check for samples nearing SLA breach and send alerts."""
    import json
    try:
        with _pg() as conn:
            cur = conn.cursor()
            # Find samples within 60 mins of breach that haven't been alerted
            cur.execute("""
                SELECT sr.sample_id, sr.bill_id, sr.original_sla_deadline, s.accession_no,
                       ti.id AS test_instance_id, ti.processing_lab_id
                FROM tat_sla_record sr
                JOIN tat_sample s ON s.id = sr.sample_id
                JOIN tat_test_instance ti ON ti.sample_id = s.id
                WHERE sr.actual_completion_time IS NULL
                  AND sr.original_sla_deadline < CURRENT_TIMESTAMP + INTERVAL '60 minutes'
                  AND sr.original_sla_deadline > CURRENT_TIMESTAMP
                  AND NOT EXISTS (
                      SELECT 1 FROM tat_alert a
                      WHERE a.test_instance_id = ti.id AND a.alert_type = 'sla_at_risk'
                  )
                LIMIT 100
            """)
            rows = cur.fetchall()
            for r in rows:
                logger.warning("[SLA_CHECK] Sample %d (test %d) is at risk! Deadline: %s",
                               r["sample_id"], r["test_instance_id"], r["original_sla_deadline"])
                msg = f"SLA at risk for test {r['test_instance_id']} on sample {r['accession_no']}. Deadline: {r['original_sla_deadline']}"
                # Write to tat_alert
                cur.execute(
                    """INSERT INTO tat_alert
                       (bill_id, sample_id, test_instance_id, lab_id, alert_type, severity, message, is_acknowledged)
                       VALUES (%s, %s, %s, %s, 'sla_at_risk', 'high', %s, 0)""",
                    (r["bill_id"], r["sample_id"], r["test_instance_id"], r["processing_lab_id"], msg)
                )
                # Also log to tat_log
                meta = {
                    "sample_id": r["sample_id"],
                    "bill_id": r["bill_id"],
                    "test_instance_id": r["test_instance_id"],
                    "lab_id": r["processing_lab_id"],
                    "original_sla_deadline": str(r["original_sla_deadline"]),
                }
                cur.execute(
                    """INSERT INTO tat_log
                       (sample_id, bill_id, lab_id, event_type, event_timestamp, triggered_by, notes, metadata)
                       VALUES (%s, %s, %s, 'tat_breach_alert', CURRENT_TIMESTAMP, 'system', %s, %s)""",
                    (r["sample_id"], r["bill_id"], r["processing_lab_id"], f"SLA at risk: {msg}", json.dumps(meta))
                )
            
            # Check for outsourced tests approaching vendor SLA deadline
            cur.execute("""
                SELECT sr.sample_id, sr.bill_id, sr.predicted_sla_deadline, s.accession_no,
                       ti.id AS test_instance_id, ti.processing_lab_id,
                       pa.outsource_vendor_name, pa.outsource_buffer_mins
                FROM tat_sla_record sr
                JOIN tat_test_instance ti ON ti.id = sr.test_instance_id
                JOIN tat_sample s ON s.id = sr.sample_id
                LEFT JOIN tat_processing_assignment pa ON pa.test_instance_id = ti.id
                WHERE ti.is_outsourced = 1
                  AND sr.actual_completion_time IS NULL
                  AND sr.predicted_sla_deadline IS NOT NULL
                  AND sr.predicted_sla_deadline < CURRENT_TIMESTAMP + INTERVAL '120 minutes'
                  AND sr.predicted_sla_deadline > CURRENT_TIMESTAMP
                  AND NOT EXISTS (
                      SELECT 1 FROM tat_alert a
                      WHERE a.test_instance_id = ti.id AND a.alert_type = 'outsource_sla_at_risk'
                  )
                LIMIT 100
            """)
            outsource_rows = cur.fetchall()
            for r in outsource_rows:
                vendor_name = r["outsource_vendor_name"] or "unknown vendor"
                logger.warning(
                    "[OUTSOURCE_SLA_CHECK] Outsourced test %d (sample %d) from vendor %s is at risk! Deadline: %s",
                    r["test_instance_id"], r["sample_id"], vendor_name, r["predicted_sla_deadline"]
                )
                msg = f"Outsourced test {r['test_instance_id']} from {vendor_name} is approaching SLA deadline. Deadline: {r['predicted_sla_deadline']}"
                # Write to tat_alert with custom alert type
                cur.execute(
                    """INSERT INTO tat_alert
                       (bill_id, sample_id, test_instance_id, lab_id, alert_type, severity, message, is_acknowledged)
                       VALUES (%s, %s, %s, %s, 'outsource_sla_at_risk', 'high', %s, 0)""",
                    (r["bill_id"], r["sample_id"], r["test_instance_id"], r["processing_lab_id"], msg)
                )
                # Log to tat_log
                meta = {
                    "sample_id": r["sample_id"],
                    "bill_id": r["bill_id"],
                    "test_instance_id": r["test_instance_id"],
                    "lab_id": r["processing_lab_id"],
                    "outsource_vendor_name": vendor_name,
                    "predicted_sla_deadline": str(r["predicted_sla_deadline"]),
                    "outsource_buffer_mins": r["outsource_buffer_mins"],
                }
                cur.execute(
                    """INSERT INTO tat_log
                       (sample_id, bill_id, lab_id, event_type, event_timestamp, triggered_by, notes, metadata)
                       VALUES (%s, %s, %s, 'outsource_sla_alert', CURRENT_TIMESTAMP, 'system', %s, %s)""",
                    (r["sample_id"], r["bill_id"], r["processing_lab_id"], f"Outsource SLA at risk: {msg}", json.dumps(meta))
                )
            
            conn.commit()
    except Exception as exc:
        logger.exception("[SLA_CHECK] Error: %s", exc)
def do_redraw_overdue_check() -> None:
    """Check for redraws that haven't been collected within expected window."""
    import json
    try:
        with _pg() as conn:
            cur = conn.cursor()
            # Find redraws requested > 24h ago that are still pending
            cur.execute("""
                SELECT s.id, s.accession_no, l.created_at as request_time, s.bill_id
                FROM tat_sample s
                JOIN tat_log l ON l.sample_id = s.id
                WHERE s.redraw = 1 AND s.status = 'rejected'
                  AND l.event_type = 'sample_rejected'
                  AND l.created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours'
                  AND NOT EXISTS (
                      SELECT 1 FROM tat_alert a
                      WHERE a.sample_id = s.id AND a.alert_type = 'redraw_overdue'
                  )
                LIMIT 50
            """)
            rows = cur.fetchall()
            for r in rows:
                logger.error("[REDRAW_CHECK] Redraw for sample %d is OVERDUE! Requested at: %s", r["id"], r["request_time"])
                msg = f"Redraw for sample {r['accession_no']} is overdue. Requested at: {r['request_time']}"
                # Write to tat_alert
                cur.execute(
                    """INSERT INTO tat_alert
                       (bill_id, sample_id, alert_type, severity, message, is_acknowledged)
                       VALUES (%s, %s, 'redraw_overdue', 'high', %s, 0)""",
                    (r["bill_id"], r["id"], msg)
                )
                # Log to tat_log
                meta = {"sample_id": r["id"], "bill_id": r["bill_id"], "request_time": str(r["request_time"])}
                cur.execute(
                    """INSERT INTO tat_log
                       (sample_id, bill_id, event_type, event_timestamp, triggered_by, notes, metadata)
                       VALUES (%s, %s, 'processing_error', CURRENT_TIMESTAMP, 'system', %s, %s)""",
                    (r["id"], r["bill_id"], f"Redraw overdue: {msg}", json.dumps(meta))
                )
            conn.commit()
    except Exception as exc:
        logger.exception("[REDRAW_CHECK] Error: %s", exc)
def do_lab_downtime_sync() -> None:
    """Check tat_lab_downtime for planned downtime windows starting within the next 2 hours and pre-generate alerts."""
    import json
    try:
        with _pg() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, lab_id, start_time, end_time, reason, is_planned
                FROM tat_lab_downtime
                WHERE start_time > CURRENT_TIMESTAMP
                  AND start_time <= CURRENT_TIMESTAMP + INTERVAL '2 hours'
                  AND is_planned = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM tat_alert a
                      WHERE a.lab_id = tat_lab_downtime.lab_id
                        AND a.alert_type = 'lab_downtime'
                        AND a.message LIKE '%%' || tat_lab_downtime.id::text || '%%'
                  )
            """)
            rows = cur.fetchall()
            for r in rows:
                logger.warning("[DOWNTIME_SYNC] Lab %d has planned downtime starting at %s", r["lab_id"], r["start_time"])
                msg = f"Lab downtime (planned, id: {r['id']}) starting at {r['start_time']} until {r['end_time']}. Reason: {r['reason']}"
                cur.execute(
                    """INSERT INTO tat_alert
                       (lab_id, alert_type, severity, message, is_acknowledged)
                       VALUES (%s, 'lab_downtime', 'medium', %s, 0)""",
                    (r["lab_id"], msg)
                )
            conn.commit()
    except Exception as exc:
        logger.exception("[DOWNTIME_SYNC] Error: %s", exc)
