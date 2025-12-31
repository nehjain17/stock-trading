#!/usr/bin/env python3
"""
IBKR-only Core Metrics Fetcher

Fetches IBKR scanner results and collects only IBKR-provided metrics:
- Symbol
- Description (IBKR contract longName)
- Volume
- Market cap (from IBKR fundamental XML when available)
- Shortable shares (generic tick 236)
- Trades/min (generic tick 294)
- Volume/min (generic tick 295)

No Yahoo, no Finnhub, no news, no dashboard. Writes CSV.
"""

import argparse
import os
import time
import csv
from typing import Optional, List
from ib_insync import IB, ScannerSubscription, Stock
import pandas as pd
from xml.etree import ElementTree as ET


SCANNER_CODES = {
    'top_gainers': 'TOP_PERC_GAIN',
    'top_losers': 'TOP_PERC_LOSE',
    'most_active': 'MOST_ACTIVE',
    'hot_by_volume': 'HOT_BY_VOLUME',
    'top_volume': 'TOP_VOLUME',
    'hot_by_price': 'HOT_BY_PRICE',
    'after_hours_gainers': 'TOP_PERC_GAIN',  # alias
}


def _set_market_data_type(ib: IB, prefer_delayed: bool = True):
    """Try to set the best-available market data type."""
    if prefer_delayed:
        try:
            ib.reqMarketDataType(3)
            print("✓ Market data type: delayed")
            return
        except Exception:
            pass
    try:
        ib.reqMarketDataType(1)
        print("✓ Market data type: real-time")
        return
    except Exception:
        pass
    try:
        ib.reqMarketDataType(2)
        print("⚠ Market data type: frozen")
        return
    except Exception:
        print("⚠ Unable to set market data type")


def _fetch_market_cap(ib: IB, symbol: str) -> Optional[float]:
    """Attempt to fetch market cap from IBKR fundamentals XML.
    Requires entitlements; returns None if unavailable."""
    try:
        contract = Stock(symbol, 'SMART', 'USD')
        xml = ib.reqFundamentalData(contract, reportType='ReportSnapshot')
        if not xml:
            return None
        # Parse XML; look for MarketCap fields
        root = ET.fromstring(xml)
        # Common tags vary; scan for any element containing 'MarketCap'
        caps: List[float] = []
        for elem in root.iter():
            tag = (elem.tag or '').lower()
            if 'marketcap' in tag or 'mktcap' in tag:
                try:
                    val = str(elem.text or '').replace(',', '').strip()
                    if val and val.replace('.', '', 1).isdigit():
                        caps.append(float(val))
                except Exception:
                    continue
        if len(caps) == 0:
            # Some XML embed value as attribute
            for elem in root.iter():
                for k, v in (elem.attrib or {}).items():
                    if 'marketcap' in k.lower() or 'mktcap' in k.lower():
                        try:
                            val = str(v).replace(',', '').strip()
                            if val and val.replace('.', '', 1).isdigit():
                                caps.append(float(val))
                        except Exception:
                            continue
        return caps[0] if caps else None
    except Exception:
        return None


