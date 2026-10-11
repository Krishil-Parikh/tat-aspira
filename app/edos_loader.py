"""
EDOS loader — reads the Aspira Pathlab CSV, indexes records for O(1) lookup,
and optionally caches them in Redis hashes.

Priority order:
  1. In-memory map (fastest)
  2. Redis hash  (cross-process, survives worker restarts)
  3. CSV on disk
  4. JSON snapshot fallback
"""
from __future__ import annotations
import csv
import json
import logging
import os
from typing import Any, Dict, List, Optional

import redis as _redis

from config.settings import cfg
from app.schedule_parser import parse_schedule
from app.tat_parser import parse_tat

logger = logging.getLogger("edos_loader")

# ── File paths ────────────────────────────────────────────────────────────────
# __file__ is app/edos_loader.py → dirname → app/ → dirname → project root
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH  = os.path.join(_BASE, "edos.csv")
JSON_PATH = os.path.join(_BASE, "app", "data", "edos_snapshot.json")

# ── In-memory indexes ─────────────────────────────────────────────────────────
_by_name: Dict[str, Dict[str, Any]] = {}   # test_name.lower() → record
_by_code: Dict[str, Dict[str, Any]] = {}   # test_code.lower() → record
_records: List[Dict[str, Any]]      = []


# ── Redis keys ────────────────────────────────────────────────────────────────
_REDIS_KEY_NAME = "edos:by_name"
_REDIS_KEY_CODE = "edos:by_code"


def _build_record(row: Dict[str, str], line_num: int) -> Optional[Dict[str, Any]]:
    test_name = row.get("test name", "").strip()
    if not test_name:
        return None
    test_code    = row.get("test code", "").strip()
    schedule_raw = row.get("test schedule", "").strip()
    tat_raw      = row.get("tat", "").strip()

    try:
        mrp = float(row.get("mrp", "0").replace(",", ""))
    except ValueError:
        mrp = 0.0

    return {
        "row_num":       line_num,
        "state":         row.get("state", "").strip(),
        "city":          row.get("city", "").strip(),
        "test_code":     test_code,
        "test_name":     test_name,
        "mrp":           mrp,
        "group":         row.get("group", "").strip(),
        "specimen_type": row.get("specimen type", "").strip(),
        "method":        row.get("method", "").strip(),
        "temp":          row.get("temp", "").strip(),
        "schedule_raw":  schedule_raw,
        "tat_raw":       tat_raw,
    }


def _index(records: List[Dict[str, Any]]) -> None:
    global _by_name, _by_code
    for rec in records:
        if rec.get("test_name"):
            _by_name[rec["test_name"].lower()] = rec
        if rec.get("test_code"):
            _by_code[rec["test_code"].lower()] = rec
    logger.info("EDOS indexed: %d by name, %d by code", len(_by_name), len(_by_code))


def _load_csv() -> List[Dict[str, Any]]:
    if not os.path.exists(CSV_PATH):
        return []
    records: List[Dict[str, Any]] = []
    try:
        with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
            # First line is a title row — skip it
            f.readline()
            reader = csv.DictReader(f)
            # Normalise header keys
            reader.fieldnames = [
                h.strip().lower() for h in (reader.fieldnames or [])
            ]
            for i, row in enumerate(reader, start=2):
                clean = {k.strip().lower(): v.strip() for k, v in row.items()}
                rec = _build_record(clean, i)
                if rec:
                    records.append(rec)

        logger.info("EDOS CSV loaded: %d records", len(records))

        # Save JSON snapshot for debugging / fallback
        os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
        with open(JSON_PATH, "w") as jf:
            json.dump(records, jf, indent=2)

    except Exception as exc:
        logger.error("CSV load failed: %s", exc)

    return records


def _load_json_fallback() -> List[Dict[str, Any]]:
    if not os.path.exists(JSON_PATH):
        return []
    try:
        with open(JSON_PATH, "r") as jf:
            records = json.load(jf)
        logger.info("EDOS JSON fallback loaded: %d records", len(records))
        return records
    except Exception as exc:
        logger.error("JSON fallback failed: %s", exc)
        return []


def _cache_redis(r: _redis.Redis, records: List[Dict[str, Any]]) -> None:
    try:
        pipe = r.pipeline()
        for rec in records:
            js = json.dumps(rec)
            if rec.get("test_name"):
                pipe.hset(_REDIS_KEY_NAME, rec["test_name"].lower(), js)
            if rec.get("test_code"):
                pipe.hset(_REDIS_KEY_CODE, rec["test_code"].lower(), js)
        pipe.execute()
        logger.info("EDOS cached in Redis (%d records)", len(records))
    except Exception as exc:
        logger.warning("Redis EDOS cache failed: %s", exc)


def load_edos(r_client: Optional[_redis.Redis] = None) -> List[Dict[str, Any]]:
    """Load EDOS data (CSV → JSON fallback), index in memory, optionally cache in Redis."""
    global _records
    records = _load_csv() or _load_json_fallback()
    _records = records
    _index(records)
    if r_client and records:
        _cache_redis(r_client, records)
    return records


def lookup_test(
    test_name: Optional[str] = None,
    test_code: Optional[str] = None,
    r_client:  Optional[_redis.Redis] = None,
) -> Optional[Dict[str, Any]]:
    """
    O(1) lookup by name or code.

    Falls back to Redis if in-memory maps are empty (e.g. freshly spawned worker).
    """
    # 1. In-memory
    if test_name:
        rec = _by_name.get(test_name.lower())
        if rec:
            return rec
    if test_code:
        rec = _by_code.get(test_code.lower())
        if rec:
            return rec

    # 2. Redis
    if r_client:
        try:
            raw = None
            if test_name:
                raw = r_client.hget(_REDIS_KEY_NAME, test_name.lower())
            if raw is None and test_code:
                raw = r_client.hget(_REDIS_KEY_CODE, test_code.lower())
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    return None


def get_all_records() -> List[Dict[str, Any]]:
    return _records


def search_records(query: str) -> List[Dict[str, Any]]:
    q = query.lower()
    return [
        r for r in _records
        if q in r.get("test_name", "").lower() or q in r.get("test_code", "").lower()
    ]
