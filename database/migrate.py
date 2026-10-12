"""
database/migrate.py — Reset and recreate the Aspira PostgreSQL schema.

Usage:
    python database/migrate.py

Reads database/schema.sql and executes it against the configured PostgreSQL DB.
For Neon: skips database creation and uses asyncpg for better performance.
For local PostgreSQL: creates database if missing.
Safe to re-run (drops and recreates the public schema).
"""
from __future__ import annotations
import os
import sys
import logging
import asyncio
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Try to import asyncpg for Neon support
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate")

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
PG_HOST     = os.getenv("PG_HOST",     "localhost")
PG_PORT     = int(os.getenv("PG_PORT", "5432"))
PG_USER     = os.getenv("PG_USER",     "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "secret")
PG_DBNAME   = os.getenv("PG_DBNAME",   "tat_db")

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")

def _is_neon_database():
    """Check if DATABASE_URL is a Neon database"""
    return "neon.tech" in DATABASE_URL


async def _run_neon_migration() -> None:
    """Run migration for Neon database using asyncpg."""
    if not HAS_ASYNCPG:
        logger.error("asyncpg is required for Neon database support. Install with: pip install asyncpg")
        sys.exit(1)
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    logger.info("=== Neon Database Migration ===")
    logger.info("Connecting to Neon database...")
    
    if not os.path.exists(SCHEMA_FILE):
        logger.error("Schema file not found at: %s", SCHEMA_FILE)
        sys.exit(1)

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        logger.info("Running schema migration...")

        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")

        await conn.execute(schema_sql)
        logger.info("✅ Schema applied successfully to Neon database!")
        
        # Verify tables were created
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        logger.info(f"Created {len(tables)} tables: {[t['table_name'] for t in tables]}")
        
    finally:
        await conn.close()


def _ensure_db_exists() -> None:
    """Connect to 'postgres' default DB and create tat_db if missing."""
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname="postgres"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_DBNAME,))
    if not cur.fetchone():
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(PG_DBNAME)))
        logger.info("Created database: %s", PG_DBNAME)
    else:
        logger.info("Database already exists: %s", PG_DBNAME)
    cur.close()
    conn.close()


def _run_schema() -> None:
    """Execute schema.sql against the target database."""
    if not os.path.exists(SCHEMA_FILE):
        logger.error("schema.sql not found at: %s", SCHEMA_FILE)
        sys.exit(1)

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DBNAME
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
    cur.execute("CREATE SCHEMA public")

    cur.execute(schema_sql)
    logger.info("Schema applied successfully to database: %s", PG_DBNAME)

    cur.close()
    conn.close()


if __name__ == "__main__":
    if _is_neon_database():
        # Use Neon migration
        try:
            asyncio.run(_run_neon_migration())
            logger.info("=== Neon Migration complete ===")
            logger.info("Schema reset from the single source file: database/schema.sql")
            logger.info("Core tables include webhook, reconciliation, lab, bill, sample, test, queue, ETA, SLA, and log entities")
        except Exception as e:
            logger.error(f"❌ Neon migration failed: {e}")
            sys.exit(1)
    else:
        # Use local PostgreSQL migration
        logger.info("=== TAT Database Migration ===")
        logger.info("Target: %s@%s:%s/%s", PG_USER, PG_HOST, PG_PORT, PG_DBNAME)

        _ensure_db_exists()
        _run_schema()

        logger.info("=== Migration complete ===")
        logger.info("Schema reset from the single source file: database/schema.sql")
        logger.info("Core tables include webhook, reconciliation, lab, bill, sample, test, queue, ETA, SLA, and log entities")
