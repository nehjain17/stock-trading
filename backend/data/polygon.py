#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

import requests


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
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
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def polygon_news(api_key: str, symbol: str, date_from: datetime, date_to: datetime, timeout: int = 20) -> list:
    # Polygon endpoint: /v2/reference/news?ticker=...
    url = "https://api.polygon.io/v2/reference/news"
    params = {
        "ticker": symbol,
        "published_utc.gte": date_from.strftime("%Y-%m-%d"),
        "published_utc.lte": date_to.strftime("%Y-%m-%d"),
        "order": "desc",
        "limit": 50,
        "apiKey": api_key,
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            return []
        js = r.json() or {}
        return js.get("results") or []
    except Exception:
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Polygon news -> CSV (no IBKR)")
    ap.add_argument("--scanner", required=True)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--out", default="")
    ap.add_argument("--token", default=os.environ.get("POLYGON_API_KEY", ""))
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    out_path = args.out or os.path.join(os.path.dirname(__file__), f"news_polygon_{args.scanner}.csv")

    if not args.token:
        print("ERR: Missing POLYGON token. Set POLYGON_API_KEY or pass --token", file=sys.stderr)
        write_csv(out_path, [])
        return 0

    symbols = read_symbols_from_ibkr_csv(args.scanner, args.limit)

    now = utc_now()
    cutoff = now - timedelta(days=args.days)

    rows: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for i, sym in enumerate(symbols, start=1):
        items = polygon_news(args.token, sym, cutoff, now, timeout=args.timeout)
        for it in items:
            headline = clean(str(it.get("title") or ""))
            if not headline:
                continue
            dt = parse_iso(str(it.get("published_utc") or ""))
            if dt and dt < cutoff:
                continue
            published = dt.isoformat() if dt else ""

            url = clean(str(it.get("article_url") or it.get("amp_url") or ""))
            article_id = clean(str(it.get("id") or ""))

            key = f"{sym}|{headline}"
            if key in seen:
                continue
            seen.add(key)

            rows.append({
                "scanner": args.scanner,
                "symbol": sym,
                "provider": "POLYGON",
                "providerName": "Polygon",
                "publishedUtc": published,
                "headline": headline,
                "url": url,
                "articleId": article_id,
            })

        if i % 10 == 0:
            print(f"Processed {i}/{len(symbols)}", flush=True)

    rows.sort(key=lambda r: r.get("publishedUtc") or "", reverse=True)
    write_csv(out_path, rows)
    print(f"✓ Wrote {len(rows)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
