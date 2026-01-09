#!/usr/bin/env python3
"""
IBKR Scanner -> CSV + UI-friendly columns

Outputs columns your UI expects (snake_case header names shown in your CSV):
symbol,last,pct_chg,rel_vol,
vol_1m,vol_3m,vol_5m,vol_10m,vol_15m,
trades_1m,trades_5m,trades_10m,trades_15m,
shortable_shares,
rsi_14,macd,macd_sig,macd_hist,
vwap_5m,vwap_30m,vwap5_dist,vwap30_dist,
_lastBarAgeSec,_prevClose

ONLY FIX THIS TIME:
- Remove cancel* calls that trigger TWS "Read-Only API" write-access warning.
  (cancelScannerSubscription / cancelMktData are treated as "write" by TWS)
  We rely on ib.disconnect() to clean up.
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from ib_insync import IB, ScannerSubscription, Stock


SCANNER_CODES = {
    "top_gainers": "TOP_PERC_GAIN",
    "top_losers": "TOP_PERC_LOSE",
    "most_active": "MOST_ACTIVE",
    "hot_by_volume": "HOT_BY_VOLUME",
    "top_volume_rate": "TOP_VOLUME_RATE",
}


# ---------------------------
# Indicators
# ---------------------------

def ema(arr: np.ndarray, span: int) -> np.ndarray:
    if len(arr) == 0:
        return arr
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(arr, dtype=float)
    out[0] = float(arr[0])
    for i in range(1, len(arr)):
        out[i] = alpha * float(arr[i]) + (1.0 - alpha) * out[i - 1]
    return out


def rsi(series: np.ndarray, period: int = 14) -> Optional[float]:
    if series is None or len(series) < period + 1:
        return None
    deltas = np.diff(series.astype(float))
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    if avg_loss == 0:
        return 100.0

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def macd(series: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if series is None or len(series) < slow + signal + 5:
        return (None, None, None)
    series = series.astype(float)
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return (float(macd_line[-1]), float(signal_line[-1]), float(hist[-1]))


# ---------------------------
# Helpers
# ---------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_tz():
    return datetime.now().astimezone().tzinfo


def safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def safe_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        return int(x)
    except Exception:
        return None


def parse_duration_to_ib(duration: str) -> str:
    """
    IB durationStr: "60 S", "1 D", "2 W", "1 M"(month!), "1 Y"
    If user gives "30m" => 1800 S.
    """
    s = duration.strip()
    if not s:
        return "1 D"

    parts = s.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1] in ("S", "D", "W", "M", "Y"):
        return s

    s_low = s.lower().replace(" ", "")
    if s_low.endswith("s") and s_low[:-1].isdigit():
        return f"{int(s_low[:-1])} S"
    if s_low.endswith("m") and s_low[:-1].isdigit():
        return f"{int(s_low[:-1]) * 60} S"
    if s_low.endswith("h") and s_low[:-1].isdigit():
        return f"{int(s_low[:-1]) * 3600} S"
    if s_low.endswith("d") and s_low[:-1].isdigit():
        return f"{int(s_low[:-1])} D"

    return "1 D"


def to_utc_datetime(bar_date) -> Optional[datetime]:
    """
    ib_insync bar.date can be datetime or string.
    If naive => treat as LOCAL, then convert to UTC.
    """
    if bar_date is None:
        return None

    if isinstance(bar_date, datetime):
        dt = bar_date
    else:
        try:
            s = str(bar_date).replace("  ", " ").strip()
            dt = datetime.strptime(s, "%Y%m%d %H:%M:%S")
        except Exception:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())

    return dt.astimezone(timezone.utc)


def bar_typical_price(b) -> Optional[float]:
    h = safe_float(getattr(b, "high", None))
    l = safe_float(getattr(b, "low", None))
    c = safe_float(getattr(b, "close", None))
    if h is None or l is None or c is None:
        return None
    return (h + l + c) / 3.0


# ---------------------------
# IBKR
# ---------------------------

def connect_ib(host: str, port: int, client_id: int, timeout: float, market_data_type: int) -> IB:
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    try:
        ib.reqMarketDataType(market_data_type)  # 1 live, 2 frozen, 3 delayed, 4 delayed-frozen
    except Exception:
        pass
    return ib


def scan_symbols(ib: IB, scanner_code: str, rows: int, location: str) -> List[Stock]:
    sub = ScannerSubscription(
        instrument="STK",
        locationCode=location,
        scanCode=scanner_code,
        numberOfRows=rows,
    )
    scan_list = ib.reqScannerSubscription(sub, [], [])
    ib.sleep(1.5)

    contracts: List[Stock] = []
    for row in list(scan_list):
        cd = getattr(row, "contractDetails", None)
        if cd and getattr(cd, "contract", None):
            c = cd.contract
            if getattr(c, "exchange", None) in (None, "", "SMART"):
                c.exchange = "SMART"
            contracts.append(c)

    # ONLY CHANGE: do NOT cancel scanner subscription here (triggers write-access warning in Read-Only API)
    # Cleanup will happen at ib.disconnect()

    if contracts:
        ib.qualifyContracts(*contracts)
    return contracts


def fetch_snapshot_prices(ib: IB, contracts: List[Stock], batch_size: int = 25) -> Dict[int, Dict[str, Optional[float]]]:
    out: Dict[int, Dict[str, Optional[float]]] = {}
    if not contracts:
        return out

    batches = [contracts[i:i + batch_size] for i in range(0, len(contracts), batch_size)]
    for bi, batch in enumerate(batches, 1):
        print(f"→ Snapshot(price) batch {bi}/{len(batches)} ({len(batch)} symbols)")
        try:
            tickers = ib.reqTickers(*batch)
        except Exception as e:
            print(f"  snapshot batch failed: {e}")
            continue

        ib.sleep(0.25)

        for t in tickers:
            c = t.contract
            con_id = getattr(c, "conId", None)
            if not con_id:
                continue

            last = safe_float(getattr(t, "last", None))
            mp = safe_float(t.marketPrice())
            close = safe_float(getattr(t, "close", None))
            prev_close = safe_float(getattr(t, "prevClose", None)) or close

            last_final = last if last is not None else (mp if mp is not None else close)

            pct_change = None
            if last_final is not None and prev_close not in (None, 0):
                pct_change = (last_final - prev_close) / prev_close * 100.0

            out[con_id] = {"last": last_final, "prev_close": prev_close, "pct_change": pct_change}
    return out


def fetch_shortable_shares_batch(
    ib: IB,
    contracts: List[Stock],
    timeout_s: float = 4.0,
    target_fill_ratio: float = 0.70,
) -> Dict[int, Optional[int]]:
    out: Dict[int, Optional[int]] = {}
    tickers = []

    for c in contracts:
        con_id = getattr(c, "conId", None)
        if con_id:
            out[con_id] = None

    for c in contracts:
        try:
            t = ib.reqMktData(
                c,
                genericTickList="236",
                snapshot=False,
                regulatorySnapshot=False,
            )
            tickers.append(t)
            ib.sleep(0.02)
        except Exception:
            continue

    t0 = time.time()
    total = len(out) if out else 0

    while time.time() - t0 < timeout_s:
        filled = 0
        for t in tickers:
            c = getattr(t, "contract", None)
            con_id = getattr(c, "conId", None)
            if not con_id:
                continue
            v = getattr(t, "shortableShares", None)
            if v is not None:
                out[con_id] = safe_int(v)
                if out[con_id] is not None:
                    filled += 1

        if total > 0 and filled >= int(target_fill_ratio * total):
            break
        ib.sleep(0.05)

    # ONLY CHANGE: do NOT cancel market data here (triggers write-access warning in Read-Only API)
    # Cleanup will happen at ib.disconnect()

    return out


def fetch_1m_bars(ib: IB, contract: Stock, duration: str, use_rth: int) -> List:
    return ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=use_rth,
        formatDate=1,
        keepUpToDate=False,
    )


def fetch_5m_bars(ib: IB, contract: Stock, duration: str, use_rth: int) -> List:
    return ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=use_rth,
        formatDate=1,
        keepUpToDate=False,
    )


def compute_windows_with_stale_guard(bars_1m: List, stale_seconds: int) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}

    for n in (1, 3, 5, 10, 15):
        out[f"vol_{n}m"] = 0.0
    for n in (1, 5, 10, 15):
        out[f"trades_{n}m"] = 0.0
    out["vwap_5m"] = None
    out["vwap_30m"] = None
    out["last_bar_age_s"] = None

    if not bars_1m:
        return out

    last_dt = to_utc_datetime(getattr(bars_1m[-1], "date", None))
    last_age = None
    if last_dt is not None:
        last_dt_end = last_dt + timedelta(seconds=60)
        last_age = int((now_utc() - last_dt_end).total_seconds())
        if last_age < 0:
            last_age = 0

    out["last_bar_age_s"] = last_age

    if last_age is not None and last_age > stale_seconds:
        return out

    def last_n(n: int) -> List:
        return bars_1m[-n:] if len(bars_1m) >= n else bars_1m

    for n in (1, 3, 5, 10, 15):
        b = last_n(n)
        out[f"vol_{n}m"] = float(sum((getattr(x, "volume", 0) or 0) for x in b))

    for n in (1, 5, 10, 15):
        b = last_n(n)
        out[f"trades_{n}m"] = float(sum((getattr(x, "barCount", 0) or 0) for x in b))

    def vwap_last(n: int) -> Optional[float]:
        b = last_n(n)
        num = 0.0
        den = 0.0
        for x in b:
            v = getattr(x, "volume", 0) or 0
            if not v:
                continue
            w = safe_float(getattr(x, "wap", None))
            if w is None:
                w = bar_typical_price(x)
            if w is None:
                continue
            num += float(w) * float(v)
            den += float(v)
        if den == 0:
            return None
        return num / den

    out["vwap_5m"] = vwap_last(5)
    out["vwap_30m"] = vwap_last(30)
    return out


def relvol_5m_vs_30m(vol_5m: Optional[float], vol_30m: Optional[float]) -> Optional[float]:
    if vol_5m is None or vol_30m is None or vol_30m <= 0:
        return None
    avg5 = vol_30m / 6.0
    if avg5 <= 0:
        return None
    return float(vol_5m / avg5)


def vwap_dist(last: Optional[float], vwap: Optional[float]) -> Optional[float]:
    if last is None or vwap is None or vwap == 0:
        return None
    return float((last - vwap) / vwap)


# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7496)
    ap.add_argument("--client-id", type=int, default=19)
    ap.add_argument("--timeout", type=float, default=8.0)

    ap.add_argument("--scanner", default="top_gainers", choices=sorted(SCANNER_CODES.keys()))
    ap.add_argument("--rows", type=int, default=50)
    ap.add_argument("--location", default="STK.US.MAJOR")
    ap.add_argument("--use-rth", type=int, default=0, choices=[0, 1])

    ap.add_argument("--window", default="4 H", help="history for 1-min bars, e.g. '4 H', '30m'")
    ap.add_argument("--indicator-window", default="3 D", help="history for RSI/MACD from 5-min bars (needs enough bars)")
    ap.add_argument("--stale-seconds", type=int, default=150, help="if last 1m bar older than this, set windows to 0")

    ap.add_argument("--market-data-type", type=int, default=1, choices=[1, 2, 3, 4])
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    scanner_code = SCANNER_CODES[args.scanner]
    window_duration = parse_duration_to_ib(args.window)
    indicator_duration = parse_duration_to_ib(args.indicator_window)

    print(f"→ Scanner '{args.scanner}' ({scanner_code}), rows={args.rows}, location={args.location}")
    print(f"→ 1m window duration '{args.window}' -> '{window_duration}'")
    print(f"→ Indicator duration '{args.indicator_window}' -> '{indicator_duration}'")
    print(f"→ Stale cutoff: {args.stale_seconds}s (older bars => windows=0)")

    ib = connect_ib(args.host, args.port, args.client_id, args.timeout, args.market_data_type)

    try:
        contracts = scan_symbols(ib, scanner_code=scanner_code, rows=args.rows, location=args.location)
        if not contracts:
            print("No scanner results. Check TWS market subscriptions + scanner permissions.")
            sys.exit(1)

        price_map = fetch_snapshot_prices(ib, contracts, batch_size=25)

        print(f"→ Streaming shortableShares (generic tick 236) for {len(contracts)} symbols")
        short_map = fetch_shortable_shares_batch(ib, contracts, timeout_s=4.0, target_fill_ratio=0.70)

        out_rows = []
        print(f"→ Historical fetch for {len(contracts)} symbols")

        for i, c in enumerate(contracts, 1):
            if i % 10 == 0 or i == len(contracts):
                print(f"  progress: {i}/{len(contracts)}")

            con_id = getattr(c, "conId", None)
            sym = getattr(c, "symbol", None)

            p = price_map.get(con_id, {}) if con_id else {}
            last = p.get("last")
            pct = p.get("pct_change")
            prev_close = p.get("prev_close")

            shortable = short_map.get(con_id) if con_id else None

            try:
                bars_1m = fetch_1m_bars(ib, c, duration=window_duration, use_rth=args.use_rth)
            except Exception:
                bars_1m = []

            wm = compute_windows_with_stale_guard(bars_1m, stale_seconds=args.stale_seconds)

            vol_30m = None
            if bars_1m and (wm.get("last_bar_age_s") is None or wm.get("last_bar_age_s") <= args.stale_seconds):
                last_30 = bars_1m[-30:] if len(bars_1m) >= 30 else bars_1m
                vol_30m = float(sum((getattr(x, "volume", 0) or 0) for x in last_30))
            relvol = relvol_5m_vs_30m(wm.get("vol_5m"), vol_30m)

            vwap5 = wm.get("vwap_5m")
            vwap30 = wm.get("vwap_30m")
            vwap5d = vwap_dist(last, vwap5)
            vwap30d = vwap_dist(last, vwap30)

            # RSI fix retained
            rsi14 = None
            m_line = None
            m_sig = None
            m_hist = None
            try:
                bars_5m = fetch_5m_bars(ib, c, duration=indicator_duration, use_rth=args.use_rth)
                closes = np.array([float(b.close) for b in bars_5m if getattr(b, "close", None) is not None], dtype=float)

                if len(closes) >= 15:
                    rsi14 = rsi(closes, 14)

                if len(closes) >= 60:
                    m_line, m_sig, m_hist = macd(closes)
            except Exception:
                pass

            out_rows.append({
                "symbol": sym,
                "last": safe_float(last),
                "pct_chg": safe_float(pct),
                "rel_vol": safe_float(relvol),

                "vol_1m": safe_float(wm.get("vol_1m")),
                "vol_3m": safe_float(wm.get("vol_3m")),
                "vol_5m": safe_float(wm.get("vol_5m")),
                "vol_10m": safe_float(wm.get("vol_10m")),
                "vol_15m": safe_float(wm.get("vol_15m")),

                "trades_1m": safe_float(wm.get("trades_1m")),
                "trades_5m": safe_float(wm.get("trades_5m")),
                "trades_10m": safe_float(wm.get("trades_10m")),
                "trades_15m": safe_float(wm.get("trades_15m")),

                "shortable_shares": safe_int(shortable),

                "rsi_14": safe_float(rsi14),
                "macd": safe_float(m_line),
                "macd_sig": safe_float(m_sig),
                "macd_hist": safe_float(m_hist),

                "vwap_5m": safe_float(vwap5),
                "vwap_30m": safe_float(vwap30),
                "vwap5_dist": safe_float(vwap5d),
                "vwap30_dist": safe_float(vwap30d),

                "_lastBarAgeSec": safe_int(wm.get("last_bar_age_s")),
                "_prevClose": safe_float(prev_close),
            })

        df = pd.DataFrame(out_rows)

        cols = [
            "symbol", "last", "pct_chg", "rel_vol",
            "vol_1m", "vol_3m", "vol_5m", "vol_10m", "vol_15m",
            "trades_1m", "trades_5m", "trades_10m", "trades_15m",
            "shortable_shares",
            "rsi_14", "macd", "macd_sig", "macd_hist",
            "vwap_5m", "vwap_30m", "vwap5_dist", "vwap30_dist",
            "_lastBarAgeSec", "_prevClose",
        ]
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]

        os.makedirs(args.outdir, exist_ok=True)
        out_path = os.path.join(args.outdir, f"ibkr_data_{args.scanner}.csv")
        df.to_csv(out_path, index=False)
        print(f"\n✓ Saved {len(df)} rows -> {out_path}\n")
        print(df.head(12).to_string(index=False))

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
