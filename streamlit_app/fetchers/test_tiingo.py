#!/usr/bin/env python3
"""
tiingo_news_to_csv.py

Fetch Tiingo News via REST API and write results to *separate CSV files*
(one per ticker), plus an optional "ALL" combined CSV.

Docs: https://www.tiingo.com/documentation/news

Usage examples:
  export TIINGO_API_KEY="YOUR_KEY"

  # last 2 days for CRWD and INBS -> writes news_CRWD.csv and news_INBS.csv
  python3 tiingo_news_to_csv.py --tickers CRWD,INBS --start 2025-12-30 --end 2026-01-01

  # filter by tag + source domain
  python3 tiingo_news_to_csv.py --tickers CRWD --start 2025-12-01 --end 2026-01-01 --tags Earnings --source reuters.com

Outputs:
  - ./tiingo_out/news_<TICKER>_<start>_to_<end>.csv
  - (optional) ./tiingo_out/news_ALL_<start>_to_<end>.csv if --write-all
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests


TIINGO_NEWS_URL = "https://api.tiingo.com/tiingo/news"


CSV_FIELDS = [
    "id",
    "publishedDate",
    "crawlDate",
    "source",
    "title",
    "description",
    "url",
    "tickers",  # semicolon-joined
    "tags",     # semicolon-joined
]


def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i) for i in x]
    return [str(x)]


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x)


def fetch_tiingo_news_page(
    session: requests.Session,
    api_key: str,
    tickers: Optional[str],
    start: Optional[str],
    end: Optional[str],
    tags: Optional[str],
    source: Optional[str],
    limit: int,
    offset: int,
    timeout_s: int,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }
    if tickers:
        params["tickers"] = tickers
    if start:
        params["startDate"] = start
    if end:
        params["endDate"] = end
    if tags:
        params["tags"] = tags
    if source:
        params["source"] = source

    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {api_key}",
        "User-Agent": "tiingo-news-csv/1.0",
    }

    r = session.get(TIINGO_NEWS_URL, params=params, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response type: {type(data)} head={str(data)[:200]}")
    return data


def normalize_rows(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for it in items:
        row = {
            "id": _safe_str(it.get("id")),
            "publishedDate": _safe_str(it.get("publishedDate")),
            "crawlDate": _safe_str(it.get("crawlDate")),
            "source": _safe_str(it.get("source")),
            "title": _safe_str(it.get("title")),
            "description": _safe_str(it.get("description")),
            "url": _safe_str(it.get("url")),
            "tickers": ";".join(_as_list(it.get("tickers"))),
            "tags": ";".join(_as_list(it.get("tags"))),
        }
        rows.append(row)
    return rows


def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=os.getenv("TIINGO_API_KEY", ""), help="Tiingo API key (or set TIINGO_API_KEY env).")
    ap.add_argument("--tickers", required=True, help="Comma-separated tickers, e.g. CRWD,INBS")
    ap.add_argument("--start", default="", help="YYYY-MM-DD startDate (optional)")
    ap.add_argument("--end", default="", help="YYYY-MM-DD endDate (optional)")
    ap.add_argument("--tags", default="", help='Optional tags filter (comma-separated), e.g. "Earnings"')
    ap.add_argument("--source", default="", help='Optional source filter (domain), e.g. "reuters.com"')
    ap.add_argument("--limit", type=int, default=100, help="Page size (Tiingo supports up to 1000).")
    ap.add_argument("--max-pages", type=int, default=50, help="Max pages to paginate.")
    ap.add_argument("--sleep-ms", type=int, default=150, help="Sleep between requests.")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--outdir", default="tiingo_out")
    ap.add_argument("--write-all", action="store_true", help="Also write a combined ALL CSV.")
    args = ap.parse_args()

    api_key = '6d62511584c5cd1bb4f3db495ab172017ec71660'
    if not api_key:
        print("ERROR: Missing Tiingo API key. Set TIINGO_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    tickers_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers_list:
        print("ERROR: Provide at least one ticker in --tickers", file=sys.stderr)
        return 2

    start = args.start.strip() or None
    end = args.end.strip() or None
    tags = args.tags.strip() or None
    source = args.source.strip() or None

    session = requests.Session()

    all_combined: List[Dict[str, str]] = []

    for t in tickers_list:
        offset = 0
        seen_ids: set[str] = set()
        collected: List[Dict[str, str]] = []

        # Fetch ticker-scoped news; then we still locally filter to ensure membership
        # in case Tiingo returns multi-ticker stories.
        for page in range(args.max_pages):
            items = fetch_tiingo_news_page(
                session=session,
                api_key=api_key,
                tickers=t,
                start=start,
                end=end,
                tags=tags,
                source=source,
                limit=args.limit,
                offset=offset,
                timeout_s=args.timeout,
            )
            if not items:
                break

            rows = normalize_rows(items)

            new_count = 0
            for r in rows:
                # Keep only rows that actually include this ticker in its tickers list
                tickers_in_row = set((r.get("tickers") or "").split(";")) if r.get("tickers") else set()
                if t not in tickers_in_row:
                    continue
                rid = r.get("id", "")
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                collected.append(r)
                all_combined.append(r)
                new_count += 1

            if new_count == 0:
                # If a whole page yielded nothing new after filtering/dedupe, stop to avoid spinning.
                break

            offset += args.limit
            time.sleep(max(0, args.sleep_ms) / 1000.0)

        start_s = start or "NA"
        end_s = end or "NA"
        out_path = os.path.join(args.outdir, f"news_{t}_{start_s}_to_{end_s}.csv")
        write_csv(out_path, collected)
        print(f"{t}: wrote {len(collected)} rows -> {out_path}")

    if args.write_all:
        start_s = start or "NA"
        end_s = end or "NA"
        out_all = os.path.join(args.outdir, f"news_ALL_{start_s}_to_{end_s}.csv")
        write_csv(out_all, all_combined)
        print(f"ALL: wrote {len(all_combined)} rows -> {out_all}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
