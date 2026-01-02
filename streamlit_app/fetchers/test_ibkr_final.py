#!/usr/bin/env python3
"""
FAST SYNC VERSION (no asyncio):
- Scanner -> symbols
- Yahoo prefetch once
- Process symbols in batches (default 10):
    * start mkt data for 10 symbols
    * wait once
    * sample volume once
    * read all tickers
    * cancel all tickers
This is much faster than doing wait+sample per symbol.

Outputs CSV:
rank,symbol,description,last,yahoo_prev_close,pct_change,volume,
shortable_shares,trade_rate,volume_rate,computed_volume_per_min,effective_volume_per_min,
market_cap,float_shares
"""

import argparse
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from ib_insync import IB, ScannerSubscription, Stock

SCANNER_CODES = {
    "top_gainers": "TOP_PERC_GAIN",
    "top_losers": "TOP_PERC_LOSE",
    "most_active": "MOST_ACTIVE",
    "hot_by_volume": "HOT_BY_VOLUME",
    "top_volume": "TOP_VOLUME",
    "hot_by_price": "HOT_BY_PRICE",
}

GENERIC_TICKS = "236,294,295"  # shortableShares, tradeRate, volumeRate


def safe(v: Any) -> Any:
    return "N/A" if v is None else v


def set_market_data_type(ib: IB, prefer_delayed: bool) -> str:
    if prefer_delayed:
        try:
            ib.reqMarketDataType(3)
            return "delayed"
        except Exception:
            pass
    try:
        ib.reqMarketDataType(1)
        return "real-time"
    except Exception:
        try:
            ib.reqMarketDataType(2)
            return "frozen"
        except Exception:
            return "unknown"


def fetch_scanner_symbols_and_desc(ib: IB, scan_code: str, location: str, limit: int) -> List[Tuple[str, str]]:
    scan = ScannerSubscription(
        instrument="STK",
        locationCode=location,
        scanCode=scan_code,
        numberOfRows=limit,
    )
    items = ib.reqScannerData(scan)
    ib.sleep(0.8)

    out: List[Tuple[str, str]] = []
    for d in (items or [])[:limit]:
        cd = d.contractDetails
        sym = cd.contract.symbol
        desc = getattr(cd, "longName", "") or ""
        out.append((sym, desc))
    return out


def get_description_if_missing(ib: IB, contract, existing: str) -> str:
    if existing:
        return existing
    try:
        cds = ib.reqContractDetails(contract)
        if cds:
            ln = getattr(cds[0], "longName", "") or ""
            return ln
    except Exception:
        pass
    return ""


def compute_volume_per_min(vol0: Optional[float], vol1: Optional[float], dt_sec: float) -> Optional[float]:
    if vol0 is None or vol1 is None or dt_sec <= 0:
        return None
    dv = vol1 - vol0
    if dv <= 0:
        return 0.0
    return dv / (dt_sec / 60.0)


def yahoo_batch_fetch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    try:
        import yfinance as yf
    except Exception:
        print("! yfinance not installed. Run: pip3 install yfinance")
        return {}

    cache: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info or {}
            prev_close = (
                info.get("previousClose")
                or info.get("regularMarketPreviousClose")
                or info.get("chartPreviousClose")
            )
            cache[sym] = {
                "marketCap": info.get("marketCap"),
                "floatShares": info.get("floatShares"),
                "sharesOutstanding": info.get("sharesOutstanding"),
                "prevClose": prev_close,
            }
        except Exception:
            cache[sym] = {"marketCap": None, "floatShares": None, "sharesOutstanding": None, "prevClose": None}

    return cache


def pct_change_from(last: Optional[float], prev_close: Optional[float]) -> Optional[float]:
    if last is None or prev_close is None or prev_close == 0:
        return None
    return (last - prev_close) / prev_close * 100.0


