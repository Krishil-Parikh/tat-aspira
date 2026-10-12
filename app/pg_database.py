"""
app/pg_database.py — Async PostgreSQL layer using asyncpg.
All public functions are coroutines used by FastAPI route handlers.
Celery workers use psycopg2 directly (see workers/celery_app.py).
"""
from __future__ import annotations
import logging
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from config.settings import cfg

logger = logging.getLogger("pg_database")
_pool: Optional[asyncpg.Pool] = None


def _numeric_event_key(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return zlib.crc32(str(value).encode("utf-8"))


async def connect_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=cfg.DATABASE_URL,
        min_size=cfg.PG_POOL_MIN,
        max_size=cfg.PG_POOL_MAX,
        statement_cache_size=0,
    )
    # Log connection without exposing credentials
    from urllib.parse import urlparse
    parsed = urlparse(cfg.DATABASE_URL)
    safe_host = f"{parsed.scheme}://***@{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
    logger.info("PostgreSQL pool created: %s", safe_host)


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(r) -> Optional[Dict]:
    if not r: return None
    d = dict(r)
    for k, v in d.items():
        if isinstance(v, datetime) and v.tzinfo is None:
            d[k] = v.replace(tzinfo=timezone.utc)
    return d

def _rows(rs) -> List[Dict]:
    return [_row(r) for r in rs if r]

# ── Webhook Events ────────────────────────────────────────────────────────────

async def insert_webhook_event(data: Dict[str, Any]) -> int:
    """
    Insert raw webhook event. bill_id stores the EXTERNAL bill reference (NOT NULL in schema).
    internal_bill_id is reserved for the internal tat_bill.id FK (set later by worker).
    """
    import json
    # bill_id is BIGINT NOT NULL — store the external key (int) here
    bill_id_val = _numeric_event_key(data.get("bill_id"))

    # lab_id is INT NOT NULL — default to 0 if missing
    lab_id_val = data.get("lab_id")
    try:
        lab_id_val = int(lab_id_val) if lab_id_val is not None else 0
    except (ValueError, TypeError):
        lab_id_val = 0

    webhook_id_val = data.get("webhook_id")
    if webhook_id_val is not None:
        try:
            webhook_id_val = int(webhook_id_val)
        except (ValueError, TypeError):
            # If the DB column is BIGINT, we can't store string IDs like "wh_abc".
            # We'll treat it as NULL for the unique constraint but log the mismatch.
            logger.warning("Non-integer webhook_id detected: %s. Storing as NULL.", webhook_id_val)
            webhook_id_val = None

    # Use a CTE to handle the ON CONFLICT case and ALWAYS return an ID.
    # This prevents the 'event_id=0' bug that blocks Celery processing for duplicates.
    sql = """
    WITH ins AS (
        INSERT INTO tat_webhook_event
          (webhook_id, webhook_type, bill_id, internal_bill_id, lab_id,
           payload, payload_hash, source_ip, auth_token_hash, status)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'received')
        ON CONFLICT (bill_id, webhook_type, webhook_id) DO NOTHING
        RETURNING id
    )
    SELECT id FROM ins
    UNION ALL
    SELECT id FROM tat_webhook_event
    WHERE bill_id = $3 AND webhook_type = $2 AND (webhook_id IS NOT DISTINCT FROM $1)
    LIMIT 1
    """

    row = await _pool.fetchrow(
        sql,
        webhook_id_val, data["webhook_type"], bill_id_val,
        None,  # internal_bill_id
        lab_id_val,
        json.dumps(data["payload"]),
        data.get("payload_hash"), data.get("source_ip"), data.get("auth_token_hash"),
    )
    
    if not row:
        logger.error("DB failure: Webhook insert/select failed for type=%s bill=%s", data["webhook_type"], bill_id_val)
        raise Exception(f"Database failure: Webhook event insert failed for type={data['webhook_type']} bill={bill_id_val}")

    event_id = row["id"]
    logger.info(
        "Webhook captured: event_id=%s bill_id=%s type=%s",
        event_id, bill_id_val, data["webhook_type"]
    )
    return event_id


async def get_webhook_event(event_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_webhook_event WHERE id = $1", event_id
    )
    return _row(row)


async def mark_event_processed(event_id: int) -> None:
    await _pool.execute(
        "UPDATE tat_webhook_event SET status = 'processed', processed_at = $1 WHERE id = $2",
        _now(), event_id
    )


async def update_webhook_event_status(event_id: int, status: str) -> None:
    """Update webhook event status."""
    await _pool.execute(
        "UPDATE tat_webhook_event SET status = $1 WHERE id = $2",
        status, event_id
    )


async def mark_event_failed(event_id: int, error: str) -> None:
    await _pool.execute(
        """UPDATE tat_webhook_event
           SET status='failed', error_message=$1,
               retry_count = retry_count + 1
           WHERE id=$2""",
        error, event_id,
    )


async def check_duplicate_event(external_key: Any, webhook_type: str, webhook_id: Optional[int]) -> bool:
    """
    Returns True only when an event with the SAME (bill_id, webhook_type, webhook_id)
    already exists.  Using IS NOT DISTINCT FROM handles the NULL == NULL case.

    FIX BUG-001: The original query ignored webhook_id, causing legitimate re-collection
    events (same bill, same type, different webhookId) to be dropped as duplicates.
    FIX BUG-TYPE: bill_id column is BIGINT NOT NULL — query now uses bill_id (int) instead
    of internal_bill_id (which received a str value against an INT column).
    """
    bid = _numeric_event_key(external_key)
    wid: Optional[int] = None
    if webhook_id is not None:
        try:
            wid = int(webhook_id)
        except (ValueError, TypeError):
            wid = None
    row = await _pool.fetchrow(
        """SELECT id FROM tat_webhook_event
           WHERE bill_id=$1
             AND webhook_type=$2
             AND (webhook_id IS NOT DISTINCT FROM $3)""",
        bid, webhook_type, wid,
    )
    return row is not None


async def check_duplicate_payload_hash(payload_hash: str) -> bool:
    if not payload_hash:
        return False
    row = await _pool.fetchrow(
        "SELECT id FROM tat_webhook_event WHERE payload_hash=$1 LIMIT 1",
        payload_hash,
    )
    return row is not None


# ── PDF Raw Storage ───────────────────────────────────────────────────────────

