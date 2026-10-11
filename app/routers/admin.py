"""
app/routers/admin.py — Admin-only endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app import pg_database as pgdb
from app.core.auth import get_current_user, require_role, UserSession
from app.pg_database import _pool

# Create admin router
admin_router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user), Depends(require_role(["admin", "super_admin"]))]
)

@admin_router.get("/health")
async def admin_health():
    """Admin health check endpoint."""
    return {"status": "ok", "admin": "active"}

@admin_router.get("/stats")
async def admin_stats():
    """Admin statistics endpoint."""
    stats = await pgdb.get_admin_dashboard()
    return stats


# ── Pydantic Request Models ──

class CapabilityCreate(BaseModel):
    lab_id: int
    department_id: int
    department_name: str
    test_code: Optional[str] = None

class RoutingCreate(BaseModel):
    test_code: Optional[str] = None
    department_id: Optional[int] = None
    processing_lab_id: int
    notes: Optional[str] = None


class LabAvailabilityUpdate(BaseModel):
    is_active: bool
    reason: str

class EdosCreate(BaseModel):
    lab_id: int
    test_code: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    processing_time_mins: int
    committed_tat_hours: Optional[float] = None
    processing_mode: str = "max"
    is_outsourced: int = 0
    outsource_vendor_name: Optional[str] = None
    outsource_buffer_mins: Optional[int] = None
    notes: Optional[str] = None


@admin_router.post("/labs/{lab_id}/availability")
async def update_lab_availability(lab_id: int, req: LabAvailabilityUpdate, user: UserSession = Depends(require_role(["admin", "super_admin"]))):
    lab = await _pool.fetchrow("SELECT id, lab_name FROM tat_lab WHERE id = $1", lab_id)
    if not lab:
        raise HTTPException(404, f"Lab {lab_id} not found")

    availability = 1 if req.is_active else 0
    await _pool.execute(
        """
        UPDATE tat_lab
        SET is_active = $1,
            is_available = $1,
            unavailability_reason = CASE WHEN $1 = 1 THEN NULL ELSE $2 END,
            unavailable_until = CASE WHEN $1 = 1 THEN NULL ELSE unavailable_until END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $3
        """,
        availability,
        req.reason,
        lab_id,
    )
    await _pool.execute(
        """
        INSERT INTO tat_log (lab_id, event_type, triggered_by, notes, event_timestamp)
        VALUES ($1, 'lab_availability_changed', $2, $3, CURRENT_TIMESTAMP)
        """,
        lab_id,
        user.email,
        f"Lab set to {'ACTIVE' if req.is_active else 'DOWN'}: {req.reason}",
    )
    return {
        "success": True,
        "lab_id": lab_id,
        "lab_name": lab["lab_name"],
        "is_active": availability,
    }


# ── Lab Capabilities CRUD ──

@admin_router.get("/capabilities")
async def list_capabilities():
    """List all registered lab capabilities."""
    rows = await _pool.fetch("SELECT * FROM tat_lab_capability ORDER BY id ASC")
    return {"capabilities": [dict(r) for r in rows]}

@admin_router.post("/capabilities")
async def create_capability(req: CapabilityCreate):
    """Add a new diagnostic department capability to a lab."""
    try:
        val = await _pool.fetchval(
            """INSERT INTO tat_lab_capability (lab_id, department_id, department_name, test_code)
               VALUES ($1, $2, $3, $4)
               RETURNING id""",
            req.lab_id, req.department_id, req.department_name, req.test_code
        )
        return {"status": "success", "id": val}
    except Exception as e:
        raise HTTPException(400, f"Database error: {e}")

@admin_router.delete("/capabilities/{id}")
async def delete_capability(id: int):
    """Remove a lab capability."""
    res = await _pool.execute("DELETE FROM tat_lab_capability WHERE id = $1", id)
    return {"status": "success", "message": res}


# ── Test Routing Rules CRUD ──

@admin_router.get("/routing")
async def list_routing():
    """List all global test routing rules."""
    rows = await _pool.fetch("SELECT * FROM tat_test_routing ORDER BY id ASC")
    return {"routing_rules": [dict(r) for r in rows]}

@admin_router.post("/routing")
async def create_routing_rule(req: RoutingCreate):
    """Create or update a global test routing rule."""
    try:
        val = await _pool.fetchval(
            """INSERT INTO tat_test_routing (test_code, department_id, processing_lab_id, notes)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (test_code, department_id) DO UPDATE
               SET processing_lab_id = EXCLUDED.processing_lab_id,
                   notes = EXCLUDED.notes,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING id""",
            req.test_code, req.department_id, req.processing_lab_id, req.notes
        )
        return {"status": "success", "id": val}
    except Exception as e:
        raise HTTPException(400, f"Database error: {e}")

@admin_router.delete("/routing/{id}")
async def delete_routing_rule(id: int):
    """Delete a test routing rule."""
    res = await _pool.execute("DELETE FROM tat_test_routing WHERE id = $1", id)
    return {"status": "success", "message": res}


# ── Lab EDOS Configs CRUD ──

@admin_router.get("/edos")
async def list_edos_configs():
    """List all per-lab EDOS test configurations."""
    rows = await _pool.fetch("SELECT * FROM tat_lab_edos ORDER BY id ASC")
    return {"edos_configs": [dict(r) for r in rows]}

@admin_router.post("/edos")
async def create_edos_config(req: EdosCreate):
    """Create or update a lab-specific EDOS configuration for a test."""
    try:
        val = await _pool.fetchval(
            """INSERT INTO tat_lab_edos 
               (lab_id, test_code, department_id, department_name, processing_time_mins, 
                committed_tat_hours, processing_mode, is_outsourced, outsource_vendor_name, 
                outsource_buffer_mins, notes)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
               ON CONFLICT (lab_id, test_code) DO UPDATE
               SET department_id = EXCLUDED.department_id,
                   department_name = EXCLUDED.department_name,
                   processing_time_mins = EXCLUDED.processing_time_mins,
                   committed_tat_hours = EXCLUDED.committed_tat_hours,
                   processing_mode = EXCLUDED.processing_mode,
                   is_outsourced = EXCLUDED.is_outsourced,
                   outsource_vendor_name = EXCLUDED.outsource_vendor_name,
                   outsource_buffer_mins = EXCLUDED.outsource_buffer_mins,
                   notes = EXCLUDED.notes,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING id""",
            req.lab_id, req.test_code, req.department_id, req.department_name, req.processing_time_mins,
            req.committed_tat_hours, req.processing_mode, req.is_outsourced, req.outsource_vendor_name,
            req.outsource_buffer_mins, req.notes
        )
        return {"status": "success", "id": val}
    except Exception as e:
        raise HTTPException(400, f"Database error: {e}")

@admin_router.delete("/edos/{id}")
async def delete_edos_config(id: int):
    """Remove a lab-specific EDOS configuration."""
    res = await _pool.execute("DELETE FROM tat_lab_edos WHERE id = $1", id)
    return {"status": "success", "message": res}


# Export router
router = admin_router

