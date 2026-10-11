"""
Queue Prioritization Service

Recalculates queue priority based on SLA urgency, processing capability,
and queue pressure. Per PRD Section 13.1.

Priority scoring considers:
- SLA urgency (time remaining to deadline)
- Processing capability (lab capacity)
- Queue pressure (queue length)
- Routing status
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger("queue_prioritizer")


def calculate_priority_score(
    eta_minutes_remaining: Optional[int],
    predefined_tat_mins: Optional[int],
    queue_position: Optional[int],
    is_urgent: bool = False,
    queue_length: int = 0,
) -> int:
    """
    Calculate a priority score (1-10, lower is higher priority).
    
    Scoring logic:
    - SLA urgency: If < 30% of TAT remaining, boost priority
    - Urgent flag: Always priority 1
    - Queue pressure: If queue is long, prioritize newer samples less
    
    Args:
        eta_minutes_remaining: Minutes until estimated completion
        predefined_tat_mins: Total TAT in minutes
        queue_position: Position in queue
        is_urgent: Whether sample is marked urgent
        queue_length: Total queue length at the lab
    
    Returns:
        Priority score (1-10, 1 = highest, 10 = lowest)
    """
    # Urgent samples always get highest priority
    if is_urgent:
        return 1
    
    # If no ETA info, use default priority
    if eta_minutes_remaining is None or predefined_tat_mins is None:
        return 5
    
    # Calculate SLA urgency percentage
    tat_remaining_pct = eta_minutes_remaining / predefined_tat_mins if predefined_tat_mins > 0 else 1.0
    
    # SLA urgency scoring
    if tat_remaining_pct < 0.3:
        # Less than 30% of TAT remaining - very urgent
        sla_priority = 1
    elif tat_remaining_pct < 0.5:
        # Less than 50% of TAT remaining - urgent
        sla_priority = 2
    elif tat_remaining_pct < 0.7:
        # Less than 70% of TAT remaining - moderate
        sla_priority = 3
    else:
        # Plenty of time - normal
        sla_priority = 5
    
    # Queue pressure adjustment
    # If queue is long (> 20), deprioritize items far back in queue
    if queue_length > 20 and queue_position and queue_position > 10:
        queue_penalty = min(3, queue_position // 10)
        sla_priority = min(10, sla_priority + queue_penalty)
    
    return sla_priority


def recalculate_sample_priority(
    sample_id: int,
    cur,
) -> Optional[int]:
    """
    Recalculate priority for a sample based on current SLA status.
    
    Args:
        sample_id: Sample ID
        cur: Database cursor
    
    Returns:
        New priority score (1-10), or None if sample not found
    """
    # Get sample and ETA info
    cur.execute("""
        SELECT s.id, s.priority as current_priority, s.is_urgent,
               e.total_eta_mins, e.predefined_tat_mins, e.is_tat_breached
        FROM tat_sample s
        LEFT JOIN tat_eta e ON e.sample_id = s.id
        WHERE s.id = %s
    """, (sample_id,))
    row = cur.fetchone()
    if not row:
        return None
    
    # Get queue position
    cur.execute("""
        SELECT COUNT(*) as queue_pos
        FROM tat_lab_queue
        WHERE lab_id = (SELECT assigned_lab_id FROM tat_sample WHERE id = %s)
          AND status = 'scheduled'
          AND arrival_time < (SELECT arrival_time FROM tat_lab_queue WHERE sample_id = %s LIMIT 1)
    """, (sample_id, sample_id))
    queue_pos_row = cur.fetchone()
    queue_position = queue_pos_row["queue_pos"] if queue_pos_row else 0
    
    # Get queue length
    cur.execute("""
        SELECT COUNT(*) as queue_len
        FROM tat_lab_queue
        WHERE lab_id = (SELECT assigned_lab_id FROM tat_sample WHERE id = %s)
          AND status = 'scheduled'
    """, (sample_id,))
    queue_len_row = cur.fetchone()
    queue_length = queue_len_row["queue_len"] if queue_len_row else 0
    
    # Calculate new priority
    new_priority = calculate_priority_score(
        eta_minutes_remaining=row["total_eta_mins"],
        predefined_tat_mins=row["predefined_tat_mins"],
        queue_position=queue_position,
        is_urgent=row["is_urgent"] == 1,
        queue_length=queue_length,
    )
    
    # If SLA is breached, boost to highest priority
    if row["is_breached"] == 1:
        new_priority = 1
    
    # Update sample if priority changed
    if new_priority != row["current_priority"]:
        cur.execute("""
            UPDATE tat_sample
            SET priority = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_priority, sample_id))
        logger.info(
            "[QUEUE_PRIORITIZER] Updated priority sample_id=%d %d → %d",
            sample_id, row["current_priority"], new_priority
        )
    
    return new_priority


def recalculate_lab_queue_priorities(lab_id: int, cur) -> int:
    """
    Recalculate priorities for all samples in a lab's queue.
    
    Args:
        lab_id: Lab ID
        cur: Database cursor
    
    Returns:
        Number of samples whose priority was updated
    """
    # Get all samples in lab's queue
    cur.execute("""
        SELECT q.sample_id
        FROM tat_lab_queue q
        JOIN tat_sample s ON s.id = q.sample_id
        WHERE q.lab_id = %s AND q.status = 'scheduled'
    """, (lab_id,))
    samples = cur.fetchall()
    
    updated_count = 0
    for row in samples:
        sample_id = row["sample_id"]
        old_priority = recalculate_sample_priority(sample_id, cur)
        if old_priority is not None:
            updated_count += 1
    
    logger.info(
        "[QUEUE_PRIORITIZER] Recalculated priorities for lab_id=%d updated=%d",
        lab_id, updated_count
    )
    
    return updated_count
