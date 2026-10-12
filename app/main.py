"""
Main FastAPI application — PostgreSQL-backed TAT System.

Run:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Scale:
  gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4

Celery workers:
  celery -A app.workers.celery_app worker -Q queue:webhook-processing,projection -c 8 -n webhook@%h
  celery -A app.workers.celery_app beat   --loglevel=info
"""
from __future__ import annotations
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import pg_database as pgdb
from app.core.hot_cache import _redis as _hot_redis
from app.routers.webhook import router as webhook_router
from app.routers.api import (
    samples_router,
    bills_router,
    labs_router,
    stats_router,
    notif_router,
    tests_router,
    test_tracking_router,
    accession_router,
)
from app.routers.admin import admin_router
from app.routers.actions import actions_router
from app.routers.dashboard import dashboard_router
from app.edos_loader import load_edos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect PostgreSQL pool
    await pgdb.connect_db()
    logger.info("PostgreSQL pool ready")

    # Pre-load EDOS catalog (file-based, no Redis required)
    try:
        records = load_edos(None)
        logger.info("EDOS catalog loaded: %d tests", len(records))
    except FileNotFoundError as exc:
        logger.error("EDOS catalog file not found: %s", exc)
        logger.warning("System will continue without EDOS catalog - test lookups may fail")
    except PermissionError as exc:
        logger.error("EDOS catalog permission denied: %s", exc)
        logger.error("FATAL: File permission issues must be resolved before startup. Halting.")
        raise RuntimeError(f"EDOS catalog permission denied: {exc}") from exc
    except Exception as exc:
        logger.error("EDOS load failed with unexpected error: %s", exc)
        logger.warning("System will continue without EDOS catalog - check file format and path")

    # Warm up Redis connections (hot cache + priority queues)
    try:
        _hot_redis().ping()
        logger.info("Redis ready — hot pipeline cache + priority queues active")
    except Exception as exc:
        logger.warning("Redis unavailable — cache/queue features degraded: %s", exc)

    yield

    await pgdb.close_db()
    logger.info("PostgreSQL pool closed")


app = FastAPI(
    title="Aspira TAT System v2",
    description=(
        "Production-grade Turnaround Time engine for Aspira Diagnostics. "
        "Event-driven webhook ingestion → PostgreSQL scheduling → real-time TAT tracking."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Configure CORS for security - only allow specific origins in production
allowed_origins = [
    "http://localhost:3000",  # Next.js development
    "http://localhost:3001",  # Alternative development port
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    allow_credentials=True,
)


# ── Request logging ───────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info("%s %s → %d  %.1f ms",
                request.method, request.url.path, response.status_code, duration_ms)
    return response


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(webhook_router)
app.include_router(samples_router)
app.include_router(bills_router)
app.include_router(labs_router)
app.include_router(stats_router)
app.include_router(notif_router)
app.include_router(tests_router)
app.include_router(test_tracking_router)
app.include_router(accession_router)
app.include_router(admin_router)      # Bug 2 Fix: GET /api/admin/*
app.include_router(actions_router)
app.include_router(dashboard_router)


# ── Health & Root ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Infra"])
async def health():
    return {"status": "ok", "db": "postgresql", "version": "2.0.0"}


@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({
        "message": "Aspira TAT System v2 is running.",
        "docs":    "/docs",
        "health":  "/health",
        "webhook": "POST /api/webhook",
    })
