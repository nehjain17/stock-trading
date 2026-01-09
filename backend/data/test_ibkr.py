#!/usr/bin/env python3
"""
test_ibkr.py

Fixes:
- Shortable inconsistent -> batch reqMktData for ALL, wait once, then cancel ALL
- VWAP inconsistent -> compute from 5-min TRADES bars (30m + 5m) with typical-price fallback
- Always writes Shortable columns even if all None
- Adds Vol(1m) + Trades(1m)
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from ib_insync import IB, ScannerSubscription, Stock


SCANNER_CODES = {
    "top_gainers": "TOP_PERC_GAIN",
    "top_losers": "TOP_PERC_LOSE",
    "most_active": "MOST_ACTIVE",
    "top_volume": "HOT_BY_VOLUME",
    "top_trade_rate": "TOP_VOLUME_RATE",
}


# ---------------------------
# Indicators
# ---------------------------
def ema(arr: np.ndarray, span: int) -> np.ndarray:
    if arr is None or len(arr) == 0:
        return np.array([], dtype=float)
    alpha = 2.0 / (span + 1.0)
    out = np.empty(len(arr), dtype=float)
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


def normalize_symbol(x) -> str:
    if x is None:
        return ""
    return str(x).strip().upper()


def parse_duration_to_ib(duration: str) -> str:
    """
    IB durationStr supports: '<int> S|D|W|M|Y'
    NOTE: 'M' = months. Minutes must be seconds.
    """
    s = (duration or "").strip()
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
    if bar_date is None:
        return None

    if isinstance(bar_date, datetime):
        dt = bar_date
    else:
        s = str(bar_date).strip()
        dt = None
        for fmt in ("%Y%m%d %H:%M:%S", "%Y%m%d  %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                pass
        if dt is None:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(timezone.utc)


def typical_price(bar) -> Optional[float]:
    h = safe_float(getattr(bar, "high", None))
    l = safe_float(getattr(bar, "low", None))
    c = safe_float(getattr(bar, "close", None))
    if h is None or l is None or c is None:
        return c
    return (h + l + c) / 3.0


def vwap_of_bars(bars: List) -> Optional[float]:
    num = 0.0
    den = 0.0
    for b in bars:
        v = getattr(b, "volume", 0) or 0
        if not v:
            continue
        w = safe_float(getattr(b, "wap", None))
        if w is None:
            w = typical_price(b)
        if w is None:
            continue
        num += float(w) * float(v)
        den += float(v)
    if den <= 0:
        return None
    return num / den


# ---------------------------
# IBKR ops
# ---------------------------
def connect_ib(host: str, port: int, client_id: int, timeout: float, market_data_type: int) -> IB:
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    try:
        ib.reqMarketDataType(market_data_type)
    except Exception:
        pass
    return ib


def scan_contracts(ib: IB, scanner: str, rows: int, location: str) -> List[Stock]:
    sub = ScannerSubscription(
        instrument="STK",
        locationCode=location,
        scanCode=SCANNER_CODES[scanner],
        numberOfRows=rows,
    )
    scan_data = ib.reqScannerSubscription(sub, [], [])
    ib.sleep(2.0)

    contracts: List[Stock] = []
    for row in list(scan_data):
        cd = getattr(row, "contractDetails", None)
        c = getattr(cd, "contract", None) if cd is not None else None
        if c is not None:
            if getattr(c, "exchange", None) in (None, "", "SMART"):
                c.exchange = "SMART"
            contracts.append(c)

    try:
        ib.cancelScannerSubscription(scan_data)
    except Exception:
        pass

    if contracts:
        ib.qualifyContracts(*contracts)
    return contracts


def fetch_snapshot_prices(ib: IB, contracts: List[Stock], batch_size: int = 10) -> Dict[int, Dict[str, Optional[float]]]:
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

        ib.sleep(0.4)

        for t in tickers:
            c = t.contract
            con_id = getattr(c, "conId", None)
            if not con_id:
                continue

            mp = safe_float(t.marketPrice())
            last = safe_float(getattr(t, "last", None))
            close = safe_float(getattr(t, "close", None))
            prev_close = safe_float(getattr(t, "prevClose", None)) or close

            last_final = last if last is not None else (mp if mp is not None else close)

            pct_change = None
            if last_final is not None and prev_close not in (None, 0):
                pct_change = (last_final - prev_close) / prev_close * 100.0

            out[con_id] = {"last": last_final, "prev_close": prev_close, "pct_change": pct_change}
    return out


def fetch_shortable_shares_batch(ib: IB, contracts: List[Stock], wait_s: float = 2.5) -> Dict[int, Optional[int]]:
    """
    MUCH more consistent:
      - subscribe mktdata for all with genericTick 236
      - wait once
      - read shortableShares
      - cancel all
    """
    out: Dict[int, Optional[int]] = {}

    tickers = []
    for c in contracts:
        con_id = getattr(c, "conId", None)
        if con_id:
            out[con_id] = None

        try:
            t = ib.reqMktData(c, genericTickList="236", snapshot=False, regulatorySnapshot=False)
            tickers.append(t)
        except Exception:
            continue

    # wait for updates to arrive
    t0 = time.time()
    while time.time() - t0 < wait_s:
        got_any = False
        for t in tickers:
            c = getattr(t, "contract", None)
            con_id = getattr(c, "conId", None) if c else None
            if not con_id:
                continue
            v = getattr(t, "shortableShares", None)
            if v is not None:
                out[con_id] = safe_int(v)
                got_any = True
        if got_any:
            # keep waiting a bit for more symbols
            ib.sleep(0.15)
        else:
            ib.sleep(0.10)

    # cancel all subscriptions
    for c in contracts:
        try:
            ib.cancelMktData(c)
        except Exception:
            pass

    return out


def fetch_hist_bars(ib: IB, contract: Stock, duration: str, bar_size: str, what: str, use_rth: int) -> List:
    return ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what,
        useRTH=use_rth,
        formatDate=1,
        keepUpToDate=False,
    )


def compute_windows_from_1m(bars_1m: List, stale_seconds: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    if not bars_1m:
        for n in (1, 3, 5, 10, 15):
            out[f"vol_{n}m"] = 0
            out[f"trades_{n}m"] = 0
        out["last_bar_age_s"] = None
        out["last_bar_time"] = None
        return out

    last_dt = to_utc_datetime(getattr(bars_1m[-1], "date", None))
    last_age = None
    if last_dt is not None:
        last_age = int((now_utc() - last_dt).total_seconds())
        if last_age < 0:
            last_age = 0

    out["last_bar_time"] = last_dt.isoformat() if last_dt else None
    out["last_bar_age_s"] = last_age

    if last_age is not None and last_age > stale_seconds:
        for n in (1, 3, 5, 10, 15):
            out[f"vol_{n}m"] = 0
            out[f"trades_{n}m"] = 0
        return out

    def last_n(n: int) -> List:
        return bars_1m[-n:] if len(bars_1m) >= n else bars_1m

    for n in (1, 3, 5, 10, 15):
        b = last_n(n)
        out[f"vol_{n}m"] = int(sum((getattr(x, "volume", 0) or 0) for x in b))
        out[f"trades_{n}m"] = int(sum((getattr(x, "barCount", 0) or 0) for x in b))

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
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--location", default="STK.US.MAJOR")
    ap.add_argument("--use-rth", type=int, default=0, choices=[0, 1])

    ap.add_argument("--window", default="4 H", help="history for 1-min TRADES bars")
    ap.add_argument("--stale-seconds", type=int, default=240)

    ap.add_argument("--indicator-window", default="5 D")
    ap.add_argument("--indicator-what", default="MIDPOINT", choices=["MIDPOINT", "TRADES"])

    ap.add_argument("--market-data-type", type=int, default=1, choices=[1, 2, 3, 4])
    ap.add_argument("--out", default="", help="output csv")
    args = ap.parse_args()

    out_path = args.out.strip() or os.path.join(".", f"ibkr_data_{args.scanner}.csv")
    window_duration = parse_duration_to_ib(args.window)
    ind_duration = parse_duration_to_ib(args.indicator_window)

    print(f"→ Scanner={args.scanner} limit={args.limit} useRTH={args.use_rth}")
    print(f"→ 1m duration: {args.window} -> {window_duration}")
    print(f"→ indicator duration: {args.indicator_window} -> {ind_duration} (what={args.indicator_what})")
    print(f"→ output: {out_path}")

    ib = connect_ib(args.host, args.port, args.client_id, args.timeout, args.market_data_type)

    try:
        contracts = scan_contracts(ib, args.scanner, rows=args.limit, location=args.location)
        if not contracts:
            print("No scanner results.")
            sys.exit(1)

        price_map = fetch_snapshot_prices(ib, contracts, batch_size=10)

        # ✅ fixed: batch shortable
        short_map = fetch_shortable_shares_batch(ib, contracts, wait_s=2.5)

        rows: List[Dict[str, Any]] = []
        print(f"→ Fetching historical bars for {len(contracts)} symbols")

        for i, c in enumerate(contracts, 1):
            if i % 10 == 0 or i == len(contracts):
                print(f"  progress {i}/{len(contracts)}")

            con_id = getattr(c, "conId", None)
            sym = normalize_symbol(getattr(c, "symbol", ""))

            p = price_map.get(con_id, {}) if con_id else {}
            last = safe_float(p.get("last"))
            prev_close = safe_float(p.get("prev_close"))
            pct_change = safe_float(p.get("pct_change"))

            shortable_shares = short_map.get(con_id) if con_id else None

            # 1m windows
            try:
                bars_1m = fetch_hist_bars(ib, c, duration=window_duration, bar_size="1 min", what="TRADES", use_rth=args.use_rth)
            except Exception:
                bars_1m = []
            wm = compute_windows_from_1m(bars_1m, stale_seconds=args.stale_seconds)

            # 30m volume for RelVol
            vol_30m = None
            if bars_1m and (wm.get("last_bar_age_s") is None or wm.get("last_bar_age_s") <= args.stale_seconds):
                last_30 = bars_1m[-30:] if len(bars_1m) >= 30 else bars_1m
                vol_30m = float(sum((getattr(x, "volume", 0) or 0) for x in last_30))
            relvol = relvol_5m_vs_30m(safe_float(wm.get("vol_5m")), vol_30m)

            # ✅ stable VWAP from 5m TRADES bars
            vwap_5m = None
            vwap_30m = None
            try:
                bars_5m_trades = fetch_hist_bars(ib, c, duration="1800 S", bar_size="5 mins", what="TRADES", use_rth=args.use_rth)
                if bars_5m_trades:
                    # last 1 bar = last 5 minutes
                    vwap_5m = vwap_of_bars(bars_5m_trades[-1:])
                    # all bars in 30m window
                    vwap_30m = vwap_of_bars(bars_5m_trades)
            except Exception:
                pass

            vwap5_dist = vwap_dist(last, vwap_5m)
            vwap30_dist = vwap_dist(last, vwap_30m)

            # indicators
            rsi14 = None
            macd_line = None
            macd_sig = None
            macd_hist = None
            try:
                bars_5m = fetch_hist_bars(ib, c, duration=ind_duration, bar_size="5 mins", what=args.indicator_what, use_rth=args.use_rth)
                closes = np.array([float(b.close) for b in bars_5m if getattr(b, "close", None) is not None], dtype=float)
                if len(closes) >= 40:
                    rsi14 = rsi(closes, 14)
                    macd_line, macd_sig, macd_hist = macd(closes)
            except Exception:
                pass

            row = {
                # backend fields
                "symbol": sym,
                "last": last,
                "prev_close": prev_close,
                "pct_change": pct_change,
                "relvol": safe_float(relvol),

                "vol_1m": safe_int(wm.get("vol_1m")),
                "vol_3m": safe_int(wm.get("vol_3m")),
                "vol_5m": safe_int(wm.get("vol_5m")),
                "vol_10m": safe_int(wm.get("vol_10m")),
                "vol_15m": safe_int(wm.get("vol_15m")),

                "trades_1m": safe_int(wm.get("trades_1m")),
                "trades_5m": safe_int(wm.get("trades_5m")),
                "trades_10m": safe_int(wm.get("trades_10m")),
                "trades_15m": safe_int(wm.get("trades_15m")),

                "shortable_shares": safe_int(shortable_shares),

                "rsi14": safe_float(rsi14),
                "macd": safe_float(macd_line),
                "macd_signal": safe_float(macd_sig),
                "macd_hist": safe_float(macd_hist),

                "vwap_5m": safe_float(vwap_5m),
                "vwap_30m": safe_float(vwap_30m),
                "vwap5_dist": safe_float(vwap5_dist),
                "vwap30_dist": safe_float(vwap30_dist),

                "last_bar_time": wm.get("last_bar_time"),
                "last_bar_age_s": safe_int(wm.get("last_bar_age_s")),
            }

            # UI aliases
            row.update({
                "Symbol": sym,
                "Last": row["last"],
                "%Chg": row["pct_change"],
                "RelVol": row["relvol"],

                "Vol(1m)": row["vol_1m"],
                "Vol(3m)": row["vol_3m"],
                "Vol(5m)": row["vol_5m"],
                "Vol(10m)": row["vol_10m"],
                "Vol(15m)": row["vol_15m"],

                "Trades(1m)": row["trades_1m"],
                "Trades(5m)": row["trades_5m"],
                "Trades(10m)": row["trades_10m"],
                "Trades(15m)": row["trades_15m"],

                # ✅ always present
                "Shortable": row["shortable_shares"],

                "RSI(14)": row["rsi14"],
                "MACD": row["macd"],
                "MACD Sig": row["macd_signal"],
                "MACD Hist": row["macd_hist"],

                "VWAP5 Dist": row["vwap5_dist"],
                "VWAP30 Dist": row["vwap30_dist"],
                "VWAP(30m)": row["vwap_30m"],
            })

            rows.append(row)

        df = pd.DataFrame(rows)

        # keep consistent columns even if all empty
        ordered_cols = [
            "symbol", "last", "prev_close", "pct_change", "relvol",
            "vol_1m", "vol_3m", "vol_5m", "vol_10m", "vol_15m",
            "trades_1m", "trades_5m", "trades_10m", "trades_15m",
            "shortable_shares",
            "rsi14", "macd", "macd_signal", "macd_hist",
            "vwap_5m", "vwap_30m", "vwap5_dist", "vwap30_dist",
            "last_bar_time", "last_bar_age_s",

            "Symbol", "Last", "%Chg", "RelVol",
            "Vol(1m)", "Vol(3m)", "Vol(5m)", "Vol(10m)", "Vol(15m)",
            "Trades(1m)", "Trades(5m)", "Trades(10m)", "Trades(15m)",
            "Shortable",
            "RSI(14)", "MACD", "MACD Sig", "MACD Hist",
            "VWAP5 Dist", "VWAP30 Dist", "VWAP(30m)",
        ]
        for c in ordered_cols:
            if c not in df.columns:
                df[c] = None
        df = df[ordered_cols]

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
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
