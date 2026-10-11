"""
app/routers/tat_config.py — Predefined TAT per test (replaces the Excel sheet).

GET    /api/admin/tat-config               list / search entries (+ counts per category)
POST   /api/admin/tat-config               add an entry
PUT    /api/admin/tat-config/{id}          edit an entry
DELETE /api/admin/tat-config/{id}          remove an entry
GET    /api/admin/tat-config/orgs          client orgs with their TAT category
PUT    /api/admin/tat-config/orgs/{id}     set an org's TAT category

The webhook worker reads tat_predefined_tat on every SLA/ETA calculation
(app/services/tat_config.py), so saved edits apply immediately to new work.
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import pg_database as pgdb
from app.core.auth import UserSession, require_role
from app.services.tat_config import CATEGORIES

logger = logging.getLogger("routers.tat_config")

tat_config_router = APIRouter(prefix="/api/admin/tat-config", tags=["TAT Configuration"])

_COLUMNS = """id, test_code, test_name, client_category, accession_mins, validation_mins,
              approval_mins, submission_mins, overall_tat_mins, is_active, updated_by,
              created_at, updated_at"""


class TatEntryCreate(BaseModel):
    test_code:        str           = Field(min_length=1, max_length=32)
    test_name:        Optional[str] = Field(default=None, max_length=1000)
    client_category:  str           = "B2B"
    accession_mins:   Optional[int] = Field(default=None, ge=0)
    validation_mins:  Optional[int] = Field(default=None, ge=0)
    approval_mins:    Optional[int] = Field(default=None, ge=0)
    submission_mins:  Optional[int] = Field(default=None, ge=0)
    overall_tat_mins: int           = Field(gt=0)
    is_active:        int           = Field(default=1, ge=0, le=1)


class TatEntryUpdate(BaseModel):
    test_name:        Optional[str] = Field(default=None, max_length=1000)
    accession_mins:   Optional[int] = Field(default=None, ge=0)
    validation_mins:  Optional[int] = Field(default=None, ge=0)
    approval_mins:    Optional[int] = Field(default=None, ge=0)
    submission_mins:  Optional[int] = Field(default=None, ge=0)
    overall_tat_mins: int           = Field(gt=0)
    is_active:        int           = Field(default=1, ge=0, le=1)


class OrgCategoryUpdate(BaseModel):
    client_category: str


def _category(value: str) -> str:
    v = (value or "").strip().upper()
    if v not in CATEGORIES:
        raise HTTPException(422, f"client_category must be one of {', '.join(CATEGORIES)}")
    return v


@tat_config_router.get("")
async def list_tat_entries(
    category: Optional[str] = Query(None, description="B2B | PRIORITY | HLM | CAMP"),
    q:        Optional[str] = Query(None, description="Search test code or name"),
    limit:    int           = Query(50, ge=1, le=500),
    offset:   int           = Query(0, ge=0),
    user: UserSession = Depends(require_role(["admin"])),
):
    where, args = [], []
    if category:
        args.append(_category(category))
        where.append(f"client_category = ${len(args)}")
    if q and q.strip():
        args.append(f"%{q.strip()}%")
        where.append(f"(test_code ILIKE ${len(args)} OR test_name ILIKE ${len(args)})")
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = await pgdb._pool.fetchval(f"SELECT COUNT(*) FROM tat_predefined_tat {clause}", *args)
    rows = await pgdb._pool.fetch(
        f"""SELECT {_COLUMNS} FROM tat_predefined_tat {clause}
            ORDER BY test_code, client_category
            LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}""",
        *args, limit, offset,
    )
    counts = await pgdb._pool.fetch(
        "SELECT client_category, COUNT(*) AS n FROM tat_predefined_tat GROUP BY client_category"
    )
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": {c: 0 for c in CATEGORIES} | {r["client_category"]: r["n"] for r in counts},
    }


@tat_config_router.post("", status_code=201)
async def create_tat_entry(req: TatEntryCreate, user: UserSession = Depends(require_role(["admin"]))):
    try:
        row = await pgdb._pool.fetchrow(
            f"""INSERT INTO tat_predefined_tat
                  (test_code, test_name, client_category, accession_mins, validation_mins,
                   approval_mins, submission_mins, overall_tat_mins, is_active, updated_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING {_COLUMNS}""",
            req.test_code.strip().upper(), (req.test_name or "").strip() or None, _category(req.client_category),
            req.accession_mins, req.validation_mins, req.approval_mins, req.submission_mins,
            req.overall_tat_mins, req.is_active, user.email,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"{req.test_code.upper()} already has a {req.client_category.upper()} TAT entry")
    logger.info("[TAT_CONFIG] created %s/%s overall=%d by=%s",
                row["test_code"], row["client_category"], row["overall_tat_mins"], user.email)
    return dict(row)


@tat_config_router.put("/{entry_id}")
async def update_tat_entry(entry_id: int, req: TatEntryUpdate, user: UserSession = Depends(require_role(["admin"]))):
    row = await pgdb._pool.fetchrow(
        f"""UPDATE tat_predefined_tat
            SET test_name=$1, accession_mins=$2, validation_mins=$3, approval_mins=$4,
                submission_mins=$5, overall_tat_mins=$6, is_active=$7, updated_by=$8
            WHERE id=$9
            RETURNING {_COLUMNS}""",
        (req.test_name or "").strip() or None, req.accession_mins, req.validation_mins,
        req.approval_mins, req.submission_mins, req.overall_tat_mins, req.is_active,
        user.email, entry_id,
    )
    if not row:
        raise HTTPException(404, f"TAT entry {entry_id} not found")
    logger.info("[TAT_CONFIG] updated %s/%s overall=%d active=%d by=%s",
                row["test_code"], row["client_category"], row["overall_tat_mins"], row["is_active"], user.email)
    return dict(row)


@tat_config_router.delete("/{entry_id}")
async def delete_tat_entry(entry_id: int, user: UserSession = Depends(require_role(["admin"]))):
    row = await pgdb._pool.fetchrow(
        "DELETE FROM tat_predefined_tat WHERE id=$1 RETURNING test_code, client_category", entry_id
    )
    if not row:
        raise HTTPException(404, f"TAT entry {entry_id} not found")
    logger.info("[TAT_CONFIG] deleted %s/%s by=%s", row["test_code"], row["client_category"], user.email)
    return {"success": True, "id": entry_id}


@tat_config_router.get("/orgs")
async def list_org_categories(user: UserSession = Depends(require_role(["admin"]))):
    rows = await pgdb._pool.fetch(
        "SELECT id, external_org_id, org_name, sla_tier FROM tat_org WHERE is_active=1 ORDER BY org_name"
    )
    return {"orgs": [dict(r) for r in rows], "categories": list(CATEGORIES)}


@tat_config_router.put("/orgs/{org_id}")
async def set_org_category(org_id: int, req: OrgCategoryUpdate, user: UserSession = Depends(require_role(["admin"]))):
    row = await pgdb._pool.fetchrow(
        "UPDATE tat_org SET sla_tier=$1 WHERE id=$2 RETURNING id, external_org_id, org_name, sla_tier",
        _category(req.client_category), org_id,
    )
    if not row:
        raise HTTPException(404, f"Org {org_id} not found")
    logger.info("[TAT_CONFIG] org %s category=%s by=%s", row["org_name"], row["sla_tier"], user.email)
    return dict(row)