async def insert_pdf_raw(data: Dict[str, Any]) -> int:
    sql = """
    INSERT INTO tat_report_pdf_raw
      (webhook_event_id, external_report_id, external_test_id, test_code,
       sample_accession_no, report_date, approval_date, is_signed, is_amended,
       report_base64, storage_path)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (external_report_id) DO UPDATE
      SET report_date=$6, approval_date=$7, is_signed=$8, is_amended=$9,
          report_base64=$10
    RETURNING id
    """
    row = await _pool.fetchrow(
        sql,
        data["webhook_event_id"], data["external_report_id"],
        data.get("external_test_id"), data.get("test_code"),
        data.get("sample_accession_no"), data.get("report_date"),
        data.get("approval_date"), data.get("is_signed", 0),
        data.get("is_amended", 0), data.get("report_base64"),
        data.get("storage_path"),
    )
    return row["id"]


# ── Labs ─────────────────────────────────────────────────────────────────────

async def get_lab(lab_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow("SELECT * FROM tat_lab WHERE id=$1", lab_id)
    return _row(row)


async def get_lab_by_code(code: str) -> Optional[Dict]:
    row = await _pool.fetchrow("SELECT * FROM tat_lab WHERE lab_code=$1", code)
    return _row(row)


async def get_all_labs() -> List[Dict]:
    rows = await _pool.fetch("SELECT * FROM tat_lab WHERE is_active=1 ORDER BY id")
    return _rows(rows)


async def get_lab_with_queue_depth(lab_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        """SELECT l.*,
           (SELECT COUNT(*) FROM tat_lab_queue
            WHERE lab_id=$1 AND status IN ('scheduled','waiting','processing')
           ) AS current_queue_depth
           FROM tat_lab l WHERE l.id=$1""",
        lab_id,
    )
    return _row(row)


async def update_lab_next_available_time(lab_id: int, dt: datetime, conn) -> None:
    """Must be called within an existing transaction (conn)."""
    await conn.execute(
        "UPDATE tat_lab SET next_available_time=$1 WHERE id=$2", dt, lab_id
    )


async def get_lab_capabilities(lab_id: int) -> List[Dict]:
    rows = await _pool.fetch(
        "SELECT * FROM tat_lab_capability WHERE lab_id=$1 AND is_active=1", lab_id
    )
    return _rows(rows)


# ── Test Config ───────────────────────────────────────────────────────────────

async def get_test_config(test_code: str) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_test_type_config WHERE test_code=$1 AND is_active=1",
        test_code,
    )
    return _row(row)


async def get_test_configs_bulk(test_codes: List[str]) -> List[Dict]:
    rows = await _pool.fetch(
        "SELECT * FROM tat_test_type_config WHERE test_code = ANY($1) AND is_active=1",
        test_codes,
    )
    return _rows(rows)


async def get_lab_test_override(lab_id: int, test_code: str) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_lab_test_override WHERE lab_id=$1 AND test_code=$2 AND is_active=1",
        lab_id, test_code,
    )
    return _row(row)


# ── Bills ─────────────────────────────────────────────────────────────────────

async def upsert_bill(data: Dict[str, Any]) -> int:
    client_type = 'walk_in' if not data.get('org_id') else 'corporate'
    sql = """
    INSERT INTO tat_bill
      (webhook_event_id, external_bill_id, external_lab_id, bill_status_type,
       bill_time, bill_total_amount, due_amount, bill_advance,
       org_id, org_name, client_type, source_lab_id,
       patient_id, patient_name, patient_gender, patient_age)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
    ON CONFLICT (external_bill_id) DO UPDATE
      SET bill_status_type = EXCLUDED.bill_status_type,
          bill_update_time = CASE WHEN EXCLUDED.bill_status_type='active'
                                  THEN CURRENT_TIMESTAMP ELSE tat_bill.bill_update_time END,
          external_lab_id  = EXCLUDED.external_lab_id,
          updated_at       = CURRENT_TIMESTAMP
    RETURNING id
    """
    row = await _pool.fetchrow(
        sql,
        data["webhook_event_id"], data["external_bill_id"], data["external_lab_id"],
        data.get("bill_status_type", "preview"),
        data.get("bill_time"), data.get("bill_total_amount"),
        data.get("due_amount"), data.get("bill_advance"),
        data.get("org_id"), data.get("org_name"),
        client_type, data.get("source_lab_id"),
        data.get("patient_id"), data.get("patient_name"),
        data.get("patient_gender"), data.get("patient_age"),
    )
    return row["id"]