def fetch_ibkr_core(
    scan_type: str,
    port: int,
    limit: int,
    wait_sec: float = 1.0,
    use_fundamentals: bool = False,
    use_hist: bool = False,
) -> pd.DataFrame:
    ib = IB()
    ib.connect('127.0.0.1', port, clientId=1001, readonly=True, timeout=20)
    print(f"✓ Connected to IBKR on port {port}")
    # Prefer real-time for live TWS (7496); delayed for paper (7497)
    _set_market_data_type(ib, prefer_delayed=(port != 7496))

    # Scanner
    location = 'STK.US.MAJOR'
    scan = ScannerSubscription(
        instrument='STK',
        locationCode=location,
        scanCode=SCANNER_CODES.get(scan_type, 'TOP_PERC_GAIN'),
        numberOfRows=limit,
    )
    print(f"Requesting {scan_type} scanner at {location}...")
    items = ib.reqScannerData(scan)
    ib.sleep(1.0)
    if not items:
        print("✗ Scanner returned no results")
        return pd.DataFrame()
    print(f"✓ Found {len(items)} stocks")

    rows = []
    for idx, d in enumerate(items, 1):
        c = d.contractDetails.contract
        # Request default market data for volume; request generic ticks separately
        ticker = None
        gen = None
        try:
            ticker = ib.reqMktData(c, '', False, False)
            waited = 0.0
            while waited < wait_sec and (ticker.volume is None):
                ib.sleep(0.2)
                waited += 0.2
        except Exception:
            ticker = None
        finally:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass

        try:
            gen = ib.reqMktData(c, '236,294,295', False, False)
            waited = 0.0
            while waited < wait_sec:
                if any([
                    hasattr(gen, 'shortableShares') and gen.shortableShares is not None,
                    hasattr(gen, 'tradeRate') and gen.tradeRate is not None,
                    hasattr(gen, 'volumeRate') and gen.volumeRate is not None,
                ]):
                    break
                ib.sleep(0.2)
                waited += 0.2
        except Exception:
            gen = None
        finally:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass

        # Historical-based estimate for volume/min (IBKR-only, optional)
        vol_per_min = None
        if use_hist:
            try:
                bars = ib.reqHistoricalData(
                    c,
                    endDateTime='',
                    durationStr='5 M',
                    barSizeSetting='1 min',
                    whatToShow='TRADES',
                    useRTH=False,
                    formatDate=1,
                )
                if bars:
                    vol_per_min = sum(b.volume for b in bars) / max(1, len(bars))
            except Exception:
                vol_per_min = None

        # Attempt market cap via fundamentals (optional)
        mktcap = _fetch_market_cap(ib, c.symbol) if use_fundamentals else None

        row = {
            'rank': idx,
            'symbol': c.symbol,
            'description': d.contractDetails.longName if hasattr(d.contractDetails, 'longName') else '',
            'volume': getattr(ticker, 'volume', None) if ticker else None,
            'market_cap': mktcap,
            'shortable_shares': getattr(gen, 'shortableShares', None) if gen and hasattr(gen, 'shortableShares') else None,
            'trade_rate': getattr(gen, 'tradeRate', None) if gen and hasattr(gen, 'tradeRate') else None,
            'volume_rate': (getattr(gen, 'volumeRate', None) if gen and hasattr(gen, 'volumeRate') else vol_per_min),
        }
        rows.append(row)

        if idx % 10 == 0:
            print(f"  Processed {idx}/{len(items)}")

    ib.disconnect()
    df = pd.DataFrame(rows)
    return df


def main():
    parser = argparse.ArgumentParser(description='IBKR-only core metrics fetcher')
    parser.add_argument('--scan-type', default='top_gainers', choices=list(SCANNER_CODES.keys()))
    parser.add_argument('--port', type=int, default=7497)
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--output', type=str, default='../output/ibkr_core_metrics.csv')
    parser.add_argument('--wait-sec', type=float, default=1.0, help='Max seconds to wait per symbol for IBKR ticks')
    parser.add_argument('--no-fundamentals', action='store_true', help='Skip IBKR fundamentals (market cap)')
    parser.add_argument('--no-hist', action='store_true', help='Skip IBKR historical bars for volume/min estimate')
    args = parser.parse_args()

    df = fetch_ibkr_core(
        args.scan_type,
        args.port,
        args.limit,
        wait_sec=max(0.2, args.wait_sec),
        use_fundamentals=not args.no_fundamentals,
        use_hist=not args.no_hist,
    )
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\n✓ Saved {len(df)} rows to {args.output}")
    if len(df) > 0:
        print(df[['rank','symbol','description','volume','market_cap','shortable_shares','trade_rate','volume_rate']].head(10).to_string(index=False))


if __name__ == '__main__':
    main()
