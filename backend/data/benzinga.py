#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

import requests


# ------------------------ Helpers ------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt_any(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    # Benzinga typically returns ISO like 2026-01-05T08:00:00Z or with offset
    fmts = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            pass
    # try fromisoformat (handles offsets)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def clean(s: str) -> str:
    return (s or "").replace("\n", " ").replace("\r", " ").strip()

def read_symbols_from_ibkr_csv(scanner: str, limit: int) -> List[str]:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, f"ibkr_data_{scanner}.csv")
    if not os.path.exists(path) or os.path.getsize(path) < 5:
        return []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        out: List[str] = []
        seen: Set[str] = set()
        for row in r:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
            if len(out) >= limit:
                break
        return out

def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [
        "scanner",
        "symbol",
        "provider",
        "providerName",
        "publishedUtc",
        "headline",
        "url",
        "articleId",
        "rawTime",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


# ------------------------ Benzinga Fetch ------------------------

@dataclass
class BenzingaCfg:
    token: str
    timeout: int = 20
    rpm: int = 60  # requests per minute throttle
    max_retries: int = 3
    min_interval: float = 1.0  # seconds
    page_size: int = 100
    pages_per_symbol: int = 2

def benzinga_get(cfg: BenzingaCfg, url: str, params: dict) -> Optional[list]:
    # throttle
    time.sleep(max(cfg.min_interval, 60.0 / max(1, cfg.rpm)))
    for attempt in range(cfg.max_retries):
        try:
            r = requests.get(url, params=params, timeout=cfg.timeout)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    return []
            # 429 rate limit -> backoff
            if r.status_code in (429, 503, 502):
                time.sleep(1.5 * (attempt + 1))
                continue
            # other errors: return empty
            return []
        except Exception:
            time.sleep(1.0 * (attempt + 1))
            continue
    return []

def fetch_benzinga_news(cfg: BenzingaCfg, symbol: str, date_from: datetime, date_to: datetime) -> List[Dict[str, str]]:
    url = "https://api.benzinga.com/api/v2/news"
    out: List[Dict[str, str]] = []

    dateFrom = date_from.strftime("%Y-%m-%d")
    dateTo = date_to.strftime("%Y-%m-%d")

    for page in range(cfg.pages_per_symbol):
        params = {
            "token": cfg.token,
            "tickers": symbol,
            "dateFrom": dateFrom,
            "dateTo": dateTo,
            "page": page,
            "pageSize": cfg.page_size,
            "sort": "updated:desc",
        }
        data = benzinga_get(cfg, url, params) or []
        if not data:
            break

        for it in data:
            headline = clean(str(it.get("title") or it.get("headline") or ""))
            if not headline:
                continue
            raw_time = str(it.get("updated") or it.get("created") or it.get("published") or "")
            dt = parse_dt_any(raw_time)
            if dt is None:
                # keep but mark unknown
                published_utc = ""
            else:
                published_utc = dt.isoformat()

            out.append({
                "scanner": "",
                "symbol": symbol,
                "provider": "BENZINGA",
                "providerName": "Benzinga",
                "publishedUtc": published_utc,
                "headline": headline,
                "url": clean(str(it.get("url") or it.get("link") or "")),
                "articleId": clean(str(it.get("id") or it.get("uuid") or "")),
                "rawTime": raw_time,
            })

        # If less than page size, done
        if len(data) < cfg.page_size:
            break

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Benzinga news -> CSV (no IBKR)")
    ap.add_argument("--scanner", required=True, help="most_active/top_gainers/top_trade_rate...")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default="", help="output CSV path override")
    ap.add_argument("--token", default=os.environ.get("BENZINGA_API_KEY", ""))
    ap.add_argument("--rpm", type=int, default=60)
    ap.add_argument("--pages-per-symbol", type=int, default=2)
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    if not args.token:
        print("ERR: Missing Benzinga token. Set BENZINGA_API_KEY or pass --token", file=sys.stderr)
        # Still write empty file so pipeline doesn't break
        out_path = args.out or os.path.join(os.path.dirname(__file__), f"news_benzinga_{args.scanner}.csv")
        write_csv(out_path, [])
        return 0

    symbols = read_symbols_from_ibkr_csv(args.scanner, args.limit)
    out_path = args.out or os.path.join(os.path.dirname(__file__), f"news_benzinga_{args.scanner}.csv")

    now = utc_now()
    cutoff = now - timedelta(days=args.days)

    print(f"Symbols: {len(symbols)}  (from ibkr_data_{args.scanner}.csv)")
    print(f"Window : {cutoff.isoformat()} .. {now.isoformat()}")

    cfg = BenzingaCfg(
        token=args.token,
        timeout=args.timeout,
        rpm=args.rpm,
        pages_per_symbol=args.pages_per_symbol,
        page_size=args.page_size,
    )

    rows: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for i, sym in enumerate(symbols, start=1):
        items = fetch_benzinga_news(cfg, sym, cutoff, now)
        for it in items:
            it["scanner"] = args.scanner
            # filter by time if parseable
            dt = parse_dt_any(it.get("publishedUtc") or it.get("rawTime") or "")
            if dt and dt < cutoff:
                continue
            # dedupe by symbol+headline
            key = f'{sym}|{it.get("headline","")}'
            if key in seen:
                continue
            seen.add(key)
            rows.append(it)

        if i % 10 == 0:
            print(f"Processed {i}/{len(symbols)}", flush=True)

    # sort newest first when we have publishedUtc
    def sort_key(r: Dict[str, str]) -> str:
        return r.get("publishedUtc") or r.get("rawTime") or ""

    rows.sort(key=sort_key, reverse=True)
    write_csv(out_path, rows)
    print(f"✓ Wrote {len(rows)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