async def get_bill(bill_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow("SELECT * FROM tat_bill WHERE id=$1", bill_id)
    return _row(row)


async def get_bill_by_external(external_bill_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_bill WHERE external_bill_id=$1", external_bill_id
    )
    return _row(row)


async def list_bills(limit: int = 50, offset: int = 0) -> List[Dict]:
    rows = await _pool.fetch(
        "SELECT * FROM tat_bill ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )
    return _rows(rows)


async def increment_bill_completed_samples(bill_id: int, conn) -> None:
    await conn.execute(
        """UPDATE tat_bill SET completed_samples = completed_samples + 1,
           bill_status_type = CASE WHEN completed_samples + 1 >= total_samples
                                   THEN 'completed' ELSE bill_status_type END
           WHERE id=$1""",
        bill_id,
    )


# ── Samples ───────────────────────────────────────────────────────────────────

async def upsert_sample(data: Dict[str, Any], conn=None) -> int:
    sql = """
    INSERT INTO tat_sample
      (bill_id, webhook_event_id, external_sample_id, accession_no,
       primary_sample_type, primary_sample_name, collected_at, received_at,
       total_tests, is_rejected, is_batch, batch_id, is_urgent, priority, status)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
    ON CONFLICT (bill_id, external_sample_id) DO UPDATE
      SET status = EXCLUDED.status,
          total_tests = EXCLUDED.total_tests,
          updated_at = CURRENT_TIMESTAMP
    RETURNING id
    """
    db = conn or _pool
    row = await db.fetchrow(
        sql,
        data["bill_id"], data["webhook_event_id"], data["external_sample_id"],
        data.get("accession_no"), data.get("primary_sample_type"),
        data.get("primary_sample_name"), data.get("collected_at"),
        data.get("received_at"), data.get("total_tests", 0),
        data.get("is_rejected", 0), data.get("is_batch", 0),
        data.get("batch_id"), data.get("is_urgent", 0),
        data.get("priority", 5), data.get("status", "draft"),
    )
    return row["id"]


async def get_sample(sample_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        """
        SELECT s.*, b.patient_name, b.external_bill_id, l.lab_name
        FROM tat_sample s
        LEFT JOIN tat_bill b ON b.id = s.bill_id
        LEFT JOIN tat_lab l ON l.id = s.assigned_lab_id
        WHERE s.id=$1
        """, 
        sample_id
    )
    return _row(row)


async def get_sample_by_accession(accession_no: str) -> Optional[Dict]:
    row = await _pool.fetchrow(
        """
        SELECT s.*, b.patient_name, b.external_bill_id, l.lab_name
        FROM tat_sample s
        LEFT JOIN tat_bill b ON b.id = s.bill_id
        LEFT JOIN tat_lab l ON l.id = s.assigned_lab_id
        WHERE s.accession_no=$1
        """, 
        accession_no
    )
    return _row(row)


async def get_sample_by_external(bill_id: int, external_sample_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_sample WHERE bill_id=$1 AND external_sample_id=$2",
        bill_id, external_sample_id,
    )
    return _row(row)


async def list_samples(status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict]:
    """Returns enriched sample rows with bill info, ETA breach flag, and completed_tests count."""
    base_sql = """
        SELECT
            s.*,
            b.external_bill_id,
            b.patient_name,
            b.org_name,
            e.is_tat_breached,
            e.total_eta_mins,
            (SELECT COUNT(*) FROM tat_test_instance ti
             WHERE ti.sample_id = s.id AND ti.status = 'completed') AS completed_tests
        FROM tat_sample s
        LEFT JOIN tat_bill  b ON b.id = s.bill_id
        LEFT JOIN (
            SELECT sample_id, 
                   MAX(is_tat_breached) as is_tat_breached,
                   MAX(total_eta_mins) as total_eta_mins
            FROM tat_eta_record
            GROUP BY sample_id
        ) e ON e.sample_id = s.id
        {where}
        ORDER BY s.created_at DESC
        LIMIT $1 OFFSET $2
    """
    if status:
        sql = base_sql.format(where="WHERE s.status=$3")
        rows = await _pool.fetch(sql, limit, offset, status)
    else:
        sql = base_sql.format(where="")
        rows = await _pool.fetch(sql, limit, offset)
    return _rows(rows)


# Whitelisted columns for update_sample_status to prevent SQL injection
_SAMPLE_UPDATE_WHITELIST = {
    "status", "assigned_lab_id", "routing_reason", "priority", "is_urgent",
    "is_batch", "batch_id", "comments", "completed_at", "received_at",
    "arrived_at_lab", "total_tests", "completed_tests", "is_rejected"
}

_VALID_STATUSES = {
    "draft", "pending", "queued", "in_transit", "arrived", "processing",
    "partially_complete", "completed", "cancelled", "rejected", "delayed",
    "unassigned", "error"
}

async def update_sample_status(sample_id: int, status: str, conn=None, **kwargs) -> None:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status value: {status}")
    db = conn or _pool
    # Validate all kwargs against whitelist to prevent SQL injection
    invalid_columns = set(kwargs.keys()) - _SAMPLE_UPDATE_WHITELIST
    if invalid_columns:
        raise ValueError(
            f"Invalid columns for tat_sample update: {invalid_columns}. "
            f"Allowed columns: {_SAMPLE_UPDATE_WHITELIST}"
        )
    fields = {"status": status, **kwargs}
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields.keys()))
    vals = list(fields.values())
    await db.execute(
        f"UPDATE tat_sample SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=$1",
        sample_id, *vals,
    )


async def assign_lab_to_sample(sample_id: int, lab_id: int, reason: str, conn) -> None:
    await conn.execute(
        "UPDATE tat_sample SET assigned_lab_id=$1, routing_reason=$2, status='queued', updated_at=CURRENT_TIMESTAMP WHERE id=$3",
        lab_id, reason, sample_id,
    )


# ── Test Instances ────────────────────────────────────────────────────────────

async def upsert_test_instance(data: Dict[str, Any], conn=None) -> int:
    sql = """
    INSERT INTO tat_test_instance
      (sample_id, bill_id, webhook_event_id, external_report_id,
       external_test_id, external_dict_id, lab_report_index,
       test_code, test_name, test_category, department_id, department_name,
       sample_type, sample_name, test_amount, is_radiology, is_outsourced,
       processing_time_mins, processing_time_is_default,
       sample_date, predicted_report_date, status)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
    ON CONFLICT (external_report_id) DO UPDATE
      SET status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP
    RETURNING id
    """
    db = conn or _pool
    row = await db.fetchrow(
        sql,
        data["sample_id"], data["bill_id"], data["webhook_event_id"],
        data["external_report_id"], data.get("external_test_id"),
        data.get("external_dict_id"), data.get("lab_report_index"),
        data.get("test_code"), data.get("test_name"), data.get("test_category"),
        data.get("department_id"), data.get("department_name"),
        data.get("sample_type"), data.get("sample_name"),
        data.get("test_amount"), data.get("is_radiology", 0),
        data.get("is_outsourced", 0), data.get("processing_time_mins", 60),
        data.get("processing_time_is_default", 0),
        data.get("sample_date"), data.get("predicted_report_date"),
        data.get("status", "draft"),
    )
    return row["id"]


async def list_test_instances(sample_id: int) -> List[Dict]:
    """Returns test instances enriched with lab name and SLA/TAT metrics."""
    rows = await _pool.fetch(
        """
        SELECT
            ti.*,
            ti.status::text AS status,
            l.lab_name,
            sr.actual_tat_mins      AS lab_tat_mins,
            sr.original_tat_mins    AS sla_tat_mins,
            sr.actual_completion_time,
            sr.is_original_breached,
            sr.original_sla_deadline,
            er.estimated_end_time,
            er.is_tat_breached
        FROM tat_test_instance ti
        LEFT JOIN tat_lab l ON l.id = ti.processing_lab_id
        LEFT JOIN tat_sla_record sr ON sr.test_instance_id = ti.id
        LEFT JOIN tat_eta_record er ON er.test_instance_id = ti.id
        WHERE ti.sample_id=$1
        ORDER BY ti.id
        """,
        sample_id,
    )
    return _rows(rows)


