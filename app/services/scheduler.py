"""
app/services/scheduler.py — Lab routing and batch scheduling logic.

Called by the Celery webhook processor (process_webhook_task).
All DB operations run within the caller's transaction (conn/cur).

Key changes vs v1:
  - schedule_sample() REMOVED (was queue-based)
  - assign_batch_slot() ADDED (batch-based, triggered on SAMPLE_RECEIVED)
  - resolve_test_routing() ADDED (per-test lab assignment)
  - route_sample_to_lab() KEPT (reused by resolve_test_routing as primary path)
  - resolve_processing_times() KEPT
  - detect_tat_breach() KEPT

H1 FIX (applied to assign_batch_slot):
  The old two-statement pattern (SELECT COUNT then separate INSERT in
  webhook_processor.py) had a TOCTOU race window.  assign_batch_slot now
  performs the INSERT into tat_lab_batch_assignment atomically via a CTE
  that guards capacity in the same SQL round-trip.  The FOR UPDATE lock on
  tat_lab serialises concurrent calls for the same lab.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone, time, date
from typing import Dict, List, Optional, Tuple

from app.edos_loader import lookup_test as _edos_lookup
from app.tat_parser import parse_tat as _parse_tat

import psycopg2
import psycopg2.extras

from app.core.pg_pool import pooled_connection
from config.settings import cfg
from app.utils.datetime_utils import get_naive_utc_now

logger = logging.getLogger("scheduler")


def _pg_conn():
    return pooled_connection()


def _now() -> datetime:
    return get_naive_utc_now()


# ── Processing time resolution ────────────────────────────────────────────────

def resolve_processing_times(
    test_codes: List[str],
    lab_id: int,
    cur,
) -> Tuple[int, int, int]:
    """
    Returns (sum_mins, max_mins, active_mins).
    Resolution order per test:
      1. tat_lab_test_override (lab-specific)
      2. tat_test_type_config  (global)
      3. tat_lab.default_processing_mins (fallback)
    """
    cur.execute("SELECT default_processing_mins FROM tat_lab WHERE id=%s", (lab_id,))
    lab_row = cur.fetchone()
    default_mins = lab_row["default_processing_mins"] if lab_row else 60

    cur.execute(
        "SELECT test_code, processing_time_mins FROM tat_test_type_config WHERE test_code = ANY(%s) AND is_active=1",
        (test_codes,)
    )
    config_map = {r["test_code"]: r["processing_time_mins"] for r in cur.fetchall()}

    cur.execute(
        "SELECT test_code, processing_time_mins FROM tat_lab_test_override WHERE lab_id=%s AND test_code = ANY(%s) AND is_active=1",
        (lab_id, test_codes)
    )
    override_map = {r["test_code"]: r["processing_time_mins"] for r in cur.fetchall()}

    total_sum, total_max, missing = 0, 0, []
    for code in test_codes:
        if code in override_map:
            mins = override_map[code]
        elif code in config_map:
            mins = config_map[code]
        else:
            # EDOS fallback: check in-memory catalog for tat_raw
            edos_rec = _edos_lookup(test_code=code)
            if edos_rec and edos_rec.get("tat_raw"):
                parsed = _parse_tat(edos_rec["tat_raw"])
                if parsed is not None:
                    days_offset, hours, _ = parsed
                    # Convert EDOS TAT to processing minutes:
                    # days_offset == 0 + "hr" in raw → raw hours
                    # else → total hours = days_offset * 24 + hours
                    if days_offset == 0 and "hr" in edos_rec["tat_raw"].lower():
                        mins = hours * 60
                    else:
                        mins = (days_offset * 24 + hours) * 60
                    logger.debug(
                        "[SCHEDULER] EDOS TAT fallback code=%s tat_raw='%s' → %d mins",
                        code, edos_rec["tat_raw"], mins,
                    )
                else:
                    mins = default_mins
                    missing.append(code)
            else:
                mins = default_mins
                missing.append(code)
        total_sum += mins
        if mins > total_max:
            total_max = mins

    if missing:
        logger.warning("[SCHEDULER] No test config for codes %s — using lab default %d min.", missing, default_mins)

    cur.execute("SELECT processing_mode FROM tat_lab WHERE id=%s", (lab_id,))
    mode_row = cur.fetchone()
    mode = mode_row["processing_mode"] if mode_row else "max"
    # mode=max → parallel processing (TAT = max of all tests)
    # mode=sum → sequential processing (TAT = sum of all tests)
    active_mins = total_max if mode == "max" else total_sum

    return total_sum, total_max, active_mins


# ── Per-test lab routing ──────────────────────────────────────────────────────

def resolve_test_routing(
    department_id: Optional[int],
    test_code: Optional[str],
    cur,
    context: Optional[Dict] = None,
) -> Tuple[int, str]:
    """
    Determines the processing_lab for a single test instance.

    Resolution order:
      1. OUTSOURCE CHECK — if test is marked as outsourced in tat_lab_edos, route to vendor
      2. PRIMARY — tat_lab_capability match for this department_id
      3. FALLBACK — tat_test_routing admin table
      4. LAST RESORT — MAIN/fallback lab
    Returns (processing_lab_id, routing_reason).
    """
    # ✅ FIX #13: Check if test is outsourced before normal routing
    if test_code:
        # Check tat_lab_edos for is_outsourced flag
        cur.execute("""
            SELECT lab_id, outsource_vendor_name, outsource_buffer_mins
            FROM tat_lab_edos
            WHERE test_code=%s AND is_outsourced=1 AND is_active=1
            LIMIT 1
        """, (test_code,))
        outsource_row = cur.fetchone()
        if outsource_row:
            vendor_name = outsource_row["outsource_vendor_name"]
            logger.info(
                "[SCHEDULER] Test %s is outsourced to vendor %s (lab_id=%d)",
                test_code, vendor_name or "unknown", outsource_row["lab_id"]
            )
            return outsource_row["lab_id"], f"outsource_vendor:{vendor_name or 'unknown'}"

    # Use context if provided to avoid DB hits
    if context:
        # 1. Primary: capability
        if department_id and department_id in context.get("capabilities", {}):
            return context["capabilities"][department_id], "capability_match"

        # 2. Fallback: admin routing — test-specific
        if test_code and test_code in context.get("test_routing", {}):
            return context["test_routing"][test_code], "admin_test_routing"

        # 2b. Fallback: admin routing — dept-specific
        if department_id and department_id in context.get("dept_routing", {}):
            return context["dept_routing"][department_id], "admin_dept_routing"

        # 3. Last resort: fallback lab
        if context.get("fallback_lab_id"):
            return context["fallback_lab_id"], "main_fallback_alert"

    # Fallback to DB lookups if no context
    if department_id:
        cur.execute("""
            SELECT lc.lab_id
            FROM tat_lab_capability lc
            JOIN tat_lab l ON l.id = lc.lab_id
            WHERE lc.department_id = %s AND lc.is_active = 1
              AND l.is_active = 1 AND l.is_available = 1 AND l.is_fallback = 0
            ORDER BY l.id LIMIT 1
        """, (department_id,))
        row = cur.fetchone()
        if row: return row["lab_id"], "capability_match"

    if test_code:
        cur.execute("SELECT processing_lab_id FROM tat_test_routing WHERE test_code=%s AND is_active=1 LIMIT 1", (test_code,))
        row = cur.fetchone()
        if row: return row["processing_lab_id"], "admin_test_routing"

    if department_id:
        cur.execute("SELECT processing_lab_id FROM tat_test_routing WHERE department_id=%s AND test_code IS NULL AND is_active=1 LIMIT 1", (department_id,))
        row = cur.fetchone()
        if row: return row["processing_lab_id"], "admin_dept_routing"

    # REMOVED: Silent fallback to lab ID 1
    # cur.execute("SELECT id FROM tat_lab WHERE is_fallback=1 AND is_active=1 AND is_available=1 LIMIT 1")
    # row = cur.fetchone()
    # if row: return row["id"], "main_fallback_alert"

    return None, "no_lab_capable_for_test"


# ── Lab routing (sample-level, kept for backward compatibility) ───────────────

def route_sample_to_lab(
    department_ids: List[int],
    cur,
) -> Tuple[int, str]:
    """
    Find the best lab for a sample covering ALL required departments.
    Used as a convenience wrapper; per-test routing uses resolve_test_routing().
    """
    if not department_ids:
        cur.execute("SELECT id FROM tat_lab WHERE is_fallback=1 AND is_active=1 AND is_available=1 LIMIT 1")
        row = cur.fetchone()
        if row:
            return row["id"], "no_department_info_fallback"
        raise ValueError("No fallback lab available")

    cur.execute("""
        SELECT lab_id, COUNT(DISTINCT department_id) AS covered
        FROM tat_lab_capability
        WHERE department_id = ANY(%s) AND is_active=1
        GROUP BY lab_id
        HAVING COUNT(DISTINCT department_id) = %s
    """, (department_ids, len(set(department_ids))))
    capable_lab_ids = [r["lab_id"] for r in cur.fetchall()]

    if capable_lab_ids:
        cur.execute("""
            SELECT id FROM tat_lab
            WHERE id = ANY(%s) AND is_active=1 AND is_available=1 AND is_fallback=0
            ORDER BY COALESCE(next_available_time, '2000-01-01') ASC
            LIMIT 1
        """, (capable_lab_ids,))
        row = cur.fetchone()
        if row:
            return row["id"], "department_match"

        cur.execute("""
            SELECT id FROM tat_lab
            WHERE id = ANY(%s) AND is_active=1 AND is_available=1 AND is_fallback=1
            LIMIT 1
        """, (capable_lab_ids,))
        row = cur.fetchone()
        if row:
            return row["id"], "capable_fallback"

    # REMOVED: Silent fallback to lab ID 1
    # cur.execute("SELECT id FROM tat_lab WHERE is_fallback=1 AND is_active=1 AND is_available=1 LIMIT 1")
    # row = cur.fetchone()
    # if not row:
    #     raise ValueError("No lab available (all labs down or unconfigured)")
    # return row["id"], "main_fallback"

    return None, "unassigned_no_capable_lab"


# ── SLA-aware queue prioritization ────────────────────────────────────────────

def compute_queue_priority(
    cur,
    sample_id: int,
    lab_id: int,
    sla_deadline: Optional[datetime] = None,
) -> int:
    """
    Compute dynamic queue priority (1-10 scale) based on SLA urgency.
    Matches convention in queue_prioritizer.py: 1 = highest, 10 = lowest.

    Per PRD Section 13.1, considers:
      - SLA urgency (distance to deadline)
      - Queue pressure (items already queued)
      - Routing status
      - Sample urgency flag
    """
    # 1. Check sample urgency flag (highest weight)
    cur.execute("SELECT is_urgent FROM tat_sample WHERE id=%s", (sample_id,))
    smp_row = cur.fetchone()
    if smp_row and smp_row["is_urgent"]:
        return 1

    base_priority = 5  # default midpoint

    # 2. Check SLA breach risk (distance to deadline)
    if sla_deadline:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mins_until_deadline = int((sla_deadline - now).total_seconds() / 60)

        if mins_until_deadline < 0:
            base_priority = 1  # Already breached!
        elif mins_until_deadline < 60:
            base_priority = max(2, base_priority - 2)  # < 1h = increase priority
        elif mins_until_deadline < 240:
            base_priority = max(3, base_priority - 1)  # < 4h = slight increase

    # 3. Check queue pressure (how many items already in this lab's queue)
    cur.execute("""
        SELECT COUNT(*) as queue_size
        FROM tat_lab_queue
        WHERE lab_id=%s AND status NOT IN ('completed', 'skipped')
    """, (lab_id,))
    queue_row = cur.fetchone()
    queue_size = queue_row["queue_size"] if queue_row else 0

    if queue_size > 20:
        base_priority = min(10, base_priority + 2)  # Very high queue pressure = lower priority
    elif queue_size > 10:
        base_priority = min(10, base_priority + 1)  # High queue pressure = lower priority

    # 4. Check if sample has routing issues (unassigned tests)
    cur.execute("""
        SELECT COUNT(*) as unassigned_count
        FROM tat_test_instance
        WHERE sample_id=%s AND processing_lab_id IS NULL
    """, (sample_id,))
    unassigned_row = cur.fetchone()
    if unassigned_row and unassigned_row["unassigned_count"] > 0:
        base_priority = max(1, base_priority - 1)  # Unassigned = higher priority

    return max(1, min(10, base_priority))  # Ensure 1-10 range


# ── Batch scheduling ──────────────────────────────────────────────────────────

def assign_batch_slot(
    lab_id: int,
    received_time: datetime,
    cur,
    processing_mins: Optional[int] = None,
    sample_id: Optional[int] = None,
) -> Dict:
    """
    Find the next available batch slot for this lab (>= received_time) and
    atomically reserve it in tat_lab_batch_assignment.

    H1 FIX — Race condition eliminated
    ===================================
    The old pattern split capacity-check and INSERT across two statements:
      1. SELECT COUNT(*) FROM tat_lab_batch_assignment  (in this function)
      2. INSERT INTO tat_lab_batch_assignment            (in webhook_processor.py)

    Between steps 1 and 2, a concurrent Celery thread (same or different worker)
    could pass the same capacity check and both insert into the same slot,
    causing slot overbooking.

    Fix: when sample_id is provided, a single CTE atomically checks capacity
    AND inserts in one SQL round-trip.  The FOR UPDATE lock on tat_lab
    serialises concurrent calls for the same lab so the count inside the
    CTE is always accurate.

    Backwards compat: sample_id=None keeps the old return dict shape so
    callers that still do their own INSERT (legacy path) are unaffected.

    Args:
        lab_id:          Internal lab id.
        received_time:   Sample arrival time ("not before" lower bound).
        cur:             psycopg2 cursor inside the caller's transaction.
        processing_mins: If given, advance tat_lab.next_available_time.
        sample_id:       If given, INSERT into tat_lab_batch_assignment
                         atomically inside this function (preferred path).

    Returns dict with:
      batch_time, batch_date, estimated_start_time, batch_schedule_id,
      is_fallback, slot_reserved
    """
    if received_time.tzinfo is not None:
        received_time = received_time.replace(tzinfo=None)

    # ── LOCK: serialise scheduling for this lab ───────────────────────────────
    # The row-level lock guarantees that concurrent tasks for the SAME lab
    # execute their capacity check + slot selection one at a time.
    cur.execute("SELECT id FROM tat_lab WHERE id = %s FOR UPDATE", (lab_id,))

    # ── Fetch batch schedules ─────────────────────────────────────────────────
    cur.execute("""
        SELECT
            lbs.id,
            lbs.batch_time,
            lbs.batch_day,
            lbs.max_capacity
        FROM tat_lab_batch_schedule lbs
        WHERE lbs.lab_id=%s AND lbs.is_active=1
        ORDER BY lbs.batch_time
    """, (lab_id,))
    schedules = cur.fetchall()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_next_available(batch_dt: datetime) -> None:
        """Advance lab.next_available_time to the end of the reserved slot."""
        if processing_mins is not None:
            new_next = batch_dt + timedelta(minutes=processing_mins)
            cur.execute(
                "UPDATE tat_lab SET next_available_time=%s WHERE id=%s",
                (new_next, lab_id),
            )

    def _atomic_reserve(batch_dt: datetime, sched_id: Optional[int],
                        max_cap: int, bd) -> bool:
        """
        Atomically insert the batch-assignment row only when capacity allows.

        Uses a two-step CTE:
          capacity_check — counts existing non-missed/cancelled rows for this
                           slot inside the FOR UPDATE transaction (accurate).
          do_insert      — inserts only when used < max_capacity.

        Returns True  → slot successfully reserved (or legacy path, no sample_id).
        Returns False → slot was already full (concurrent fill on a different
                        lab that shares this batch_time — move to next slot).
        """
        if sample_id is None:
            # Legacy path: caller inserts into tat_lab_batch_assignment separately.
            # We still return True because the FOR UPDATE lock already protects
            # the count, so the capacity check above is safe.
            return True

        cur.execute("""
            WITH capacity_check AS (
                SELECT COUNT(*) AS used
                FROM tat_lab_batch_assignment
                WHERE lab_id     = %s
                  AND batch_time = %s
                  AND status NOT IN ('missed', 'cancelled')
            ),
            do_insert AS (
                INSERT INTO tat_lab_batch_assignment
                    (lab_id, sample_id, batch_date, batch_time,
                     batch_schedule_id, status)
                SELECT %s, %s, %s, %s, %s, 'assigned'
                FROM capacity_check
                WHERE used < %s
                ON CONFLICT (sample_id, lab_id) DO UPDATE
                    SET batch_time        = EXCLUDED.batch_time,
                        batch_schedule_id = EXCLUDED.batch_schedule_id,
                        status            = 'assigned',
                        updated_at        = CURRENT_TIMESTAMP
                RETURNING id
            )
            SELECT id FROM do_insert
        """, (
            lab_id, batch_dt,                          # capacity_check params
            lab_id, sample_id, bd, batch_dt, sched_id, max_cap,  # do_insert params
        ))
        row = cur.fetchone()
        return row is not None   # None → WHERE used < max_cap filtered the insert

    # ── No schedule configured — graceful degradation ─────────────────────────
    if not schedules:
        logger.warning("[BATCH] No batch schedule for lab_id=%d — using fallback (+2h)", lab_id)
        batch_time = received_time + timedelta(hours=2)
        _update_next_available(batch_time)
        _atomic_reserve(batch_time, None, 999_999, received_time.date())
        return {
            "batch_time":           batch_time,
            "batch_date":           received_time.date(),
            "estimated_start_time": batch_time,
            "batch_schedule_id":    None,
            "is_fallback":          True,
            "slot_reserved":        True,
        }

    today = received_time.date()

    # Search up to 7 days ahead for an open slot.
    for day_offset in range(7):
        check_date = today + timedelta(days=day_offset)
        weekday = check_date.weekday()  # 0=Mon, 6=Sun

        for sched in schedules:
            # Filter by batch_day if set
            if sched["batch_day"] is not None and sched["batch_day"] != weekday:
                continue

            batch_dt = datetime.combine(check_date, sched["batch_time"])

            if batch_dt < received_time:
                continue  # slot already passed

            # Read current usage inside the locked transaction — accurate
            # because the FOR UPDATE prevents concurrent inserts for this lab.
            cur.execute("""
                SELECT COUNT(*) AS used_capacity
                FROM tat_lab_batch_assignment
                WHERE lab_id=%s AND batch_time=%s
                  AND status NOT IN ('missed', 'cancelled')
            """, (lab_id, batch_dt))
            used_capacity = cur.fetchone()["used_capacity"]

            if used_capacity < sched["max_capacity"]:
                reserved = _atomic_reserve(
                    batch_dt, sched["id"], sched["max_capacity"], check_date,
                )
                if not reserved:
                    # CTE found the slot concurrently filled by a different
                    # lab's schedule sharing the same batch_time — rare edge
                    # case; try the next slot.
                    logger.debug(
                        "[BATCH] Slot %s for lab=%d filled concurrently — trying next",
                        batch_dt.isoformat(), lab_id,
                    )
                    continue

                _update_next_available(batch_dt)
                return {
                    "batch_time":           batch_dt,
                    "batch_date":           check_date,
                    "estimated_start_time": batch_dt,
                    "batch_schedule_id":    sched["id"],
                    "is_fallback":          False,
                    "slot_reserved":        True,
                }

    # All slots full — use distant fallback
    logger.error("[BATCH] All slots full for lab_id=%d — using fallback (+4h)", lab_id)
    batch_time = received_time + timedelta(hours=4)
    _update_next_available(batch_time)
    _atomic_reserve(batch_time, None, 999_999, received_time.date())
    return {
        "batch_time":           batch_time,
        "batch_date":           received_time.date(),
        "estimated_start_time": batch_time,
        "batch_schedule_id":    None,
        "is_fallback":          True,
        "slot_reserved":        True,
    }


# ── TAT breach detection ──────────────────────────────────────────────────────

def detect_tat_breach(
    collection_time:      datetime,
    estimated_end_time:   datetime,
    predefined_tat_hours: Optional[float],
) -> Tuple[bool, Optional[int], Optional[int]]:
    """
    Returns (is_breached, predefined_tat_mins, breach_by_mins).
    ETA = batch_time + processing_time_mins; TAT check: ETA - collection_time > predefined.
    """
    if not predefined_tat_hours:
        return False, None, None

    predefined_mins = int(predefined_tat_hours * 60)
    total_eta_mins  = int((estimated_end_time - collection_time).total_seconds() / 60)
    breach_by       = total_eta_mins - predefined_mins
    is_breached     = breach_by > 0
    return is_breached, predefined_mins, (breach_by if is_breached else None)
