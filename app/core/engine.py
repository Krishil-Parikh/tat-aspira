"""
Core Engine — high-level orchestration used by API route handlers.

Coordinates: EDOS lookup → per-test routing → batch slot → DB write → hot cache push.

Heavy CPU work (batch assign, TAT parse) is synchronous but fast enough
that it does not block the event loop for real workloads.

Used by:
  - POST /api/accession  (legacy manual accession)
  - Potentially future admin-triggered reassignment endpoints
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg
import psycopg2
import psycopg2.extras
import pytz

from app.core.pg_pool import pooled_connection
from config.settings import cfg
from app.edos_loader import lookup_test
from app.services.scheduler import (
    assign_batch_slot,
    resolve_test_routing,
    resolve_processing_times,
    detect_tat_breach,
)
from app.core.hot_cache import push as cache_push

logger = logging.getLogger("engine")
_IST = pytz.timezone(cfg.ZONE)


def _pg_sync():
    """Synchronous psycopg2 connection — used for CPU-bound orchestration calls."""
    return pooled_connection()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Sample record builder ─────────────────────────────────────────────────────

def _build_cache_record(
    sample: Dict[str, Any],
    bill: Dict[str, Any],
    tests: list,
    eta: Optional[Dict],
) -> Dict[str, Any]:
    """
    Build a flat dict suitable for pushing into the hot pipeline cache.
    Keeps only the fields the Operations Dashboard needs for sub-ms reads.
    """
    return {
        "sample_id":          sample.get("id"),
        "accession_no":       sample.get("accession_no"),
        "status":             sample.get("status"),
        "priority":           sample.get("priority"),
        "assigned_lab_id":    sample.get("assigned_lab_id"),
        "total_tests":        sample.get("total_tests"),
        "completed_tests":    sample.get("completed_tests"),
        "collected_at":       str(sample.get("collected_at") or ""),
        "received_at":        str(sample.get("received_at") or ""),
        "arrived_at_lab":     str(sample.get("arrived_at_lab") or ""),
        "bill_id":            bill.get("id"),
        "external_bill_id":   bill.get("external_bill_id"),
        "client_type":        bill.get("client_type"),
        "patient_name":       bill.get("patient_name"),
        "eta_end":            str(eta.get("estimated_end_time") or "") if eta else "",
        "is_tat_breached":    eta.get("is_tat_breached", 0) if eta else 0,
        "total_eta_mins":     eta.get("total_eta_mins") if eta else None,
        "test_codes":         [t.get("test_code") for t in tests if t.get("test_code")],
        "cached_at":          _now().isoformat(),
    }


# ── Manual accession (legacy, used by POST /api/accession) ───────────────────

async def accession_sample_pg(
    pool: asyncpg.Pool,
    test_code:        str,
    accession_time:   Optional[datetime] = None,
    agreed_tat_hours: int                = 24,
    priority:         str                = "NORMAL",
    sample_id_hint:   Optional[str]      = None,
) -> Dict[str, Any]:
    """
    Manual sample accession flow (non-webhook path).

    Steps:
      1. Validate test code against EDOS catalog
      2. Look up test config in DB for processing_time + department
      3. Resolve lab via resolve_test_routing()
      4. Find next batch slot via assign_batch_slot()
      5. Insert sample + test instance + queue entry + ETA into PostgreSQL
      6. Push result into hot pipeline cache
      7. Return full assembled record

    CPU-heavy steps (routing, batch slot, TAT parse) are sync but do not
    block the event loop in practice — they complete in < 5 ms.
    """
    if accession_time is None:
        accession_time = _now()

    # 1. EDOS validation (in-memory, instant)
    edos = lookup_test(test_code=test_code.upper())
    if not edos:
        raise ValueError(f"Test code '{test_code}' not found in EDOS catalog")

    # 2–5. Sync DB work in a thread-pool-friendly psycopg2 connection
    with _pg_sync() as conn:
        cur = conn.cursor()

        # Look up test config
        cur.execute("""
            SELECT * FROM tat_test_type_config
            WHERE test_code=%s AND is_active=1
        """, (test_code.upper(),))
        tc = cur.fetchone()

        dept_id   = tc["department_id"]   if tc else None
        dept_name = tc["department_name"] if tc else None
        proc_mins = tc["processing_time_mins"] if tc else 60

        # Resolve lab
        lab_id, routing_reason = resolve_test_routing(dept_id, test_code.upper(), cur)

        # Batch slot (reserve lab capacity for proc_mins)
        slot = assign_batch_slot(lab_id, accession_time, cur, proc_mins)
        batch_time = slot["batch_time"]

        from datetime import timedelta
        estimated_end = batch_time + timedelta(minutes=proc_mins)

        # TAT breach
        pred_tat_hrs = tc.get("predefined_tat_hours") if tc else None
        is_breached, pred_mins, breach_by = detect_tat_breach(
            accession_time, estimated_end, pred_tat_hrs
        )

        queue_wait = int((batch_time - accession_time).total_seconds() / 60)
        total_eta  = int((estimated_end - accession_time).total_seconds() / 60)

        conn.commit()

    # 5. Manual accession is a PREVIEW / CALCULATION-ONLY path.
    # The full pipeline entry is created via the BILL_GENERATE webhook from the LIS.
    # We intentionally do NOT insert a tat_bill or tat_sample row here because:
    #   - The webhook flow owns the canonical record creation.
    #   - Manual accession is used only for ETA estimation at the counter.
    # FIX BUG-006: The original code had `if False:` around a DB insert block,
    # causing the block to silently never execute with no warning to the caller.
    # We now document this intent explicitly and surface it in the response.

    # 6. Build and push cache record (partial — calculation only, no DB IDs)
    cache_record = {
        "accession_no":    sample_id_hint or test_code.upper(),
        "status":          "batch_assigned",
        "priority":        priority,
        "assigned_lab_id": lab_id,
        "routing_reason":  routing_reason,
        "test_codes":      [test_code.upper()],
        "client_type":     "walk_in",
        "eta_end":         estimated_end.isoformat(),
        "is_tat_breached": 1 if is_breached else 0,
        "total_eta_mins":  total_eta,
        "batch_time":      batch_time.isoformat(),
        "cached_at":       _now().isoformat(),
        "source":          "manual_accession",
    }
    cache_push(cache_record)

    # 7. Return full result
    # FIX BUG-006: Expose 'mode' flag so callers know this is calculation-only
    # and no DB record (tat_bill / tat_sample) was created.
    return {
        "mode":            "preview_only",   # ← no DB row created; webhook flow owns persistence
        "test_code":       test_code.upper(),
        "test_name":       edos.get("test_name", ""),
        "lab_id":          lab_id,
        "routing_reason":  routing_reason,
        "batch_time":      batch_time.isoformat(),
        "estimated_end":   estimated_end.isoformat(),
        "queue_wait_mins": queue_wait,
        "total_eta_mins":  total_eta,
        "predefined_tat_mins": pred_mins,
        "is_tat_breached": is_breached,
        "breach_by_mins":  breach_by,
        "is_fallback_slot": slot.get("is_fallback", False),
        "note": (
            "Manual accession — ETA calculated only. "
            "Use POST /api/webhook with BILL_GENERATE for full pipeline entry."
        ),
    }


# ── Cache push helper (called from webhook_processor after key events) ────────

def push_sample_to_cache(cur, sample_id: int) -> None:
    """
    Synchronous helper called inside Celery webhook handlers to push a
    freshly-updated sample record into the hot pipeline cache.

    Pulls sample + bill + tests + ETA in one round-trip, builds the
    flat cache record, and calls hot_cache.push().

    Safe to call from any handler — failures are caught and logged,
    never propagated (cache is best-effort).
    """
    try:
        cur.execute("""
            SELECT s.*, b.external_bill_id, b.client_type, b.patient_name,
                   b.org_name, b.id AS bill_internal_id
            FROM tat_sample s
            JOIN tat_bill b ON b.id = s.bill_id
            WHERE s.id = %s
        """, (sample_id,))
        row = cur.fetchone()
        if not row:
            return

        row = dict(row)
        bill = {
            "id":               row.pop("bill_internal_id", None),
            "external_bill_id": row.pop("external_bill_id", None),
            "client_type":      row.pop("client_type", "walk_in"),
            "patient_name":     row.pop("patient_name", None),
            "org_name":         row.pop("org_name", None),
        }

        cur.execute("""
            SELECT test_code, status, processing_lab_id, department_name
            FROM tat_test_instance
            WHERE sample_id=%s AND status != 'cancelled'
        """, (sample_id,))
        tests = [dict(t) for t in cur.fetchall()]

        cur.execute("SELECT * FROM tat_eta WHERE sample_id=%s", (sample_id,))
        eta_row = cur.fetchone()
        eta = dict(eta_row) if eta_row else None

        record = _build_cache_record(row, bill, tests, eta)
        cache_push(record)
        logger.debug("[ENGINE] Pushed sample_id=%d to hot cache", sample_id)

    except Exception as exc:
        logger.warning("[ENGINE] hot cache push failed for sample_id=%s: %s", sample_id, exc)
