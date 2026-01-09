#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Set, Optional
import re

import pandas as pd
from ib_insync import IB, Contract, util

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7496
DEFAULT_CLIENT_ID = 2101  # keep unique vs other scripts

# IMPORTANT: keep this small. Too many providers triggers timeouts / pacing violations.
DEFAULT_PROVIDERS = ["BRFG", "DJ-N"]  # start with 1-2 only

NEWS_COLUMNS = [
    "symbol",
    "provider",
    "time",
    "time_utc",
    "articleId",
    "headline",
]

_HEAD_PREFIX_RE = re.compile(r"^\s*\{A:[^}]*\}\s*\*?\s*")


def clean_headline(text: str) -> str:
    if not text:
        return ""
    s = str(text).strip()
    for _ in range(3):
        s2 = _HEAD_PREFIX_RE.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return s


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ib_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%d %H:%M:%S")


def read_symbols(scanner: str, limit: int) -> List[str]:
    p = DATA_DIR / f"ibkr_data_{scanner}.csv"
    if not p.exists() or p.stat().st_size < 5:
        return []
    df = pd.read_csv(p)
    if df is None or df.empty or "symbol" not in df.columns:
        return []
    syms = (
        df["symbol"]
        .astype(str)
        .str.upper()
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )
    return syms[:limit]


def write_csv(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(NEWS_COLUMNS)
        for r in rows:
            w.writerow(r)


def parse_ibkr_news_time(s: str) -> Optional[datetime]:
    # IB sometimes returns "YYYY-MM-DD HH:MM:SS"
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def req_historical_news_safe(
    ib: IB,
    conId: int,
    provider: str,
    start: datetime,
    max_results: int,
    timeout_sec: float,
) -> list:
    """
    Returns list of news items, or [] on timeout/error.
    """
    try:
        # ib_insync has async under the hood; timeout often manifests as None
        news = ib.reqHistoricalNews(conId, provider, ib_time(start), "", max_results, [])
        # Give IB some time to return; if it's going to timeout, it will.
        ib.sleep(0.2)
        if news is None:
            return []
        return list(news)
    except Exception:
        return []


def main() -> int:
    util.startLoop()  # macOS friendly

    ap = argparse.ArgumentParser(description="IBKR historical news (safe)")
    ap.add_argument("--scanner", required=True)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--client-id", type=int, default=DEFAULT_CLIENT_ID)

    ap.add_argument("--providers", default="")  # comma-separated
    ap.add_argument("--max-results", type=int, default=50)
    ap.add_argument("--timeout-sec", type=float, default=12.0)
    ap.add_argument("--sleep-ms", type=int, default=350)  # throttle between requests

    args = ap.parse_args()

    providers = (
        [p.strip() for p in args.providers.split(",") if p.strip()]
        if args.providers.strip()
        else DEFAULT_PROVIDERS
    )

    now = utc_now()
    cutoff = now - timedelta(days=int(args.days))
    print(f"NOW_UTC    : {now.isoformat()}")
    print(f"CUTOFF_UTC : {cutoff.isoformat()}  (last {args.days} days)")

    symbols = read_symbols(args.scanner, int(args.limit))
    print(f"Symbols    : {len(symbols)}")

    out_path = DATA_DIR / f"news_ibkr_{args.scanner}.csv"

    if not symbols:
        write_csv(out_path, [])
        print(f"✓ Wrote 0 rows -> {out_path}")
        return 0

    ib = IB()
    ib.connect(args.host, int(args.port), clientId=int(args.client_id), readonly=True, timeout=20)
    print(f"✓ Connected to IBKR {args.host}:{args.port} clientId={args.client_id}")

    rows = []
    seen: Set[str] = set()

    for idx, sym in enumerate(symbols, start=1):
        contract = Contract(symbol=sym, secType="STK", exchange="SMART", currency="USD")
        cds = ib.reqContractDetails(contract)
        ib.sleep(0.15)

        if not cds:
            continue
        conId = cds[0].contract.conId

        for prov in providers:
            # throttle to avoid pacing violations / timeouts
            time.sleep(max(0.0, args.sleep_ms / 1000.0))

            news_items = req_historical_news_safe(
                ib=ib,
                conId=conId,
                provider=prov,
                start=cutoff,
                max_results=int(args.max_results),
                timeout_sec=float(args.timeout_sec),
            )

            # if timeout -> []
            if not news_items:
                continue

            for n in news_items:
                article_id = getattr(n, "articleId", "") or ""
                headline = clean_headline(getattr(n, "headline", "") or "")
                t = getattr(n, "time", "") or ""
                dt = parse_ibkr_news_time(t)

                # Filter by cutoff if parsable
                if dt and dt < cutoff:
                    continue

                key = f"{sym}:{prov}:{article_id}"
                if key in seen:
                    continue
                seen.add(key)

                rows.append([
                    sym,
                    prov,
                    t,
                    dt.isoformat() if dt else "",
                    article_id,
                    headline,
                ])

        if idx % 10 == 0:
            print(f"Processed {idx}/{len(symbols)}", flush=True)

    try:
        ib.disconnect()
    except Exception:
        pass

    rows.sort(key=lambda r: r[3] or "", reverse=True)
    write_csv(out_path, rows)
    print(f"✓ Wrote {len(rows)} rows -> {out_path}")

    # Always succeed so refresh pipeline doesn't break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
