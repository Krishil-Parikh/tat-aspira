"""
Central configuration — all env-overridable values in one place.
Usage:  from config.settings import cfg
"""
import os
from dataclasses import dataclass
from urllib.parse import urlparse
from dotenv import load_dotenv

from config.constants import (
    DEFAULT_AGREED_TAT_HOURS,
    BATCH_SCAN_HORIZON_DAYS,
    REDIS_RESULT_TTL_HOURS,
    DEFAULT_PG_POOL_MIN,
    DEFAULT_PG_POOL_MAX,
    DEFAULT_CELERY_CONCURRENCY,
)

load_dotenv()


@dataclass
class Settings:
    # ── PostgreSQL / Neon ────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    PG_DSN: str = os.getenv("PG_DSN", "")
    PG_POOL_MIN: int = int(os.getenv("PG_POOL_MIN", str(DEFAULT_PG_POOL_MIN)))
    PG_POOL_MAX: int = int(os.getenv("PG_POOL_MAX", str(DEFAULT_PG_POOL_MAX)))

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL:          str = os.getenv("REDIS_URL",   "redis://localhost:6379/0")
    REDIS_RESULT_TTL:   int = int(os.getenv("REDIS_TTL", str(REDIS_RESULT_TTL_HOURS * 3600)))   # 48 h
    CACHE_HOT_PIPELINE: str = "hot:pipeline"
    QUEUE_WEBHOOK:      str = "queue:webhook-processing"
    QUEUE_SAMPLE:       str = "queue:sample-processing"   # priority queue for sample jobs
    QUEUE_RESULT:       str = "queue:result-processing"   # priority queue for result/report jobs
    QUEUE_ALERT:        str = "queue:alert-processing"
    QUEUE_PROJECTION:   str = "queue:projection"

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_CONCURRENCY: int = int(os.getenv("CELERY_CONCURRENCY", str(DEFAULT_CELERY_CONCURRENCY)))

    # ── Timezone ──────────────────────────────────────────────────────────────
    ZONE: str = os.getenv("TZ", "Asia/Kolkata")

    # ── SMTP ─────────────────────────────────────────────────────────────────
    SMTP_HOST:        str = os.getenv("SMTP_HOST",  "")
    SMTP_PORT:        int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER:        str = os.getenv("SMTP_USER",  "")
    SMTP_PASS:        str = os.getenv("SMTP_PASS",  "")
    ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", "")
    ALERT_EMAIL_TO:   str = os.getenv("ALERT_EMAIL_TO",   "")

    # ── Webhooks ─────────────────────────────────────────────────────────────
    WEBHOOK_RESULTS_URL: str = os.getenv("WEBHOOK_RESULTS_URL", "")
    WEBHOOK_SHARED_SECRET: str = os.getenv("WEBHOOK_SHARED_SECRET", "")
    WEBHOOK_SIGNATURE_HEADER: str = os.getenv("WEBHOOK_SIGNATURE_HEADER", "X-Aspira-Signature")
    WEBHOOK_TIMESTAMP_HEADER: str = os.getenv("WEBHOOK_TIMESTAMP_HEADER", "X-Aspira-Timestamp")
    WEBHOOK_MAX_CLOCK_SKEW_SECONDS: int = int(os.getenv("WEBHOOK_MAX_CLOCK_SKEW_SECONDS", "300"))
    APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "development"))).lower()

    # ── Migration feature flags ──────────────────────────────────────────────
    MIGRATION_RECONCILIATION_ENABLED: bool = os.getenv("MIGRATION_RECONCILIATION_ENABLED", "false").lower() == "true"
    MIGRATION_RECONCILIATION_SWEEP_ENABLED: bool = os.getenv("MIGRATION_RECONCILIATION_SWEEP_ENABLED", "false").lower() == "true"
    MIGRATION_DUAL_WRITE_SLA_ETA: bool = os.getenv("MIGRATION_DUAL_WRITE_SLA_ETA", "false").lower() == "true"
    MIGRATION_DUAL_WRITE_QUEUE_ROUTING: bool = os.getenv("MIGRATION_DUAL_WRITE_QUEUE_ROUTING", "false").lower() == "true"
    MIGRATION_READ_NEW_DASHBOARD_MODEL: bool = os.getenv("MIGRATION_READ_NEW_DASHBOARD_MODEL", "false").lower() == "true"
    MIGRATION_READ_NEW_API_MODEL: bool = os.getenv("MIGRATION_READ_NEW_API_MODEL", "false").lower() == "true"
    MIGRATION_DISABLE_LEGACY_WRITES: bool = os.getenv("MIGRATION_DISABLE_LEGACY_WRITES", "false").lower() == "true"
    MIGRATION_ENABLE_CYCLE_LINEAGE: bool = os.getenv("MIGRATION_ENABLE_CYCLE_LINEAGE", "false").lower() == "true"

    # ── TAT defaults ──────────────────────────────────────────────────────────
    DEFAULT_AGREED_TAT_HOURS: int = DEFAULT_AGREED_TAT_HOURS
    BATCH_SCAN_HORIZON_DAYS:  int = BATCH_SCAN_HORIZON_DAYS
    DEFAULT_PROCESSING_TIME_MINS: int = int(os.getenv("DEFAULT_PROCESSING_TIME_MINS", "60"))
    ALLOW_DOCTOR_SAMPLE_CREATE: bool = os.getenv("ALLOW_DOCTOR_SAMPLE_CREATE", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "aspira-dev-secret-123")

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV in {"prod", "production"}


cfg = Settings()


if not cfg.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Set it to your Neon PostgreSQL connection string.")

if cfg.IS_PRODUCTION and not cfg.WEBHOOK_SHARED_SECRET:
    raise RuntimeError("WEBHOOK_SHARED_SECRET is required in production.")

# If PG_DSN is not set, derive a psycopg2 DSN from DATABASE_URL.
# This keeps one canonical source of truth while preserving existing sync code.
if not cfg.PG_DSN:
    parsed = urlparse(cfg.DATABASE_URL)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL.")
    if not parsed.hostname or not parsed.path:
        raise RuntimeError("DATABASE_URL is malformed.")
    parts = [
        f"host={parsed.hostname}",
        f"port={parsed.port or 5432}",
        f"dbname={parsed.path.lstrip('/')}",
    ]
    if parsed.username:
        parts.append(f"user={parsed.username}")
    if parsed.password:
        parts.append(f"password={parsed.password}")
    # Neon requires SSL for external connections.
    parts.append("sslmode=require")
    cfg.PG_DSN = " ".join(parts)
    DEFAULT_PROCESSING_TIME_MINS: int = int(os.getenv("DEFAULT_PROCESSING_TIME_MINS", "60"))
