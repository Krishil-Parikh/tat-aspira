"""Core engine for TAT calculation, batch scheduling, and missed batch detection."""

import uuid
from datetime import datetime
from typing import Optional, Tuple

from app.csv_loader import get_test_by_code
from app.schedule_parser import find_next_batch
from app.tat_parser import calculate_eta
from app.models import SampleStatus
from app import database as db


async def accession_sample(test_code: str, accession_time: datetime = None) -> dict:
    """Register a new sample and calculate its batch assignment and ETA.
    
    Args:
        test_code: The test code from the CSV
        accession_time: When the sample was received (defaults to now)
        
    Returns:
        The complete sample document
        
    Raises:
        ValueError: If test code not found or schedule can't be parsed
    """
    test = get_test_by_code(test_code)
    if not test:
        raise ValueError(f"Test code '{test_code}' not found in the database")

    if accession_time is None:
        accession_time = datetime.now()
    # Strip timezone info to avoid naive vs aware comparison
    if accession_time.tzinfo is not None:
        accession_time = accession_time.replace(tzinfo=None)

    # Find next batch
    next_batch = find_next_batch(accession_time, test.test_schedule)
    if next_batch is None:
        raise ValueError(
            f"Cannot parse schedule '{test.test_schedule}' for test {test_code}"
        )

    # Calculate ETA
    eta = calculate_eta(next_batch, test.tat)
    if eta is None:
        raise ValueError(
            f"Cannot parse TAT '{test.tat}' for test {test_code}"
        )

    sample_id = f"S-{uuid.uuid4().hex[:8].upper()}"

    sample_doc = {
        "sample_id": sample_id,
        "test_code": test.test_code,
        "test_name": test.test_name,
        "accession_time": accession_time,
        "test_schedule": test.test_schedule,
        "tat_rule": test.tat,
        "assigned_batch": next_batch,
        "eta": eta,
        "status": SampleStatus.BATCH_ASSIGNED.value,
        "miss_count": 0,
        "original_eta": eta,
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }

    await db.insert_sample(sample_doc)
    return sample_doc


async def simulate_missed_batch(sample_id: str) -> Tuple[dict, dict]:
    """Simulate a missed batch for a sample.
    
    Finds the next available batch, recalculates ETA, and creates a notification.
    
    Args:
        sample_id: The sample to mark as missed
        
    Returns:
        Tuple of (updated_sample, notification)
        
    Raises:
        ValueError: If sample not found
    """
    sample = await db.get_sample(sample_id)
    if not sample:
        raise ValueError(f"Sample '{sample_id}' not found")

    test = get_test_by_code(sample["test_code"])
    if not test:
        raise ValueError(f"Test code '{sample['test_code']}' not found")

    old_batch = sample["assigned_batch"]
    old_eta = sample["eta"]
    original_eta = sample.get("original_eta", old_eta)

    # Find next batch AFTER the missed one
    next_batch = find_next_batch(old_batch, test.test_schedule)
    if next_batch is None:
        raise ValueError("Cannot find next batch")

    # Recalculate ETA
    new_eta = calculate_eta(next_batch, test.tat)
    if new_eta is None:
        raise ValueError("Cannot calculate new ETA")

    miss_count = sample.get("miss_count", 0) + 1

    # Update sample in DB
    update_data = {
        "assigned_batch": next_batch,
        "eta": new_eta,
        "status": SampleStatus.MISSED_BATCH.value,
        "miss_count": miss_count,
        "original_eta": original_eta,
    }
    await db.update_sample(sample_id, update_data)

    # Create notification
    notif_id = f"N-{uuid.uuid4().hex[:8].upper()}"
    
    # Format readable dates
    old_batch_str = old_batch.strftime("%A %I:%M %p") if isinstance(old_batch, datetime) else str(old_batch)
    new_batch_str = next_batch.strftime("%A %I:%M %p")
    old_eta_str = old_eta.strftime("%A %I:%M %p") if isinstance(old_eta, datetime) else str(old_eta)
    new_eta_str = new_eta.strftime("%A %I:%M %p")

    notification = {
        "notification_id": notif_id,
        "sample_id": sample_id,
        "test_code": sample["test_code"],
        "test_name": sample["test_name"],
        "notification_type": "missed_batch",
        "message": (
            f"⚠️ Sample {sample_id} for {sample['test_name']} missed the "
            f"{old_batch_str} batch. Reassigned to {new_batch_str} batch. "
            f"Updated report ETA: {new_eta_str}."
        ),
        "original_batch": old_batch,
        "new_batch": next_batch,
        "original_eta": old_eta,
        "new_eta": new_eta,
        "created_at": datetime.now(),
        "read": False,
    }
    await db.insert_notification(notification)

    # Fetch updated sample
    updated_sample = await db.get_sample(sample_id)
    return updated_sample, notification


def calculate_eta_standalone(test_code: str, accession_time: datetime = None) -> Optional[dict]:
    """Standalone ETA calculation without database (for CLI mode).
    
    Returns a dict with batch and ETA info, or None.
    """
    test = get_test_by_code(test_code)
    if not test:
        return None

    if accession_time is None:
        accession_time = datetime.now()
    if accession_time.tzinfo is not None:
        accession_time = accession_time.replace(tzinfo=None)

    next_batch = find_next_batch(accession_time, test.test_schedule)
    if next_batch is None:
        return None

    eta = calculate_eta(next_batch, test.tat)
    if eta is None:
        return None

    return {
        "test_code": test.test_code,
        "test_name": test.test_name,
        "accession_time": accession_time,
        "test_schedule": test.test_schedule,
        "tat_rule": test.tat,
        "assigned_batch": next_batch,
        "eta": eta,
    }


def simulate_missed_batch_standalone(test_code: str, accession_time: datetime = None) -> Optional[dict]:
    """Standalone missed batch simulation for CLI mode."""
    result = calculate_eta_standalone(test_code, accession_time)
    if not result:
        return None

    test = get_test_by_code(test_code)
    original_batch = result["assigned_batch"]
    original_eta = result["eta"]

    # Find next batch after missed one
    next_batch = find_next_batch(original_batch, test.test_schedule)
    if next_batch is None:
        return None

    new_eta = calculate_eta(next_batch, test.tat)
    if new_eta is None:
        return None

    return {
        **result,
        "original_batch": original_batch,
        "original_eta": original_eta,
        "new_batch": next_batch,
        "new_eta": new_eta,
        "message": (
            f"Sample for {test.test_name} missed the "
            f"{original_batch.strftime('%A %I:%M %p')} batch.\n"
            f"Reassigned to {next_batch.strftime('%A %I:%M %p')} batch.\n"
            f"Updated report ETA: {new_eta.strftime('%A %B %d, %I:%M %p')}."
        ),
    }