async def list_tracked_tests(
    q: Optional[str] = None,
    status: Optional[str] = None,
    lab_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Returns test instances enriched with patient, bill, sample, and ETA data."""
    where = []
    args: list[Any] = []

    if status:
        args.append(status)
        where.append(f"ti.status::text = ${len(args)}")

    if lab_id:
        args.append(lab_id)
        where.append(f"ti.processing_lab_id = ${len(args)}")

    if q:
        args.append(f"%{q.lower()}%")
        idx = len(args)
        where.append(
            f"""(
                LOWER(COALESCE(b.patient_name, '')) LIKE ${idx}
                OR CAST(b.external_bill_id AS TEXT) LIKE ${idx}
                OR CAST(b.patient_id AS TEXT) LIKE ${idx}
            )"""
        )

    args.extend([limit, offset])
    limit_idx = len(args) - 1
    offset_idx = len(args)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    rows = await _pool.fetch(
        f"""
        SELECT
            ti.id AS test_instance_id,
            ti.test_name,
            ti.status::text AS status,
            b.patient_name,
            b.external_bill_id AS bill_id,
            b.patient_id,
            e.estimated_end_time AS eta,
            ti.created_at,
            s.id AS sample_id,
            s.accession_no,
            COUNT(*) OVER() AS total_count
        FROM tat_test_instance ti
        JOIN tat_bill b ON b.id = ti.bill_id
        LEFT JOIN tat_sample s ON s.id = ti.sample_id
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        {where_sql}
        ORDER BY ti.created_at DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """,
        *args,
    )
    tests = _rows(rows)
    total = int(rows[0].get("total_count", 0)) if rows else 0
    return {"total": total, "tests": tests}


def _title_from_event_type(event_type: Optional[str]) -> str:
    if not event_type:
        return "Timeline Event"
    return event_type.replace("_", " ").title()


async def get_tracked_test_detail(test_id: int) -> Optional[Dict[str, Any]]:
    """Return one test instance with patient, lab, ETA, and dynamic audit timeline."""
    row = await _pool.fetchrow(
        """
        SELECT
            ti.id AS test_id,
            ti.test_name,
            ti.test_code,
            ti.status::text AS status,
            ti.created_at,
            b.patient_name,
            b.external_bill_id AS bill_id,
            b.patient_id,
            e.estimated_end_time AS eta,
            source_lab.lab_name AS source_lab,
            processing_lab.lab_name AS processing_lab,
            s.id AS sample_id,
            s.accession_no
        FROM tat_test_instance ti
        JOIN tat_bill b ON b.id = ti.bill_id
        JOIN tat_sample s ON s.id = ti.sample_id
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        LEFT JOIN tat_lab source_lab ON source_lab.external_lab_id = b.external_lab_id
        LEFT JOIN tat_lab processing_lab ON processing_lab.id = ti.processing_lab_id
        WHERE ti.id = $1
        """,
        test_id,
    )
    if not row:
        return None

    detail = _row(row)
    logs = await _pool.fetch(
        """
        SELECT event_type::text AS event_type, event_timestamp, notes, triggered_by
        FROM tat_log
        WHERE sample_id = $1
          AND (test_instance_id = $2 OR test_instance_id IS NULL)
        ORDER BY event_timestamp ASC, id ASC
        """,
        detail["sample_id"],
        test_id,
    )

    timeline = []
    for log in logs:
        event_type = log["event_type"]
        timeline.append({
            "status": _title_from_event_type(event_type),
            "description": log["notes"] or f"{_title_from_event_type(event_type)} recorded",
            "timestamp": log["event_timestamp"],
        })

    if not timeline:
        timeline.append({
            "status": "Test Created",
            "description": "Test instance registered",
            "timestamp": detail["created_at"],
        })

    return {
        "test_id": detail["test_id"],
        "test_name": detail["test_name"] or detail["test_code"] or f"Test #{detail['test_id']}",
        "status": detail["status"],
        "patient_name": detail["patient_name"],
        "bill_id": detail["bill_id"],
        "patient_id": detail["patient_id"],
        "source_lab": detail["source_lab"],
        "processing_lab": detail["processing_lab"],
        "created_at": detail["created_at"],
        "eta": detail["eta"],
        "timeline": timeline,
        "sample_id": detail["sample_id"],
        "accession_no": detail["accession_no"],
    }


async def get_test_instance_by_external_report(external_report_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_test_instance WHERE external_report_id=$1", external_report_id
    )
    return _row(row)


async def complete_test_instance(
    instance_id: int, webhook_event_id: int,
    report_date: Optional[datetime], approval_date: Optional[datetime],
    accession_date: Optional[datetime], is_signed: int, is_amended: int, conn
) -> None:
    await conn.execute(
        """UPDATE tat_test_instance SET
           status='completed', completion_webhook_id=$2,
           report_date=$3, approval_date=$4, accession_date=$5,
           is_signed=$6, is_amended=$7, updated_at=CURRENT_TIMESTAMP
           WHERE id=$1""",
        instance_id, webhook_event_id, report_date, approval_date,
        accession_date, is_signed, is_amended,
    )


async def count_completed_tests(sample_id: int, conn) -> tuple[int, int]:
    """Returns (total, completed)."""
    row = await conn.fetchrow(
        """SELECT COUNT(*) AS total,
           SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
           FROM tat_test_instance WHERE sample_id=$1 AND status != 'cancelled'""",
        sample_id,
    )
    return int(row["total"]), int(row["completed"] or 0)


async def get_sample_department_ids(sample_id: int) -> List[int]:
    rows = await _pool.fetch(
        "SELECT DISTINCT department_id FROM tat_test_instance WHERE sample_id=$1 AND status != 'cancelled'",
        sample_id,
    )
    return [r["department_id"] for r in rows if r["department_id"]]


# ── Queue ─────────────────────────────────────────────────────────────────────

async def insert_queue_entry(data: Dict[str, Any], conn) -> int:
    sql = """
    INSERT INTO tat_lab_queue
      (sample_id, lab_id, bill_id, initial_queue_position, priority,
       processing_time_sum_mins, processing_time_max_mins, processing_time_mins,
       arrival_time, estimated_start_time, estimated_end_time, status)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'scheduled')
    RETURNING id
    """
    row = await conn.fetchrow(
        sql,
        data["sample_id"], data["lab_id"], data["bill_id"],
        data.get("initial_queue_position"), data.get("priority", 5),
        data["processing_time_sum_mins"], data["processing_time_max_mins"],
        data["processing_time_mins"], data["arrival_time"],
        data["estimated_start_time"], data["estimated_end_time"],
    )
    return row["id"]


async def get_queue_entry_for_sample(sample_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow(
        "SELECT * FROM tat_lab_queue WHERE sample_id=$1 ORDER BY estimated_end_time DESC NULLS LAST LIMIT 1", sample_id
    )
    return _row(row)


# Whitelisted columns for update_queue_entry to prevent SQL injection
_QUEUE_UPDATE_WHITELIST = {
    "priority", "status", "estimated_start_time", "estimated_end_time",
    "actual_start_time", "actual_end_time", "skip_reason",
    "recalculation_count", "last_recalculated_at", "processing_time_mins"
}

async def update_queue_entry(entry_id: int, conn=None, **fields) -> None:
    db = conn or _pool
    # Validate all fields against whitelist to prevent SQL injection
    invalid_columns = set(fields.keys()) - _QUEUE_UPDATE_WHITELIST
    if invalid_columns:
        raise ValueError(
            f"Invalid columns for tat_lab_queue update: {invalid_columns}. "
            f"Allowed columns: {_QUEUE_UPDATE_WHITELIST}"
        )
    sets = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields.keys()))
    vals = list(fields.values())
    await db.execute(
        f"UPDATE tat_lab_queue SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=$1",
        entry_id, *vals,
    )


async def get_delayed_queue_entries() -> List[Dict]:
    rows = await _pool.fetch(
        """SELECT * FROM tat_lab_queue
           WHERE status NOT IN ('completed','skipped','delayed')
           AND estimated_end_time < CURRENT_TIMESTAMP"""
    )
    return _rows(rows)


async def get_lab_queue(lab_id: int, limit: int = 50) -> List[Dict]:
    rows = await _pool.fetch(
        """SELECT q.*, s.accession_no, s.priority AS sample_priority
           FROM tat_lab_queue q JOIN tat_sample s ON s.id = q.sample_id
           WHERE q.lab_id=$1 AND q.status NOT IN ('completed','skipped')
           ORDER BY q.priority, q.estimated_start_time
           LIMIT $2""",
        lab_id, limit,
    )
    return _rows(rows)


# ── ETA ───────────────────────────────────────────────────────────────────────

async def insert_eta(data: Dict[str, Any], conn) -> int:
    sql = """
    INSERT INTO tat_eta
      (sample_id, queue_entry_id, bill_id,
       collection_time, arrival_time_at_lab, estimated_start_time, estimated_end_time,
       queue_wait_mins, lab_processing_mins, lab_eta_mins, total_eta_mins,
       predefined_tat_mins, is_tat_breached, breach_by_mins, version)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,1)
    ON CONFLICT (sample_id) DO UPDATE
      SET queue_entry_id=$2, estimated_end_time=$7,
          total_eta_mins=$11, is_tat_breached=$13, breach_by_mins=$14,
          version = tat_eta.version + 1, updated_at=CURRENT_TIMESTAMP
    RETURNING id
    """
    row = await conn.fetchrow(
        sql,
        data["sample_id"], data["queue_entry_id"], data["bill_id"],
        data["collection_time"], data["arrival_time_at_lab"],
        data["estimated_start_time"], data["estimated_end_time"],
        data["queue_wait_mins"], data["lab_processing_mins"],
        data["lab_eta_mins"], data["total_eta_mins"],
        data.get("predefined_tat_mins"), data["is_tat_breached"],
        data.get("breach_by_mins"),
    )
    return row["id"]


async def get_eta(sample_id: int) -> Optional[Dict]:
    row = await _pool.fetchrow("SELECT * FROM tat_eta WHERE sample_id=$1", sample_id)
    return _row(row)


async def snapshot_eta_history(eta: Dict, reason: str, triggered_by: str, conn) -> None:
    await conn.execute(
        """INSERT INTO tat_eta_history
           (sample_id, eta_id, version, collection_time, arrival_time_at_lab,
            estimated_start_time, estimated_end_time, queue_wait_mins,
            lab_eta_mins, total_eta_mins, predefined_tat_mins,
            is_tat_breached, breach_by_mins, recalculation_reason, triggered_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)""",
        eta["sample_id"], eta["id"], eta["version"],
        eta["collection_time"], eta["arrival_time_at_lab"],
        eta["estimated_start_time"], eta["estimated_end_time"],
        eta["queue_wait_mins"], eta["lab_eta_mins"], eta["total_eta_mins"],
        eta.get("predefined_tat_mins"), eta["is_tat_breached"],
        eta.get("breach_by_mins"), reason, triggered_by,
    )


# ── Audit Log ─────────────────────────────────────────────────────────────────

async def insert_log(data: Dict[str, Any], conn=None) -> None:
    import json
    sql = """
    INSERT INTO tat_log
      (sample_id, bill_id, test_instance_id, lab_id, event_type,
       event_timestamp, triggered_by, webhook_event_id,
       queue_position, queue_status, eta_minutes_remaining,
       elapsed_mins, notes, metadata)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
    """
    db = conn or _pool
    meta = data.get("metadata")
    if meta and not isinstance(meta, str):
        meta = json.dumps(meta)
    await db.execute(
        sql,
        data["sample_id"], data["bill_id"],
        data.get("test_instance_id"), data.get("lab_id"),
        data["event_type"], data.get("event_timestamp", _now()),
        data.get("triggered_by"), data.get("webhook_event_id"),
        data.get("queue_position"), data.get("queue_status"),
        data.get("eta_minutes_remaining"), data.get("elapsed_mins"),
        data.get("notes"), meta,
    )


async def list_logs(sample_id: int, limit: int = 50) -> List[Dict]:
    rows = await _pool.fetch(
        "SELECT * FROM tat_log WHERE sample_id=$1 ORDER BY created_at DESC LIMIT $2",
        sample_id, limit,
    )
    return _rows(rows)


# ── Dashboard Stats ───────────────────────────────────────────────────────────

async def get_dashboard_stats() -> Dict[str, Any]:
    row = await _pool.fetchrow("""
    SELECT
      (SELECT COUNT(*) FROM tat_sample)                                                AS total_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status IN ('pending','arrived','in_transit','partially_complete')) AS active_samples, -- FIX BUG-004
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'completed')                    AS completed_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'delayed')                      AS delayed_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'cancelled')                    AS cancelled_samples,
      (SELECT COUNT(*) FROM tat_eta   WHERE is_tat_breached = 1)                      AS tat_breaches,
      (SELECT COUNT(*) FROM tat_bill  WHERE bill_status_type = 'active')              AS active_bills,
      (SELECT COUNT(*) FROM tat_lab   WHERE is_available = 1 AND is_active = 1)       AS labs_available
    """)
    return dict(row)

# ── Batch Queries (new) ───────────────────────────────────────────────────────

async def get_batch_assignments(lab_id: int, limit: int = 50) -> list:
    rows = await _pool.fetch("""
        SELECT ba.*, s.accession_no, s.priority AS sample_priority
        FROM tat_lab_batch_assignment ba
        JOIN tat_sample s ON s.id = ba.sample_id
        WHERE ba.lab_id=$1
        ORDER BY ba.batch_time DESC LIMIT $2
    """, lab_id, limit)
    return [dict(r) for r in rows]


async def get_batch_schedule(lab_id: int) -> list:
    rows = await _pool.fetch(
        "SELECT * FROM tat_lab_batch_schedule WHERE lab_id=$1 AND is_active=1 ORDER BY batch_time",
        lab_id
    )
    return [dict(r) for r in rows]


async def get_dashboard_stats_extended() -> dict:
    row = await _pool.fetchrow("""
    SELECT
      (SELECT COUNT(*) FROM tat_sample)                                                  AS total_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status IN ('arrived','processing'))         AS active_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'completed')                       AS completed_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'delayed')                         AS delayed_samples,
      (SELECT COUNT(*) FROM tat_sample WHERE status = 'cancelled')                       AS cancelled_samples,
      (SELECT COUNT(*) FROM tat_eta   WHERE is_tat_breached = 1)                         AS tat_breaches,
      (SELECT COUNT(*) FROM tat_bill  WHERE bill_status_type = 'active')                 AS active_bills,
      (SELECT COUNT(*) FROM tat_lab   WHERE is_available = 1 AND is_active = 1)          AS labs_available,
      (SELECT COUNT(*) FROM tat_lab_batch_assignment WHERE status = 'assigned')          AS pending_batch_count,
      (SELECT COUNT(*) FROM tat_lab_batch_assignment WHERE status = 'missed')            AS missed_batch_count,
      (SELECT COUNT(*) FROM tat_test_instance WHERE status = 'completed')                AS completed_tests,
      (SELECT COUNT(*) FROM tat_test_instance WHERE status = 'pending')                  AS pending_tests
    """)
    return dict(row)


async def get_lab_stats() -> list:
    rows = await _pool.fetch("""
        SELECT l.id, l.lab_name, l.lab_code,
          (SELECT COUNT(*) FROM tat_lab_batch_assignment ba
           WHERE ba.lab_id=l.id AND ba.status='assigned') AS pending_batches,
          (SELECT COUNT(*) FROM tat_lab_batch_assignment ba
           WHERE ba.lab_id=l.id AND ba.status='missed')   AS missed_batches,
          (SELECT COUNT(*) FROM tat_lab_queue q
           WHERE q.lab_id=l.id AND q.status NOT IN ('completed','skipped')) AS queue_depth
        FROM tat_lab l WHERE l.is_active=1
        ORDER BY l.id
    """)
    return [dict(r) for r in rows]


async def get_sla_stats() -> list:
    rows = await _pool.fetch("""
        SELECT b.client_type,
          COUNT(e.id) AS total_with_eta,
          SUM(CASE WHEN e.is_tat_breached=1 THEN 1 ELSE 0 END) AS breached
        FROM tat_eta e
        JOIN tat_sample s ON s.id = e.sample_id
        JOIN tat_bill   b ON b.id = s.bill_id
        GROUP BY b.client_type
    """)
    return [dict(r) for r in rows]


# ── Timeline (structured view over tat_log) ───────────────────────────────────

async def get_sample_timeline(sample_id: int) -> List[Dict]:
    """
    Returns a structured chronological timeline of all events for a sample.
    Derived from tat_log which is written inside every webhook handler.
    No new tables needed — tat_log is the source of truth.
    """
    rows = await _pool.fetch("""
        SELECT
            l.id,
            l.event_type,
            l.event_timestamp,
            l.notes,
            l.lab_id,
            l.test_instance_id,
            l.triggered_by,
            l.webhook_event_id,
            lab.lab_name,
            ti.test_code,
            ti.test_name
        FROM tat_log l
        LEFT JOIN tat_lab lab ON lab.id = l.lab_id
        LEFT JOIN tat_test_instance ti ON ti.id = l.test_instance_id
        WHERE l.sample_id = $1
        ORDER BY l.event_timestamp ASC, l.id ASC
    """, sample_id)
    return _rows(rows)


# ── Per-lab KPI (derived from webhook-written tables) ─────────────────────────

async def get_lab_kpi(lab_id: int) -> Dict:
    """
    Per-lab KPI metrics. All data written by webhook handlers.
    Metrics: total tests, completed, pending, delayed, avg TAT, SLA %.
    RBAC enforced at API layer.
    """
    row = await _pool.fetchrow("""
        SELECT
          l.id                                                     AS lab_id,
          l.lab_name,
          l.lab_code,
          l.is_available,
          l.is_active,
          COUNT(DISTINCT ti.id)                                    AS total_tests,
          COUNT(DISTINCT CASE WHEN ti.status = 'completed' THEN ti.id END) AS completed_tests,
          COUNT(DISTINCT CASE WHEN ti.status = 'pending'   THEN ti.id END) AS pending_tests,
          COUNT(DISTINCT CASE WHEN ti.status = 'cancelled' THEN ti.id END) AS cancelled_tests,
          COUNT(DISTINCT CASE WHEN e.is_tat_breached = 1   THEN e.id END) AS tat_breaches,
          COUNT(DISTINCT e.id)                                     AS samples_with_eta,
          ROUND(AVG(e.actual_total_eta_mins)::numeric, 1)         AS avg_actual_tat_mins,
          ROUND(AVG(e.total_eta_mins)::numeric, 1)                AS avg_expected_tat_mins,
          CASE WHEN COUNT(DISTINCT e.id) > 0
               THEN ROUND(
                 (1.0 - COUNT(DISTINCT CASE WHEN e.is_tat_breached=1 THEN e.id END)::numeric
                      / COUNT(DISTINCT e.id)) * 100, 1)
               ELSE 100.0
          END                                                      AS sla_percent,
          (SELECT COUNT(*) FROM tat_lab_batch_assignment ba
           WHERE ba.lab_id = l.id AND ba.status = 'assigned')     AS pending_batches,
          (SELECT COUNT(*) FROM tat_lab_batch_assignment ba
           WHERE ba.lab_id = l.id AND ba.status = 'missed')       AS missed_batches,
          (SELECT COUNT(*) FROM tat_lab_queue q
           WHERE q.lab_id = l.id AND q.status NOT IN ('completed','skipped')) AS queue_depth
        FROM tat_lab l
        LEFT JOIN tat_test_instance ti ON ti.processing_lab_id = l.id
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        WHERE l.id = $1
        GROUP BY l.id, l.lab_name, l.lab_code, l.is_available, l.is_active
    """, lab_id)
    return _row(row)


# ── Admin dashboard (full system view, webhook-derived) ───────────────────────

async def get_admin_dashboard() -> Dict:
    """
    Admin dashboard: system-wide stats + recent activity.
    All data written by webhook processors.
    """
    stats = await get_dashboard_stats()
    lab_stats = await get_lab_stats()
    sla = await get_sla_stats()

    # Recent TAT breach alerts from tat_log
    breach_rows = await _pool.fetch("""
        SELECT l.sample_id, l.bill_id, l.event_timestamp, l.notes,
               l.lab_id, lab.lab_name, b.patient_name, b.external_bill_id
        FROM tat_log l
        JOIN tat_bill b ON b.id = l.bill_id
        LEFT JOIN tat_lab lab ON lab.id = l.lab_id
        WHERE l.event_type = 'tat_breach_alert'
        ORDER BY l.event_timestamp DESC
        LIMIT 10
    """)

    # Unassigned samples (routing failed)
    unassigned_rows = await _pool.fetch("""
        SELECT s.id, s.accession_no, s.status, s.collected_at,
               b.patient_name, b.external_bill_id
        FROM tat_sample s
        JOIN tat_bill b ON b.id = s.bill_id
        WHERE s.status = 'unassigned'
        ORDER BY s.collected_at ASC
        LIMIT 20
    """)

    return {
        "stats": stats,
        "labs": lab_stats,
        "sla_by_client": sla,
        "recent_breaches": _rows(breach_rows),
        "unassigned_samples": _rows(unassigned_rows),
    }


# ── Lab dashboard (lab-scoped, webhook-derived) ───────────────────────────────

async def get_lab_dashboard(lab_id: int) -> Dict:
    """
    Lab-specific dashboard: work queue + KPI + recent completions.
    All data written by webhook processors. RBAC enforced at API layer.
    """
    kpi = await get_lab_kpi(lab_id)

    # Active work queue for this lab
    queue_rows = await _pool.fetch("""
        SELECT
            s.id AS sample_id, s.accession_no, s.priority,
            s.status AS sample_status, s.arrived_at_lab,
            b.patient_name, b.external_bill_id,
            ti.id AS test_instance_id, ti.test_code, ti.test_name,
            ti.status AS test_status,
            e.estimated_end_time, e.is_tat_breached, e.total_eta_mins,
            lba.batch_time AS assigned_batch_time
        FROM tat_sample s
        JOIN tat_bill b ON b.id = s.bill_id
        JOIN tat_test_instance ti ON ti.sample_id = s.id
        LEFT JOIN tat_eta e ON e.sample_id = s.id
        LEFT JOIN tat_lab_batch_assignment lba ON lba.sample_id = s.id AND lba.lab_id = $1
        WHERE ti.processing_lab_id = $1
          AND ti.status NOT IN ('completed', 'cancelled')
          AND s.status NOT IN ('completed', 'cancelled')
        ORDER BY s.priority DESC, e.estimated_end_time ASC NULLS LAST
        LIMIT 100
    """, lab_id)

    # Recent completions (last 20)
    completed_rows = await _pool.fetch("""
        SELECT s.id AS sample_id, s.accession_no,
               b.patient_name,
               ti.test_code, ti.test_name, ti.result_time,
               e.actual_total_eta_mins, e.actual_tat_breached
        FROM tat_test_instance ti
        JOIN tat_sample s ON s.id = ti.sample_id
        JOIN tat_bill b ON b.id = s.bill_id
        LEFT JOIN tat_eta e ON e.sample_id = s.id
        WHERE ti.processing_lab_id = $1
          AND ti.status = 'completed'
        ORDER BY ti.result_time DESC NULLS LAST
        LIMIT 20
    """, lab_id)

    return {
        "lab_id": lab_id,
        "kpi": kpi,
        "work_queue": _rows(queue_rows),
        "recent_completions": _rows(completed_rows),
    }


# ── Test-wise SLA Analytics ───────────────────────────────────────────────────

async def get_test_analytics() -> Dict:
    """
    Per-test-type KPI analytics. Aggregated entirely in DB.
    Returns:
      - global: list of test_code stats (avg TAT, SLA%, total, completed, delayed)
      - per_lab: same breakdown scoped to each lab
    All data written by webhook processor (tat_test_instance, tat_eta, tat_log).
    """
    # Global: per test_code breakdown
    global_rows = await _pool.fetch("""
        SELECT
            ti.test_code,
            ti.test_name,
            COUNT(ti.id)                                                         AS total,
            COUNT(CASE WHEN ti.status = 'completed'  THEN 1 END)                AS completed,
            COUNT(CASE WHEN e.is_tat_breached = 1     THEN 1 END)               AS delayed,
            ROUND(AVG(e.actual_total_eta_mins)::numeric, 1)                     AS avg_actual_tat_mins,
            ROUND(AVG(e.total_eta_mins)::numeric, 1)                            AS avg_expected_tat_mins,
            CASE WHEN COUNT(e.id) > 0
                 THEN ROUND(
                     (1.0 - COUNT(CASE WHEN e.is_tat_breached=1 THEN 1 END)::numeric
                           / NULLIF(COUNT(e.id), 0)) * 100, 1)
                 ELSE 100.0
            END                                                                  AS sla_percent
        FROM tat_test_instance ti
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        WHERE ti.test_code IS NOT NULL
        GROUP BY ti.test_code, ti.test_name
        ORDER BY total DESC
        LIMIT 100
    """)

    # Per-lab breakdown: test_code × lab_id
    per_lab_rows = await _pool.fetch("""
        SELECT
            ti.test_code,
            l.lab_name,
            l.id AS lab_id,
            COUNT(ti.id)                                                         AS total,
            COUNT(CASE WHEN ti.status = 'completed'  THEN 1 END)                AS completed,
            COUNT(CASE WHEN e.is_tat_breached = 1     THEN 1 END)               AS delayed,
            ROUND(AVG(e.actual_total_eta_mins)::numeric, 1)                     AS avg_actual_tat_mins,
            CASE WHEN COUNT(e.id) > 0
                 THEN ROUND(
                     (1.0 - COUNT(CASE WHEN e.is_tat_breached=1 THEN 1 END)::numeric
                           / NULLIF(COUNT(e.id), 0)) * 100, 1)
                 ELSE 100.0
            END                                                                  AS sla_percent
        FROM tat_test_instance ti
        JOIN tat_lab l ON l.id = ti.processing_lab_id
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        WHERE ti.test_code IS NOT NULL
          AND ti.processing_lab_id IS NOT NULL
        GROUP BY ti.test_code, l.id, l.lab_name
        ORDER BY ti.test_code, total DESC
        LIMIT 500
    """)

    # Group per_lab by test_code
    per_lab: Dict[str, list] = {}
    for r in per_lab_rows:
        code = r["test_code"]
        per_lab.setdefault(code, []).append(_row(r))

    global_result = []
    for r in global_rows:
        rec = _row(r)
        if rec:
            rec["per_lab"] = per_lab.get(rec["test_code"], [])
            global_result.append(rec)

    return {"tests": global_result, "total": len(global_result)}


# ── Lab Management Dashboard KPIs (new) ──────────────────────────────────────

async def get_lab_management_metrics() -> Dict[str, Any]:
    """
    Overall system KPIs for lab management dashboard.
    All 9 metrics calculated in a single optimized query.
    
    Metrics:
    1. Total Active Labs - count of labs that are available
    2. Total Tests Today - tests created today
    3. Total In Progress - tests in 'pending'/'processing' status
    4. Total Completed - tests completed today
    5. Delayed Tests - tests where actual_tat > expected_tat
    6. SLA Compliance % - (on_time / total_completed) * 100
    7. Avg Processing TAT - avg actual TAT across all completed tests
    8. Queue Load - count of active queue entries
    9. Avg Queue Wait - avg(queue_wait_mins) from tat_eta
    """
    row = await _pool.fetchrow("""
        SELECT
          -- 1. Total Active Labs
          (SELECT COUNT(*) FROM tat_lab WHERE is_available=1 AND is_active=1)
          AS total_active_labs,
          
          -- 2. Total Tests Today (created today)
          (SELECT COUNT(*) FROM tat_test_instance 
           WHERE DATE(created_at) = CURRENT_DATE)
          AS total_tests_today,
          
          -- 3. Total In Progress (pending status)
          (SELECT COUNT(*) FROM tat_test_instance 
           WHERE status IN ('pending', 'processing'))
          AS total_in_progress,
          
          -- 4. Total Completed Today
          (SELECT COUNT(*) FROM tat_test_instance 
           WHERE status = 'completed' AND DATE(created_at) = CURRENT_DATE)
          AS total_completed_today,
          
          -- 5. Delayed Tests (actual_tat > expected_tat)
          (SELECT COUNT(DISTINCT e.id) FROM tat_eta e
           WHERE e.is_tat_breached = 1)
          AS delayed_tests,
          
          -- 6. SLA Compliance % 
          CASE WHEN COUNT(DISTINCT e.id) > 0
               THEN ROUND(
                 (1.0 - COUNT(DISTINCT CASE WHEN e.is_tat_breached=1 THEN e.id END)::numeric
                      / COUNT(DISTINCT e.id)) * 100, 1)
               ELSE 100.0
          END AS sla_compliance_percent,
          
          -- 7. Avg Processing TAT (actual)
          ROUND(AVG(e.actual_total_eta_mins)::numeric, 1)
          AS avg_processing_tat_mins,
          
          -- 8. Queue Load (active queue entries)
          (SELECT COUNT(*) FROM tat_lab_queue 
           WHERE status NOT IN ('completed', 'skipped'))
          AS queue_load,
          
          -- 9. Avg Queue Wait Time
          ROUND(AVG(e.queue_wait_mins)::numeric, 1)
          AS avg_queue_wait_mins
        FROM tat_eta e
    """)
    
    if not row:
        # Return defaults if no data
        return {
            "total_active_labs": 0,
            "total_tests_today": 0,
            "total_in_progress": 0,
            "total_completed_today": 0,
            "delayed_tests": 0,
            "sla_compliance_percent": 100.0,
            "avg_processing_tat_mins": 0,
            "queue_load": 0,
            "avg_queue_wait_mins": 0,
        }
    
    return {
        "total_active_labs": row["total_active_labs"] or 0,
        "total_tests_today": row["total_tests_today"] or 0,
        "total_in_progress": row["total_in_progress"] or 0,
        "total_completed_today": row["total_completed_today"] or 0,
        "delayed_tests": row["delayed_tests"] or 0,
        "sla_compliance_percent": row["sla_compliance_percent"] or 100.0,
        "avg_processing_tat_mins": row["avg_processing_tat_mins"] or 0,
        "queue_load": row["queue_load"] or 0,
        "avg_queue_wait_mins": row["avg_queue_wait_mins"] or 0,
    }


async def get_labs_with_metrics() -> List[Dict[str, Any]]:
    """
    Enhanced lab list with per-lab metrics and status indicators.
    
    Per-lab metrics:
    - queue_size: active queue entries
    - avg_tat: average actual TAT
    - sla_percent: SLA compliance
    - delayed_tests: count of delayed tests
    - active_batches: count of pending batch assignments
    - utilization_percent: queue_size / max_concurrent_samples
    - status: 'healthy' / 'overloaded' / 'delayed'
    
    Status logic:
    - healthy: SLA > 90% AND queue_size <= threshold
    - overloaded: queue_size > threshold OR utilization > 80%
    - delayed: delayed_tests > 0
    """
    rows = await _pool.fetch("""
        SELECT
          l.id,
          l.lab_name,
          l.lab_code,
          l.is_available,
          l.max_concurrent_samples,
          l.default_processing_mins,
          l.next_available_time,
          
          -- Queue metrics
          (SELECT COUNT(*) FROM tat_lab_queue q
           WHERE q.lab_id = l.id AND q.status NOT IN ('completed','skipped'))
          AS queue_size,
          
          -- TAT metrics
          ROUND(AVG(e.actual_total_eta_mins)::numeric, 1)
          AS avg_tat_mins,
          
          -- SLA %
          CASE WHEN COUNT(DISTINCT e.id) > 0
               THEN ROUND(
                 (1.0 - COUNT(DISTINCT CASE WHEN e.is_tat_breached=1 THEN e.id END)::numeric
                      / COUNT(DISTINCT e.id)) * 100, 1)
               ELSE 100.0
          END AS sla_percent,
          
          -- Delayed tests
          COUNT(DISTINCT CASE WHEN e.is_tat_breached=1 THEN e.id END)
          AS delayed_tests,
          
          -- Active batches
          (SELECT COUNT(*) FROM tat_lab_batch_assignment ba
           WHERE ba.lab_id = l.id AND ba.status = 'assigned')
          AS active_batches,
          
          -- Total tests in this lab
          COUNT(DISTINCT ti.id)
          AS total_tests_processed
          
        FROM tat_lab l
        LEFT JOIN tat_test_instance ti ON ti.processing_lab_id = l.id
        LEFT JOIN tat_eta e ON e.sample_id = ti.sample_id
        WHERE l.is_active = 1
        GROUP BY l.id, l.lab_name, l.lab_code, l.is_available, l.max_concurrent_samples,
                 l.default_processing_mins, l.next_available_time
        ORDER BY l.lab_name
    """)
    
    labs_list = []
    for row in rows:
        row_dict = dict(row)
        
        # Calculate utilization percent
        max_concurrent = row_dict.get("max_concurrent_samples", 1) or 1
        queue_size = row_dict.get("queue_size", 0) or 0
        utilization_percent = round((queue_size / max_concurrent) * 100, 1) if max_concurrent > 0 else 0
        
        # Determine status
        sla_pct = row_dict.get("sla_percent", 100) or 100
        delayed = row_dict.get("delayed_tests", 0) or 0
        queue_threshold = max_concurrent * 2  # arbitrary threshold
        
        if delayed > 0:
            status = "delayed"
        elif queue_size > queue_threshold or utilization_percent > 80:
            status = "overloaded"
        elif sla_pct > 90:
            status = "healthy"
        else:
            status = "at_risk"
        
        row_dict["utilization_percent"] = utilization_percent
        row_dict["status"] = status
        
        labs_list.append(row_dict)
    
    return labs_list
