"""
app/routers/sample_create.py — Sample creation endpoints.
"""

from fastapi import APIRouter
from typing import Dict, Any

# Create sample creation router
sample_create_router = APIRouter(prefix="/api/sample-create", tags=["Sample Create"])

@sample_create_router.get("/health")
async def sample_create_health():
    """Sample creation health check endpoint."""
    return {"status": "ok", "sample_create": "active"}

@sample_create_router.post("/")
async def create_sample():
    """Create sample endpoint - to be implemented."""
    return {"message": "Sample creation endpoint - to be implemented"}

# Export router
router = sample_create_router