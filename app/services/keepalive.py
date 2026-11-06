"""
app/services/keepalive.py — keeps a free-tier host (Render) awake during working hours.

Render's free web services sleep after 15 minutes without inbound traffic. While the
window is open (default 08:00–20:00 Asia/Kolkata), a background loop in the API calls
GET {KEEPALIVE_URL}/api/keepalive every KEEPALIVE_INTERVAL_MINS minutes; that endpoint
pings GET {KEEPALIVE_URL}/health. Both go through the public URL, so they count as
inbound traffic. Outside the window nothing is sent and the service may sleep; the first
request after that wakes it, and the loop keeps it awake again from the next window.

Disabled unless KEEPALIVE_URL (or Render's RENDER_EXTERNAL_URL) is set.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx

from config.settings import cfg

logger = logging.getLogger("services.keepalive")

_TIMEOUT = httpx.Timeout(30.0)


def _tz() -> ZoneInfo:
    return ZoneInfo(cfg.KEEPALIVE_TIMEZONE)


def in_window(now: Optional[datetime] = None) -> bool:
    """True between KEEPALIVE_START_HOUR:00 (inclusive) and KEEPALIVE_END_HOUR:00 (exclusive),
    local time in KEEPALIVE_TIMEZONE."""
    local = (now or datetime.now(_tz())).astimezone(_tz())
    return cfg.KEEPALIVE_START_HOUR <= local.hour < cfg.KEEPALIVE_END_HOUR


def _base_url() -> str:
    return cfg.KEEPALIVE_URL.rstrip("/")


async def ping_health() -> Dict[str, Any]:
    """One GET of the backend's own /health through its public URL."""
    local_now = datetime.now(_tz())
    result: Dict[str, Any] = {
        "enabled": bool(cfg.KEEPALIVE_URL),
        "in_window": in_window(local_now),
        "window": f"{cfg.KEEPALIVE_START_HOUR:02d}:00-{cfg.KEEPALIVE_END_HOUR:02d}:00 {cfg.KEEPALIVE_TIMEZONE}",
        "local_time": local_now.isoformat(timespec="seconds"),
        "pinged": False,
    }
    if not result["enabled"]:
        result["reason"] = "KEEPALIVE_URL is not set"
        return result
    if not result["in_window"]:
        result["reason"] = "outside the keep-alive window"
        return result
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_base_url()}/health")
        result.update(pinged=True, status_code=resp.status_code, ok=resp.is_success)
    except httpx.HTTPError as exc:
        result.update(pinged=True, ok=False, error=f"{type(exc).__name__}: {exc}"[:200])
    return result


async def run_loop() -> None:
    """Background task started from the app lifespan: every interval, inside the window,
    call our own public /api/keepalive (which then pings /health)."""
    interval = max(1, cfg.KEEPALIVE_INTERVAL_MINS) * 60
    url = f"{_base_url()}/api/keepalive"
    logger.info("keep-alive loop started: %s every %d min, %02d:00-%02d:00 %s",
                url, interval // 60, cfg.KEEPALIVE_START_HOUR, cfg.KEEPALIVE_END_HOUR,
                cfg.KEEPALIVE_TIMEZONE)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        while True:
            await asyncio.sleep(interval)
            if not in_window():
                continue
            try:
                resp = await client.get(url)
                logger.info("keep-alive ping status=%s body=%s", resp.status_code, resp.text[:200])
            except httpx.HTTPError as exc:
                logger.warning("keep-alive ping failed: %s", exc)
