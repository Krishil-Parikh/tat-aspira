"""FastAPI main application for the TAT & Batch Monitoring System."""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

from app import database as db
from app.csv_loader import get_all_tests, get_test_by_code, search_tests
from app.engine import accession_sample, simulate_missed_batch
from app.models import AccessionRequest
from app.schedule_parser import parse_schedule, find_next_batch
from app.tat_parser import parse_tat, calculate_eta


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await db.connect_db()
    # Pre-load test data
    tests = get_all_tests()
    print(f"📋 Loaded {len(tests)} test configurations from CSV")
    yield
    await db.close_db()


app = FastAPI(
    title="TAT & Batch Monitoring System",
    description="Automated TAT and Batch Monitoring for Laboratory Tests",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- Helper to serialize datetimes for JSON ---
def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    result = {}
    for key, value in doc.items():
        if key == "_id":
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# =============================================
# Frontend
# =============================================

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the main dashboard HTML."""
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return JSONResponse({"message": "Frontend not found. API is running at /docs"})


# =============================================
# Test Configuration Endpoints
# =============================================

@app.get("/api/tests")
async def list_tests(
    q: Optional[str] = Query(None, description="Search query for test name or code"),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
):
    """List or search all available tests."""
    if q:
        results = search_tests(q)
    else:
        results = get_all_tests()

    total = len(results)
    start = (page - 1) * limit
    end = start + limit
    page_results = results[start:end]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "tests": [t.model_dump() for t in page_results],
    }


@app.get("/api/tests/{test_code}")
async def get_test(test_code: str):
    """Get details for a specific test including parsed schedule info."""
    test = get_test_by_code(test_code)
    if not test:
        raise HTTPException(status_code=404, detail=f"Test '{test_code}' not found")

    # Parse schedule for display
    slots = parse_schedule(test.test_schedule)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    schedule_info = []
    for slot in slots:
        info = f"{day_names[slot.day_of_week]} {slot.hour:02d}:{slot.minute:02d}"
        if slot.week_numbers:
            weeks = ", ".join([f"Week {w}" for w in slot.week_numbers])
            info += f" ({weeks})"
        schedule_info.append(info)

    # Parse TAT
    tat_parsed = parse_tat(test.tat)

    # Calculate next batch from now
    now = datetime.now()
    next_batch = find_next_batch(now, test.test_schedule)
    eta = calculate_eta(next_batch, test.tat) if next_batch else None

    return {
        "test": test.model_dump(),
        "schedule_parsed": schedule_info,
        "tat_parsed": {
            "days": tat_parsed[0] if tat_parsed else None,
            "hour": tat_parsed[1] if tat_parsed else None,
            "minute": tat_parsed[2] if tat_parsed else None,
        },
        "next_batch_from_now": next_batch.isoformat() if next_batch else None,
        "eta_from_now": eta.isoformat() if eta else None,
    }


# =============================================
# Sample Accession Endpoints
# =============================================

@app.post("/api/accession")
async def create_accession(req: AccessionRequest):
    """Register a new sample and calculate batch assignment + ETA."""
    accession_time = None
    if req.accession_time:
        try:
            accession_time = datetime.fromisoformat(req.accession_time)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid datetime format: '{req.accession_time}'. Use ISO format."
            )

    try:
        sample = await accession_sample(req.test_code, accession_time)
        return {
            "success": True,
            "message": f"Sample {sample['sample_id']} accessioned successfully",
            "sample": serialize_doc(sample),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================
# Sample Tracking Endpoints
# =============================================

@app.get("/api/samples")
async def list_samples(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List all tracked samples."""
    if status:
        samples = await db.get_samples_by_status(status)
    else:
        samples = await db.get_all_samples(limit)

    return {
        "total": len(samples),
        "samples": [serialize_doc(s) for s in samples],
    }


@app.get("/api/samples/{sample_id}")
async def get_sample_detail(sample_id: str):
    """Get detailed information for a specific sample."""
    sample = await db.get_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")

    return serialize_doc(sample)


@app.post("/api/samples/{sample_id}/miss-batch")
async def miss_batch(sample_id: str):
    """Simulate a missed batch for a sample."""
    try:
        updated_sample, notification = await simulate_missed_batch(sample_id)
        return {
            "success": True,
            "message": notification["message"],
            "sample": serialize_doc(updated_sample),
            "notification": serialize_doc(notification),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/samples/{sample_id}")
async def delete_sample(sample_id: str):
    """Delete a sample."""
    deleted = await db.delete_sample(sample_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return {"success": True, "message": f"Sample {sample_id} deleted"}


# =============================================
# Notification Endpoints
# =============================================

@app.get("/api/notifications")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """Get notifications."""
    if unread_only:
        notifications = await db.get_unread_notifications()
    else:
        notifications = await db.get_notifications(limit)

    return {
        "total": len(notifications),
        "unread_count": await db.get_notification_count(),
        "notifications": [serialize_doc(n) for n in notifications],
    }


@app.post("/api/notifications/{notification_id}/read")
async def read_notification(notification_id: str):
    """Mark a notification as read."""
    marked = await db.mark_notification_read(notification_id)
    if not marked:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


# =============================================
# Dashboard Stats
# =============================================

@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics."""
    all_samples = await db.get_all_samples(1000)
    
    total = len(all_samples)
    active = sum(1 for s in all_samples if s.get("status") in ["batch_assigned", "processing"])
    missed = sum(1 for s in all_samples if s.get("status") == "missed_batch")
    completed = sum(1 for s in all_samples if s.get("status") == "completed")
    unread_notifs = await db.get_notification_count()

    return {
        "total_samples": total,
        "active_samples": active,
        "missed_batches": missed,
        "completed": completed,
        "unread_notifications": unread_notifs,
        "total_tests_in_catalog": len(get_all_tests()),
    }


# =============================================
# Utility
# =============================================

@app.post("/api/clear", include_in_schema=False)
async def clear_data():
    """Clear all samples and notifications (dev only)."""
    await db.clear_all_data()
    return {"success": True, "message": "All data cleared"}
