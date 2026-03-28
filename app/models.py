"""Pydantic models for the TAT & Batch Monitoring System."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class SampleStatus(str, Enum):
    ACCESSIONED = "accessioned"
    BATCH_ASSIGNED = "batch_assigned"
    PROCESSING = "processing"
    COMPLETED = "completed"
    MISSED_BATCH = "missed_batch"


class TestConfig(BaseModel):
    """Configuration for a single laboratory test loaded from CSV."""
    row_number: int = 0
    state: str = ""
    city: str = ""
    test_code: str = ""
    test_name: str = ""
    mrp: float = 0.0
    group: str = ""
    specimen_type: str = ""
    method: str = ""
    temp: str = ""
    test_schedule: str = ""
    tat: str = ""
    action: str = ""


class AccessionRequest(BaseModel):
    """Request body for sample accession."""
    test_code: str
    accession_time: Optional[str] = None  # ISO format, defaults to now


class MissBatchRequest(BaseModel):
    """Request to simulate a missed batch."""
    pass


class SampleDocument(BaseModel):
    """A sample being tracked in MongoDB."""
    sample_id: str
    test_code: str
    test_name: str
    accession_time: datetime
    test_schedule: str
    tat_rule: str
    assigned_batch: datetime
    eta: datetime
    status: SampleStatus = SampleStatus.BATCH_ASSIGNED
    miss_count: int = 0
    original_eta: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class NotificationDocument(BaseModel):
    """Notification for missed batches and alerts."""
    notification_id: str
    sample_id: str
    test_code: str
    test_name: str
    notification_type: str = "missed_batch"
    message: str
    original_batch: Optional[datetime] = None
    new_batch: Optional[datetime] = None
    original_eta: Optional[datetime] = None
    new_eta: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    read: bool = False
