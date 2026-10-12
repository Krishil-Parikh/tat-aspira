"""
Pydantic v2 models — shared across API, workers, and services.
Covers both the new webhook event shapes and legacy API models.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class Priority(str, Enum):
    NORMAL  = "NORMAL"
    HIGH    = "HIGH"
    URGENT  = "URGENT"

class AlertType(str, Enum):
    MISSED_BATCH      = "missed_batch"
    SLA_BREACH        = "sla_breach"
    TAT_BREACH        = "tat_breach"
    DELAY_ESCALATION  = "delay_escalation"
    RESULT_COMPLETED  = "result_completed"

    # Alert types from Documentation section 8.1
    SLA_AT_RISK       = "sla_at_risk"
    SLA_BREACHED      = "sla_breached"
    SAMPLE_REJECTED   = "sample_rejected"
    REDRAW_OVERDUE    = "redraw_overdue"
    LAB_DOWNTIME      = "lab_downtime"
    QUEUE_OVERLOAD    = "queue_overload"

class AlertSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"

class WebhookType(str, Enum):
    BILL_GENERATE    = "BILL_GENERATE"
    BILL_UPDATE      = "BILL_UPDATE"
    BILL_CANCEL      = "BILL_CANCEL"
    SAMPLE_COLLECTED = "SAMPLE_COLLECTED"   # sample drawn at collection center
    SAMPLE_UNCOLLECTED = "SAMPLE_UNCOLLECTED" # collection reset/correction
    SAMPLE_RECEIVED  = "SAMPLE_RECEIVED"    # sample arrived at processing lab → scheduling trigger
    SAMPLE_REJECTED  = "SAMPLE_REJECTED"    # sample rejected at lab
    SAMPLE_REDRAWN   = "SAMPLE_REDRAWN"     # specimen redraw event — create new cycle
    SAMPLE_DISMISSED = "SAMPLE_DISMISSED"   # full sample cancelled/dismissed
    REPORT_SAVE      = "REPORT_SAVE"        # result values saved, not SLA closure
    REPORT_SUBMIT    = "REPORT_SUBMIT"      # report submitted → test completion driver
    REPORT_SIGNED    = "REPORT_SIGNED"      # report signed → final state
    REPORT_PDF       = "REPORT_PDF"         # PDF artifact storage only (no status change)
    TEST_DISMISSED   = "TEST_DISMISSED"     # individual test dismissed/cancelled
    SAMPLE_SENT_TO_EXTERNAL = "SAMPLE_SENT_TO_EXTERNAL"  # sample forwarded to external vendor

# ── Webhook Payload Sub-models ────────────────────────────────────────────────

class LabIdField(BaseModel):
    """labId can be int or object {labId: int, labName: str}"""
    labId:   int
    labName: Optional[str] = None

class OrgId(BaseModel):
    orgId:       Optional[int] = None
    orgFullName: Optional[str] = None

class SampleId(BaseModel):
    id:             Optional[int]  = None
    accessionNo:    Optional[str]  = None
    collectionTime: Optional[str]  = None
    type:           Optional[str]  = None
    name:           Optional[str]  = None
    toBatchProcessing: Optional[bool] = False

class DepartmentId(BaseModel):
    id:   Optional[int] = None
    name: Optional[str] = None

class ReportID(BaseModel):
    """One entry in labReportDetails / testDetails array."""
    labReportId:      Optional[int]   = None
    labReportIndex:   Optional[int]   = None
    testID:           Optional[int]   = None
    testCode:         Optional[str]   = None
    testName:         Optional[str]   = None
    testCategory:     Optional[str]   = None
    testAmount:       Optional[Any]   = None   # may be str or float
    dictionaryId:     Optional[int]   = None
    departmentId:     Optional[DepartmentId] = None
    sampleId:         Optional[SampleId]     = None
    collectedSampleId: Optional[SampleId]   = None
    sampleDate:       Optional[str]   = None
    reportDate:       Optional[str]   = None
    isRadiology:      Optional[bool]  = False
    isOutsourced:     Optional[bool]  = False

class CollectedSampleId(BaseModel):
    id:                Optional[int]  = None
    accessionNo:       Optional[str]  = None
    collectionTime:    Optional[str]  = None
    type:              Optional[str]  = None
    name:              Optional[str]  = None
    toBatchProcessing: Optional[bool] = False


# ── BILL_GENERATE Payload ─────────────────────────────────────────────────────

class BillGeneratePayload(BaseModel):
    webhookId:         Optional[int]  = None
    bill_id:           Optional[int]  = None
    billId:            Optional[int]  = None
    labId:             Union[int, LabIdField, None] = None
    billTime:          Optional[str]  = None
    totalAmount:       Optional[Any]  = None
    dueAmount:         Optional[Any]  = None
    billAdvance:       Optional[Any]  = None
    orgId:             Optional[Union[int, OrgId]] = None
    patientId:         Optional[int]  = None
    patientName:       Optional[str]  = None
    patientGender:     Optional[str]  = None
    patientAge:        Optional[str]  = None
    collectedSampleId: Optional[CollectedSampleId] = None
    labReportDetails:  Optional[List[ReportID]]    = None
    testDetails:       Optional[List[ReportID]]    = None
    sampleDate:        Optional[str]  = None
    reportDate:        Optional[str]  = None

    def get_lab_id(self) -> Optional[int]:
        if isinstance(self.labId, int):
            return self.labId
        if isinstance(self.labId, LabIdField):
            return self.labId.labId
        return None

    def get_org_id(self) -> Optional[int]:
        if isinstance(self.orgId, int):
            return self.orgId
        if isinstance(self.orgId, OrgId):
            return self.orgId.orgId
        return None

    def get_org_name(self) -> Optional[str]:
        if isinstance(self.orgId, OrgId):
            return self.orgId.orgFullName
        return None

    def get_report_list(self) -> List[ReportID]:
        return self.labReportDetails or self.testDetails or []


# ── BILL_UPDATE Payload ───────────────────────────────────────────────────────

class BillUpdatePayload(BillGeneratePayload):
    """Same shape as BillGenerate — activates bill/tests. Scheduling happens on SAMPLE_RECEIVED."""
    pass


class BillCancelPayload(BaseModel):
    webhookId:     Optional[int] = None
    bill_id:       Optional[int] = None
    billId:        Optional[int] = None
    billComment:   Optional[str] = None
    bill_comment:  Optional[str] = None
    apiUser:       Optional[str] = None


# ── SAMPLE_COLLECTED / SAMPLE_RECEIVED / SAMPLE_REJECTED Payload ──────────────

class SampleEventPayload(BaseModel):
    """Shared shape for SAMPLE_COLLECTED, SAMPLE_RECEIVED, SAMPLE_REJECTED."""
    webhookId:       Optional[int]               = None
    bill_id:         Optional[int]               = None   # may be absent; use sampleId as key
    billId:          Optional[int]               = None
    sampleId:        Optional[int]               = None
    accessionNo:     Optional[str]               = None
    labId:           Union[int, LabIdField, None] = None
    collectionTime:  Optional[str]               = None
    receivedTime:    Optional[str]               = None   # for SAMPLE_RECEIVED
    accessionDate:   Optional[str]               = None   # Livehealth SAMPLE_RECEIVED field
    rejectionReason: Optional[str]               = None   # for SAMPLE_REJECTED
    reason:          Optional[str]               = None
    isUrgent:        Optional[bool]              = False

    def get_lab_id(self) -> Optional[int]:
        if isinstance(self.labId, int):
            return self.labId
        if isinstance(self.labId, LabIdField):
            return self.labId.labId
        return None

    def get_event_key(self) -> Optional[int]:
        """Primary key for idempotency — bill_id preferred, sampleId fallback."""
        return self.bill_id or self.sampleId


class SampleSentExternalPayload(SampleEventPayload):
    externalLabName: Optional[str] = None
    sentTime: Optional[str] = None


# ── SAMPLE_REDRAWN Payload ────────────────────────────────────────────────────

class SampleRedrawPayload(BaseModel):
    """SAMPLE_REDRAWN event — creates new test instance cycle."""
    webhookId:       Optional[int]               = None
    bill_id:         Optional[int]               = None
    billId:          Optional[int]               = None
    sampleId:        Optional[int]               = None
    accessionNo:     Optional[str]               = None
    labId:           Union[int, LabIdField, None] = None
    redrawReason:    Optional[str]               = None     # reason for redraw (QC failure, etc)
    newCollectionTime: Optional[str]             = None     # timestamp of redraw collection
    expectedSLA:     Optional[str]               = None     # revised SLA deadline if provided
    isUrgent:        Optional[bool]              = False

    def get_lab_id(self) -> Optional[int]:
        if isinstance(self.labId, int):
            return self.labId
        if isinstance(self.labId, LabIdField):
            return self.labId.labId
        return None

    def get_event_key(self) -> Optional[int]:
        """Primary key for idempotency — bill_id preferred, sampleId fallback."""
        return self.bill_id or self.sampleId


# ── REPORT_SUBMIT / REPORT_SIGNED Payload ─────────────────────────────────────

class ReportLifecyclePayload(BaseModel):
    """Shared shape for REPORT_SUBMIT and REPORT_SIGNED."""
    webhookId:     Optional[int]               = None
    bill_id:       Optional[int]               = None
    billId:        Optional[int]               = None
    labId:         Union[int, LabIdField, None] = None
    labReportId:   Optional[int]               = None
    testID:        Optional[int]               = None
    testCode:      Optional[str]               = None
    sampleID:      Optional[str]               = None   # accession string
    reportDate:    Optional[str]               = None
    Report_Date:   Optional[str]               = None
    approvalDate:  Optional[str]               = None
    Approval_Date: Optional[str]               = None
    isSigned:      Optional[bool]              = False
    is_amended:    Optional[bool]              = False
    reportFormatAndValues: Optional[Any]        = None

    def get_lab_id(self) -> Optional[int]:
        if isinstance(self.labId, int):
            return self.labId
        if isinstance(self.labId, LabIdField):
            return self.labId.labId
        return None


# ── TEST_DISMISSED Payload ─────────────────────────────────────────────────────

class TestDismissedPayload(BaseModel):
    webhookId:     Optional[int] = None
    bill_id:       Optional[int] = None
    billId:        Optional[int] = None
    labReportId:   Optional[int] = None
    testID:        Optional[int] = None
    testCode:      Optional[str] = None
    dismissReason: Optional[str] = None


# ── REPORT_PDF Payload ────────────────────────────────────────────────────────

class ReportPdfPayload(BaseModel):
    webhookId:        Optional[int]  = None
    bill_id:          Optional[int]  = None
    billId:           Optional[int]  = None
    labId:            Union[int, LabIdField, None] = None
    labReportId:      Optional[int]  = None
    testID:           Optional[int]  = None
    testCode:         Optional[str]  = None
    testName:         Optional[str]  = None
    sampleID:         Optional[str]  = None          # accession string
    reportDate:       Optional[str]  = None
    approvalDate:     Optional[str]  = None
    accessionDate:    Optional[str]  = None
    isSigned:         Optional[bool] = False
    is_amended:       Optional[bool] = False
    reportBase64:     Optional[str]  = None          # stripped before storage

    def get_lab_id(self) -> Optional[int]:
        if isinstance(self.labId, int):
            return self.labId
        if isinstance(self.labId, LabIdField):
            return self.labId.labId
        return None


# ── Inbound Webhook Envelope ──────────────────────────────────────────────────

class WebhookInboundRequest(BaseModel):
    """Top-level envelope received at POST /api/webhook."""
    webhook_type: WebhookType
    payload:      Dict[str, Any]    # raw body, validated per type inside router


# ── Legacy / API models (kept for EDOS + accession routes) ───────────────────

class TestConfig(BaseModel):
    row_number:    int    = 0
    test_code:     str
    test_name:     str
    mrp:           float  = 0.0
    specimen_type: str    = ""
    method:        str    = ""
    schedule_raw:  str    = ""
    tat_raw:       str    = ""

class AccessionRequest(BaseModel):
    test_code:        str
    accession_time:   Optional[str] = None
    priority:         Priority      = Priority.NORMAL
    agreed_tat_hours: int           = 24
    sample_id:        Optional[str] = None

    @field_validator("test_code")
    @classmethod
    def upper_strip(cls, v: str) -> str:
        return v.strip().upper()


# ── Response schemas ──────────────────────────────────────────────────────────

class WebhookAcceptedResponse(BaseModel):
    status:    str = "accepted"
    event_id:  Optional[int]  = None
    duplicate: bool = False
    message:   Optional[str]  = None

class SampleDetailResponse(BaseModel):
    sample:        Dict[str, Any]
    tests:         List[Dict[str, Any]]
    queue_entry:   Optional[Dict[str, Any]] = None
    eta:           Optional[Dict[str, Any]] = None
    recent_logs:   List[Dict[str, Any]]     = []

class DashboardStats(BaseModel):
    total_samples:    int
    active_samples:   int
    completed_samples: int
    delayed_samples:  int
    cancelled_samples: int
    tat_breaches:     int
    active_bills:     int
    labs_available:   int


class LoginRequest(BaseModel):
    email:    str
    password: str
