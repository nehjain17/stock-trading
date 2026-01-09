from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiohttp
from dateutil import parser as dateparser


# ---------- shared model ----------

@dataclass
class NewsItem:
    symbol: str
    provider: str
    published_at: str
    headline: str
    url: str
    summary: str = ""
    source: str = ""
    raw_id: str = ""


# ---------- small utils ----------

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def log_line(path: str, msg: str) -> None:
    d = os.path.dirname(path)
    if d:
        ensure_dir(d)
    with open(path, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

def redact_key(s: str, keep: int = 6) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "..." + "*" * 6

def sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(params or {})
    for k in list(out.keys()):
        if k.lower() in ("token", "apikey", "api_key", "key"):
            out[k] = redact_key(out[k])
    return out

def normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    return re.sub(r"[^A-Z0-9.\-]", "", sym)

def safe_str(x: Any) -> str:
    return "" if x is None else str(x)

def parse_dt_utc(s: str) -> Optional[dt.datetime]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = dateparser.parse(s)
        if not d:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None

def within_last_days(published_at: str, days: int) -> bool:
    d = parse_dt_utc(published_at)
    if not d:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    return d >= (now - dt.timedelta(days=days))


# ---------- shared HTTP client ----------

class HttpClient:
    def __init__(self, timeout_sec: float = 30.0):
        self.timeout = aiohttp.ClientTimeout(total=timeout_sec)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "HttpClient":
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
        self._session = None

    async def get_json(
        self,
        url: str,
        *,
        params: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
        log_path: str | None = None,
        label: str = "",
    ) -> Any:
        assert self._session is not None, "HttpClient must be used with 'async with'"
        p = params or {}
        h = headers or {}

        t0 = dt.datetime.now(dt.timezone.utc)
        try:
            async with self._session.get(url, params=p, headers=h) as r:
                text = await r.text()
                ms = int((dt.datetime.now(dt.timezone.utc) - t0).total_seconds() * 1000)
                if log_path:
                    log_line(
                        log_path,
                        f"[{now_iso()}] {label} status={r.status} ms={ms} url={url} params={sanitize_params(p)} body_head={text[:200]!r}",
                    )
                if r.status >= 400:
                    raise RuntimeError(f"HTTP {r.status}: {text[:500]}")
                ctype = r.headers.get("content-type", "")
                if "application/json" in ctype:
                    return await r.json()
                # try parse anyway
                return await r.json(content_type=None)
        except Exception as e:
            if log_path:
                log_line(log_path, f"[{now_iso()}] {label} EXC url={url} err={e}")
            raise


# ---------- rate limiter (shared) ----------

class RateLimiter:
    """At most 1 request per min_interval seconds (global)."""
    def __init__(self, min_interval: float):
        self.min_interval = float(min_interval)
        self._lock = asyncio.Lock()
        self._next_ok = 0.0

    async def wait(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if now < self._next_ok:
                await asyncio.sleep(self._next_ok - now)
            self._next_ok = loop.time() + self.min_interval
