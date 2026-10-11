"""
Application constants - centralized configuration values.
All magic numbers and hardcoded values should be defined here.
"""

# ── TAT Configuration ──────────────────────────────────────────────────────────
DEFAULT_AGREED_TAT_HOURS = 24
BATCH_SCAN_HORIZON_DAYS = 35

# ── Cache TTL Settings ────────────────────────────────────────────────────────
REDIS_RESULT_TTL_HOURS = 48  # 48 hours in seconds = 172800

# ── Cookie Settings ────────────────────────────────────────────────────────────
COOKIE_MAX_AGE_SECONDS = 300  # 5 minutes

# ── Database Pool Settings ────────────────────────────────────────────────────
# Tuned for 100+ samples/sec throughput (45 queries/sample = 4500 q/sec needed)
# With ~50 q/sec per connection: need 100 connections
DEFAULT_PG_POOL_MIN = 20
DEFAULT_PG_POOL_MAX = 100

# ── Celery Configuration ───────────────────────────────────────────────────────
DEFAULT_CELERY_CONCURRENCY = 8

# ── Webhook Processing ─────────────────────────────────────────────────────────
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 10

# ── Scheduled Jobs ────────────────────────────────────────────────────────────
SWEEP_DELAYED_INTERVAL_MINUTES = 5
PROJECTION_REFRESH_INTERVAL_MINUTES = 10

# ── HTTP Configuration ────────────────────────────────────────────────────────
DEFAULT_HTTP_TIMEOUT_SECONDS = 30

# ── Logging Configuration ───────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
