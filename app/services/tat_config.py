"""
Predefined TAT lookup — single source of truth for committed TAT per test.

Values live in tat_predefined_tat (one row per test_code × client category) and
are edited from Admin > TAT Configuration. Every read goes to the database, so an
edit applies to every SLA / ETA computed after it is saved.

A sample's category comes from its bill's org (tat_org.sla_tier). Walk-in bills,
orgs without a tier, and tests missing a row for the org's category fall back to
the B2B row.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger("tat_config")

CATEGORIES = ("B2B", "PRIORITY", "HLM", "CAMP")
DEFAULT_CATEGORY = "B2B"


def normalize_category(value: Optional[str]) -> str:
    v = (value or "").strip().upper()
    return v if v in CATEGORIES else DEFAULT_CATEGORY


def resolve_client_category(cur, bill_id: Optional[int]) -> str:
    """TAT category for a bill, from its org's sla_tier."""
    if not bill_id:
        return DEFAULT_CATEGORY
    cur.execute("""
        SELECT o.sla_tier
        FROM tat_bill b
        LEFT JOIN tat_org o ON o.id = b.org_internal_id
        WHERE b.id = %s
    """, (bill_id,))
    row = cur.fetchone()
    return normalize_category(row["sla_tier"] if row else None)


def get_predefined_tat_mins(cur, test_code: Optional[str], category: str = DEFAULT_CATEGORY) -> Optional[int]:
    """Overall predefined TAT (minutes) for one test, or None if not configured."""
    if not test_code:
        return None
    category = normalize_category(category)
    cur.execute("""
        SELECT overall_tat_mins
        FROM tat_predefined_tat
        WHERE test_code = %s AND is_active = 1 AND client_category IN (%s, %s)
        ORDER BY (client_category = %s) DESC
        LIMIT 1
    """, (test_code.strip().upper(), category, DEFAULT_CATEGORY, category))
    row = cur.fetchone()
    return row["overall_tat_mins"] if row else None


def get_max_predefined_tat_mins(cur, test_codes: Iterable[Optional[str]], category: str = DEFAULT_CATEGORY) -> Optional[int]:
    """Largest predefined TAT among the given tests (sample-level commitment)."""
    values = [get_predefined_tat_mins(cur, code, category) for code in {c for c in test_codes if c}]
    values = [v for v in values if v]
    return max(values) if values else None