def chunks(lst: List[Any], n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def main():
    ap = argparse.ArgumentParser(description="FAST sync IBKR scanner + batch metrics + Yahoo enrichment")
    ap.add_argument("--port", type=int, default=7496, help="7496 live, 7497 paper")
    ap.add_argument("--limit", type=int, default=100, help="Top N stocks (default 100)")
    ap.add_argument("--batch-size", type=int, default=10, help="How many symbols to process at once (default 10)")
    ap.add_argument("--scanner", type=str, default="top_gainers", choices=SCANNER_CODES.keys())
    ap.add_argument("--location", type=str, default="STK.US.MAJOR")
    ap.add_argument("--wait-sec", type=float, default=1.5, help="initial wait after starting mkt data for a batch")
    ap.add_argument("--sample-sec", type=float, default=4.0, help="sampling window for computed vol/min (batch-wide)")
    ap.add_argument("--prefer-delayed", action="store_true")
    ap.add_argument("--no-qualify", action="store_true")
    ap.add_argument("--output", type=str, default="./ibkr_scanner_metrics.csv")
    args = ap.parse_args()

    ib = IB()
    ib.connect("127.0.0.1", args.port, clientId=1001, readonly=True, timeout=60)
    print(f"✓ Connected to IBKR on port {args.port}")

    md = set_market_data_type(ib, prefer_delayed=args.prefer_delayed)
    print(f"✓ Market data type: {md}")

    scan_code = SCANNER_CODES[args.scanner]
    print(f"Requesting scanner: {scan_code} @ {args.location} ...")
    sym_desc = fetch_scanner_symbols_and_desc(ib, scan_code, args.location, args.limit)

    symbols = [s for s, _ in sym_desc]
    print(f"✓ Found {len(symbols)} symbols from scanner\n")

    print("Scanner symbols:")
    for i, s in enumerate(symbols, start=1):
        print(f"{i:3d}. {s}")
    print()

    print("Prefetching Yahoo (prevClose/marketCap/float)...")
    yahoo = yahoo_batch_fetch(symbols)

    rows: List[Dict[str, Any]] = []

    # Process in batches
    for batch_idx, batch in enumerate(chunks(sym_desc, args.batch_size), start=1):
        # Build contracts for the batch
        contracts = []
        desc_map = {}
        for sym, desc0 in batch:
            c = Stock(sym, "SMART", "USD")
            contracts.append(c)
            desc_map[sym] = desc0

        # Qualify batch (optional)
        if not args.no_qualify:
            try:
                ib.qualifyContracts(*contracts)
            except Exception:
                pass

        # Start market data for all in batch
        tickers = []
        for c in contracts:
            try:
                t = ib.reqMktData(c, GENERIC_TICKS, snapshot=False, regulatorySnapshot=False)
                tickers.append((c, t))
            except Exception:
                tickers.append((c, None))

        # Wait once for batch to populate
        ib.sleep(max(0.2, args.wait_sec))

        # Snapshot volume at t0
        vol0_map: Dict[str, Optional[float]] = {}
        t0 = time.time()
        for c, t in tickers:
            sym = c.symbol
            vol0_map[sym] = getattr(t, "volume", None) if t is not None else None

        # Sample window once for batch
        ib.sleep(max(0.0, args.sample_sec))

        # Snapshot volume at t1
        t1 = time.time()
        dt = t1 - t0

        # Build rows for each symbol in batch
        for (c, t) in tickers:
            sym = c.symbol
            desc0 = desc_map.get(sym, "")
            desc = get_description_if_missing(ib, c, desc0)

            y = yahoo.get(sym, {})
            y_prev = y.get("prevClose")
            y_mktcap = y.get("marketCap")
            y_float = y.get("floatShares") if y.get("floatShares") is not None else y.get("sharesOutstanding")

            if t is None:
                rows.append(
                    {
                        "rank": symbols.index(sym) + 1,
                        "symbol": sym,
                        "description": desc if desc else "N/A",
                        "last": "N/A",
                        "yahoo_prev_close": safe(y_prev),
                        "pct_change": "N/A",
                        "volume": "N/A",
                        "shortable_shares": "N/A",
                        "trade_rate": "N/A",
                        "volume_rate": "N/A",
                        "computed_volume_per_min": "N/A",
                        "effective_volume_per_min": "N/A",
                        "market_cap": safe(y_mktcap),
                        "float_shares": safe(y_float),
                        "error": "reqMktData failed",
                    }
                )
                continue

            last = getattr(t, "last", None) or getattr(t, "close", None)
            vol1 = getattr(t, "volume", None)

            computed_vpm = compute_volume_per_min(vol0_map.get(sym), vol1, dt)

            shortable = getattr(t, "shortableShares", None)
            trade_rate = getattr(t, "tradeRate", None)
            volume_rate = getattr(t, "volumeRate", None)

            effective_vpm = volume_rate
            if (effective_vpm is None or effective_vpm == 0.0) and (computed_vpm is not None and computed_vpm > 0):
                effective_vpm = computed_vpm

            pct = pct_change_from(last, y_prev)

            rows.append(
                {
                    "rank": symbols.index(sym) + 1,
                    "symbol": sym,
                    "description": desc if desc else "N/A",
                    "last": safe(last),
                    "yahoo_prev_close": safe(y_prev),
                    "pct_change": safe(pct),
                    "volume": safe(vol1),
                    "shortable_shares": safe(shortable),
                    "trade_rate": safe(trade_rate),
                    "volume_rate": safe(volume_rate),
                    "computed_volume_per_min": safe(computed_vpm),
                    "effective_volume_per_min": safe(effective_vpm),
                    "market_cap": safe(y_mktcap),
                    "float_shares": safe(y_float),
                }
            )

        # Cancel market data for batch
        for c, _t in tickers:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass

        done = min(batch_idx * args.batch_size, len(sym_desc))
        print(f"  Processed {done}/{len(sym_desc)}")

    ib.disconnect()

    # sort by rank
    rows.sort(key=lambda r: r.get("rank", 10**9))

    df = pd.DataFrame(rows).fillna("N/A")
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    df.to_csv(args.output, index=False, na_rep="N/A")

    print(f"\n✓ Saved {len(df)} rows to {args.output}")
    print(
        df[
            [
                "rank",
                "symbol",
                "last",
                "yahoo_prev_close",
                "pct_change",
                "volume",
                "shortable_shares",
                "trade_rate",
                "effective_volume_per_min",
                "market_cap",
                "float_shares",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
