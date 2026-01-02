#!/usr/bin/env python3
"""
IBKR scanner -> symbols -> Benzinga (sequential) + Polygon (rate-limited) -> CSV

Why this version:
- Benzinga: one symbol at a time (sequential), paginated, with health check + access logs
- Polygon: one symbol at a time with strict rate limiter + 429 exponential backoff + access logs
- No hard-coded keys (reads env only)
- Writes symbols.csv + news.csv

Install:
  python3 -m pip install ib_insync aiohttp pandas python-dateutil

Env:
  BENZINGA_API_KEY
  POLYGON_API_KEY

Run:
  python3 ibkr_news.py --port 7496 --limit 50 --days 2 --polygon-interval 15
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import aiohttp
import pandas as pd
from dateutil import parser as dateparser
from ib_insync import IB, ScannerSubscription


# -----------------------------
# Logging helpers
# -----------------------------

def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def redact_key(s: str, keep: int = 6) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "..." + "*" * 6

def sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(params)
    for k in list(out.keys()):
        if k.lower() in ("token", "apikey", "api_key", "key"):
            out[k] = redact_key(out[k])
    return out

def log_line(path: str, msg: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "a") as f:
        f.write(msg.rstrip() + "\n")


# -----------------------------
# Rate limiter (Polygon)
# -----------------------------

class RateLimiter:
    """Enforce at most 1 request per `min_interval` seconds (global)."""
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


# -----------------------------
# Data model
# -----------------------------

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


# -----------------------------
# Utilities
# -----------------------------

def normalize_symbol(sym: str) -> str:
    sym = sym.strip().upper()
    sym = re.sub(r"[^A-Z0-9.\-]", "", sym)
    return sym

def to_ymd(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")

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


# -----------------------------
# IBKR scanner
# -----------------------------

def fetch_ibkr_scanner_symbols(
    host: str,
    port: int,
    client_id: int,
    scan_code: str,
    location_code: str,
    limit: int,
    timeout: int = 30,
) -> List[str]:
    ib = IB()
    ib.connect(host, port, clientId=client_id, readonly=True, timeout=timeout)

    sub = ScannerSubscription(
        instrument="STK",
        locationCode=location_code,
        scanCode=scan_code,
        numberOfRows=limit,
    )

    rows = ib.reqScannerData(sub)

    symbols: List[str] = []
    for r in rows:
        c = r.contractDetails.contract
        if getattr(c, "symbol", None):
            symbols.append(normalize_symbol(c.symbol))

    # dedupe preserve order
    seen = set()
    uniq: List[str] = []
    for s in symbols:
        if s and s not in seen:
            uniq.append(s)
            seen.add(s)

    ib.disconnect()
    return uniq


def save_symbols_csv(symbols: List[str], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol"])
        for s in symbols:
            w.writerow([s])


def save_news_csv(items: List[NewsItem], path: str) -> None:
    df = pd.DataFrame([{
        "symbol": n.symbol,
        "provider": n.provider,
        "published_at": n.published_at,
        "headline": n.headline,
        "url": n.url,
        "summary": n.summary,
        "source": n.source,
        "raw_id": n.raw_id,
    } for n in items])
    df.to_csv(path, index=False)


# -----------------------------
# HTTP client with access logs
# -----------------------------

class HttpClient:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def get_text(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        *,
        log_path: Optional[str] = None,
        label: str = "",
    ) -> Tuple[int, str]:
        t0 = dt.datetime.now(dt.timezone.utc)
        async with self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as r:
            text = await r.text()
            dt_ms = int((dt.datetime.now(dt.timezone.utc) - t0).total_seconds() * 1000)

            if log_path:
                log_line(
                    log_path,
                    f"[{now_iso()}] {label} status={r.status} ms={dt_ms} url={url} "
                    f"params={sanitize_params(params)} body_head={text[:350]!r}"
                )
            return r.status, text

    async def get_json(
        self,
        url: str,
        params: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        *,
        log_path: Optional[str] = None,
        label: str = "",
    ) -> Any:
        status, text = await self.get_text(url, params, headers, log_path=log_path, label=label)
        if status >= 400:
            raise RuntimeError(f"HTTP {status} {url} params={sanitize_params(params)} body={text[:800]}")
        if text.lstrip().startswith("<?xml"):
            # Benzinga sometimes returns empty XML wrapper
            return []
        try:
            return json.loads(text)
        except Exception:
            raise RuntimeError(f"Non-JSON response from {url}: {text[:800]}")


# -----------------------------
# Benzinga (SEQUENTIAL, per symbol)
# -----------------------------

async def benzinga_health_check(hc: HttpClient, date_from: str, date_to: str) -> bool:
    api_key = os.getenv("BENZINGA_API_KEY", "").strip()
    if not api_key:
        return False

    url = "https://api.benzinga.com/api/v2/news"
    params = {
        "token": api_key,
        "tickers": "AAPL",
        "dateFrom": date_from,
        "dateTo": date_to,
        "page": 0,
        "pageSize": 5,
        "sort": "updated:desc",
    }

    try:
        data = await hc.get_json(url, params=params, headers={"accept": "application/json"},
                                 log_path="./logs/benzinga.log", label="BENZINGA_HEALTH")
        articles = data if isinstance(data, list) else data.get("articles") or data.get("data") or data.get("news") or []
        return len(articles) > 0
    except Exception:
        return False


async def fetch_benzinga_sequential(
    hc: HttpClient,
    symbols: Sequence[str],
    date_from: str,
    date_to: str,
    *,
    pages_per_symbol: int = 4,
    sleep_between_calls: float = 0.35,
    log_path: str = "./logs/benzinga.log",
) -> List[NewsItem]:
    api_key = os.getenv("BENZINGA_API_KEY", "").strip()
    if not api_key:
        print("  Benzinga: BENZINGA_API_KEY not set")
        return []

    url = "https://api.benzinga.com/api/v2/news"
    headers = {"accept": "application/json"}
    out: List[NewsItem] = []

    for idx, sym in enumerate(symbols, start=1):
        sym = normalize_symbol(sym)
        if not sym:
            continue

        for page in range(pages_per_symbol):
            params = {
                "token": api_key,
                "tickers": sym,
                "dateFrom": date_from,
                "dateTo": date_to,
                "page": page,
                "pageSize": 100,
                "sort": "updated:desc",
            }

            try:
                data = await hc.get_json(url, params=params, headers=headers, log_path=log_path,
                                         label=f"BENZINGA {sym} page={page}")
            except Exception as e:
                print(f"  Benzinga error for {sym}: {e}")
                break

            articles = data if isinstance(data, list) else data.get("articles") or data.get("data") or data.get("news") or []
            if not articles:
                break

            for a in articles:
                title = safe_str(a.get("title"))
                teaser = safe_str(a.get("teaser"))
                created = safe_str(a.get("created")) or safe_str(a.get("updated"))
                url_ = safe_str(a.get("url")) or safe_str(a.get("link"))

                out.append(NewsItem(
                    symbol=sym,
                    provider="benzinga",
                    published_at=created,
                    headline=title,
                    url=url_,
                    summary=teaser,
                    source="Benzinga",
                    raw_id=safe_str(a.get("id")),
                ))

            await asyncio.sleep(sleep_between_calls)

        if idx % 10 == 0:
            print(f"  Benzinga processed {idx}/{len(symbols)}")

    log_line(log_path, f"[{now_iso()}] BENZINGA done items={len(out)}")
    return out


# -----------------------------
# Polygon (rate-limited, sequential)
# -----------------------------

async def fetch_polygon_rate_limited(
    hc: HttpClient,
    symbols: Sequence[str],
    date_from: str,
    date_to: str,
    *,
    min_interval_sec: float = 15.0,
    max_retries: int = 6,
    log_path: str = "./logs/polygon.log",
) -> List[NewsItem]:
    api_key = "ef2s5m1rTW97TuR2rLZLI4jhyupDkzU6"
    if not api_key:
        print("  Polygon: POLYGON_API_KEY not set")
        return []

    url = "https://api.polygon.io/v2/reference/news"
    headers = {"accept": "application/json"}
    out: List[NewsItem] = []

    limiter = RateLimiter(min_interval_sec)
    log_line(log_path, f"[{now_iso()}] POLYGON start key_head={redact_key(api_key)} interval={min_interval_sec}s")

    for idx, sym in enumerate(symbols, start=1):
        sym = normalize_symbol(sym)
        if not sym:
            continue

        params = {
            "ticker": sym,
            "limit": 50,
            "order": "desc",
            "sort": "published_utc",
            "published_utc.gte": f"{date_from}T00:00:00Z",
            "published_utc.lte": f"{date_to}T23:59:59Z",
            "apiKey": api_key,
        }

        await limiter.wait()

        for attempt in range(max_retries):
            try:
                data = await hc.get_json(url, params=params, headers=headers, log_path=log_path,
                                         label=f"POLYGON {sym} attempt={attempt+1}")
            except Exception as e:
                msg = str(e)
                if "HTTP 429" in msg:
                    sleep_s = min(120.0, (min_interval_sec * (2 ** attempt)))
                    print(f"  Polygon 429 for {sym} attempt {attempt+1}/{max_retries} sleep {sleep_s:.1f}s")
                    await asyncio.sleep(sleep_s)
                    continue
                print(f"  Polygon error for {sym}: {e}")
                break

            if isinstance(data, dict) and data.get("status") == "ERROR":
                print(f"  Polygon API ERROR for {sym}: {data.get('error')}")
                break

            results = data.get("results", []) if isinstance(data, dict) else []
            for a in (results or []):
                out.append(NewsItem(
                    symbol=sym,
                    provider="polygon",
                    published_at=safe_str(a.get("published_utc")),
                    headline=safe_str(a.get("title")),
                    url=safe_str(a.get("article_url")),
                    summary=safe_str(a.get("description")),
                    source=safe_str((a.get("publisher") or {}).get("name")),
                    raw_id=safe_str(a.get("id")),
                ))
            break

        if idx % 10 == 0:
            print(f"  Polygon processed {idx}/{len(symbols)}")

    log_line(log_path, f"[{now_iso()}] POLYGON done items={len(out)}")
    return out


# -----------------------------
# Orchestration
# -----------------------------

async def run(symbols: List[str], days: int, polygon_interval: float, enable_benzinga: bool, enable_polygon: bool) -> List[NewsItem]:
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    date_from = to_ymd(start)
    date_to = to_ymd(today)

    connector = aiohttp.TCPConnector(limit=4, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        hc = HttpClient(session)
        items: List[NewsItem] = []

        if enable_benzinga:
            ok = await benzinga_health_check(hc, date_from, date_to)
            print(f"  Benzinga health: {'OK' if ok else 'FAILED (empty / no access)'} (see ./logs/benzinga.log)")
            if ok:
                bz = await fetch_benzinga_sequential(hc, symbols, date_from, date_to)
                print(f"  Benzinga items: {len(bz)}")
                items.extend(bz)
            else:
                print("  Skipping Benzinga fetch because health check returned empty.")

        if enable_polygon:
            pg = await fetch_polygon_rate_limited(hc, symbols, date_from, date_to, min_interval_sec=polygon_interval)
            print(f"  Polygon items: {len(pg)}")
            items.extend(pg)

    # Filter + dedupe
    filtered = [x for x in items if within_last_days(x.published_at, days)]
    seen = set()
    uniq: List[NewsItem] = []
    for n in filtered:
        key = (n.provider, n.url) if n.url else (n.provider, n.symbol, n.headline, n.published_at)
        if key not in seen:
            seen.add(key)
            uniq.append(n)

    uniq.sort(key=lambda x: x.published_at or "", reverse=True)
    return uniq


# -----------------------------
# CLI
# -----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7496)
    p.add_argument("--client-id", type=int, default=1001)
    p.add_argument("--scan-code", default="TOP_PERC_GAIN")
    p.add_argument("--location", default="STK.US.MAJOR")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--days", type=int, default=2)
    p.add_argument("--out-symbols", default="./symbols.csv")
    p.add_argument("--out-news", default="./news.csv")
    p.add_argument("--polygon-interval", type=float, default=15.0)
    p.add_argument("--no-benzinga", action="store_true")
    p.add_argument("--no-polygon", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"✓ Connecting to IBKR on port {args.port}")
    symbols = fetch_ibkr_scanner_symbols(
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        scan_code=args.scan_code,
        location_code=args.location,
        limit=args.limit,
    )

    print(f"✓ Found {len(symbols)} symbols from scanner")
    print("Symbols:", ", ".join(symbols))

    save_symbols_csv(symbols, args.out_symbols)
    print(f"✓ Saved symbols to {args.out_symbols}")

    print(f"Fetching last {args.days} day(s) news…")
    items = asyncio.run(run(
        symbols=symbols,
        days=args.days,
        polygon_interval=args.polygon_interval,
        enable_benzinga=(not args.no_benzinga),
        enable_polygon=(not args.no_polygon),
    ))

    print(f"✓ News items collected: {len(items)}")
    save_news_csv(items, args.out_news)
    print(f"✓ Saved news to {args.out_news}")

    if items:
        df = pd.DataFrame([{
            "symbol": n.symbol,
            "provider": n.provider,
            "published_at": n.published_at,
            "headline": (n.headline or "")[:110],
            "url": n.url,
        } for n in items[:25]])
        print(df.to_string(index=False))
    else:
        print("No items. Check logs:")
        print("  - ./logs/benzinga.log")
        print("  - ./logs/polygon.log")


if __name__ == "__main__":
    main()
