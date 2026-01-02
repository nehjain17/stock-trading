#!/usr/bin/env python3
"""
IBKR Scanner -> Historical News -> ONE CSV (ONLY last N days)

- Python 3.9+
- Per-symbol dedup
- Only outputs last N days (default 2)
- Suppresses the expected Error 162 "scanner subscription cancelled"
"""

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.scanner import ScannerSubscription


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def ib_datetime(dt_utc: datetime) -> str:
    return dt_utc.strftime("%Y%m%d %H:%M:%S")

def parse_ib_time(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    if "." in s:
        s = s.split(".", 1)[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None

@dataclass
class NewsRow:
    symbol: str
    provider: str
    time_str: str
    time_utc: str
    article_id: str
    headline: str


def make_stock_contract(symbol: str, exchange: str = "SMART", currency: str = "USD") -> Contract:
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = exchange
    c.currency = currency
    return c


class App(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

        self.next_req_id: int = -1

        # Scanner
        self.scanner_symbols: List[str] = []
        self._scanner_done: bool = False

        # Contract details
        self.conids: Dict[str, int] = {}
        self._cd_pending: Dict[int, str] = {}
        self._cd_done: Set[str] = set()

        # Historical news state
        self._pending_reqid: Optional[int] = None
        self._pending_symbol: Optional[str] = None

        self.news_rows: List[NewsRow] = []
        self._dedup_per_symbol: Dict[str, Set[str]] = {}

        # errors
        self.errors: List[Tuple[int, int, str]] = []
        self._scanner_reqid: Optional[int] = None  # to suppress expected cancel msg

    def nextValidId(self, orderId: int):
        self.next_req_id = orderId

    def new_req_id(self) -> int:
        if self.next_req_id < 0:
            self.next_req_id = 1
        rid = self.next_req_id
        self.next_req_id += 1
        return rid

    # Scanner
    def scannerData(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr):
        sym = (contractDetails.contract.symbol or "").strip().upper()
        if sym and sym not in self.scanner_symbols:
            self.scanner_symbols.append(sym)

    def scannerDataEnd(self, reqId):
        self._scanner_done = True

    # Contract details
    def contractDetails(self, reqId, contractDetails):
        sym = self._cd_pending.get(reqId)
        if not sym:
            return
        conId = int(getattr(contractDetails.contract, "conId", 0) or 0)
        if conId and sym not in self.conids:
            self.conids[sym] = conId

    def contractDetailsEnd(self, reqId: int):
        sym = self._cd_pending.get(reqId)
        if sym:
            self._cd_done.add(sym)

    # Historical news
    def historicalNews(self, reqId, timeStr, providerCode, articleId, headline):
        sym = self._pending_symbol or "UNKNOWN"
        dt = parse_ib_time(timeStr)
        time_utc = dt.isoformat() if dt else ""

        # per-symbol dedup
        seen = self._dedup_per_symbol.setdefault(sym, set())
        if articleId and articleId in seen:
            return
        if articleId:
            seen.add(articleId)

        self.news_rows.append(
            NewsRow(
                symbol=sym,
                provider=str(providerCode),
                time_str=str(timeStr),
                time_utc=time_utc,
                article_id=str(articleId),
                headline=str(headline),
            )
        )

    def historicalNewsEnd(self, reqId, hasMore):
        self._pending_reqid = None
        self._pending_symbol = None

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        self.errors.append((reqId, errorCode, errorString))

        # Suppress the EXPECTED scanner cancel noise:
        # "Historical Market Data Service error message: API scanner subscription cancelled"
        if errorCode == 162 and self._scanner_reqid is not None and reqId == self._scanner_reqid:
            return

        # Print only meaningful errors
        if errorCode in (162, 200, 354, 10089):
            print(f"[IB ERROR] reqId={reqId} code={errorCode}: {errorString}", file=sys.stderr)

        # unblock if pending request errors
        if self._pending_reqid is not None and reqId == self._pending_reqid:
            self._pending_reqid = None
            self._pending_symbol = None


def wait_until(pred, timeout: float, what: str):
    start = time.time()
    while True:
        if pred():
            return
        if time.time() - start > timeout:
            raise TimeoutError(f"Timed out waiting for {what}")
        time.sleep(0.05)


DEFAULT_PROVIDERS = ["BRFG", "BRFUPDN", "DJ-N", "DJ-RT", "DJ-RTA", "DJ-RTE", "DJ-RTG", "DJNL", "FLY"]


def write_csv(path: str, rows: List[NewsRow]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "provider", "time", "time_utc", "articleId", "headline"])
        for r in rows:
            w.writerow([r.symbol, r.provider, r.time_str, r.time_utc, r.article_id, r.headline])


def run(
    host: str,
    port: int,
    client_id: int,
    screener: str,
    location: str,
    max_symbols: int,
    days: int,
    providers: List[str],
    total_results_per_provider: int,
    pace_seconds: float,
    out_csv: str,
    exchange: str,
    currency: str,
):
    app = App()
    app.connect(host, port, client_id)

    import threading
    threading.Thread(target=app.run, daemon=True).start()

    wait_until(lambda: app.next_req_id >= 0, timeout=10, what="nextValidId")
    print(f"✓ Connected to IBKR {host}:{port} clientId={client_id}")

    now = utc_now()
    cutoff = now - timedelta(days=days)
    start_dt = ib_datetime(cutoff)

    print(f"NOW_UTC    : {now.isoformat()}")
    print(f"CUTOFF_UTC : {cutoff.isoformat()}  (last {days} days)")
    print(f"startDateTime sent to IB: {start_dt}\n")

    # Scanner
    scan_req = app.new_req_id()
    app._scanner_reqid = scan_req  # used to suppress expected cancel error
    sub = ScannerSubscription()
    sub.instrument = "STK"
    sub.locationCode = location
    sub.scanCode = screener
    sub.numberOfRows = max_symbols

    app.reqScannerSubscription(scan_req, sub, [], [])
    wait_until(lambda: app._scanner_done, timeout=25, what="scanner results")
    app.cancelScannerSubscription(scan_req)

    symbols = app.scanner_symbols[:max_symbols]
    print(f"✓ Scanner {screener} returned {len(symbols)} symbols\n")

    # ContractDetails (conId)
    for sym in symbols:
        rid = app.new_req_id()
        app._cd_pending[rid] = sym
        app.reqContractDetails(rid, make_stock_contract(sym, exchange=exchange, currency=currency))
        time.sleep(0.12)

    wait_until(lambda: len(app._cd_done) >= len(symbols), timeout=40, what="contract details")

    # News per symbol
    for i, sym in enumerate(symbols, 1):
        conId = app.conids.get(sym)
        if not conId:
            continue

        for prov in providers:
            rid = app.new_req_id()
            app._pending_reqid = rid
            app._pending_symbol = sym

            app.reqHistoricalNews(
                rid,
                conId,
                prov,
                start_dt,
                "",
                total_results_per_provider,
                []
            )

            wait_until(lambda: app._pending_reqid is None, timeout=12, what=f"historicalNews {sym} {prov}")
            time.sleep(pace_seconds)

    app.disconnect()

    # Filter ONLY last N days (parseable time required)
    filtered: List[NewsRow] = []
    for r in app.news_rows:
        if not r.time_utc:
            continue
        try:
            dt = datetime.fromisoformat(r.time_utc)
        except Exception:
            continue
        if dt >= cutoff:
            filtered.append(r)

    filtered.sort(key=lambda r: r.time_utc, reverse=True)
    write_csv(out_csv, filtered)

    print(f"✓ Wrote {len(filtered)} rows -> {out_csv}")

    # Optional: still report symbols with no recent news (not an error)
    has_recent: Set[str] = set(r.symbol for r in filtered)
    no_recent = [s for s in symbols if s not in has_recent]
    if no_recent:
        print("No 2-day headlines for:", ", ".join(no_recent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7496)
    ap.add_argument("--clientId", type=int, default=1101)

    ap.add_argument("--screener", default="TOP_PERC_GAIN")
    ap.add_argument("--location", default="STK.US.MAJOR")
    ap.add_argument("--max", type=int, default=50)
    ap.add_argument("--days", type=int, default=3)

    ap.add_argument("--providers", default="")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--pace", type=float, default=0.25)

    ap.add_argument("--out", default="news_ALL_SYMBOLS.csv")
    ap.add_argument("--exchange", default="SMART")
    ap.add_argument("--currency", default="USD")

    args = ap.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()] if args.providers.strip() else DEFAULT_PROVIDERS

    run(
        host=args.host,
        port=args.port,
        client_id=args.clientId,
        screener=args.screener,
        location=args.location,
        max_symbols=args.max,
        days=args.days,
        providers=providers,
        total_results_per_provider=args.limit,
        pace_seconds=args.pace,
        out_csv=args.out,
        exchange=args.exchange,
        currency=args.currency,
    )


if __name__ == "__main__":
    main()
