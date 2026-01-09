#!/usr/bin/env python3
"""
IBKR Scanner -> historical bars -> RSI/MACD/RelVol -> CSV (FAST, loop-safe)

Works with older ib_insync versions:
- No util.sleepAsync
- No IB.sleepAsync
- Uses asyncio.sleep for pacing/yields

Rules:
- In async code, DO NOT call sync ib_insync methods like:
  ib.reqScannerData(), ib.reqHistoricalData(), ib.sleep()
  (they call util.run() and can trigger nested-loop errors)

Use:
- await ib.connectAsync()
- await ib.reqScannerDataAsync()
- await ib.reqHistoricalDataAsync()
- await asyncio.sleep()

Example:
  python3 ibkr_indicators.py --scanner top_gainers --limit 50 --lookback-days 10 \
    --out ibkr_indicators_top_gainers.csv
"""

import argparse
import asyncio
import os
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, ScannerSubscription


SCANNER_CODES = {
    "top_gainers": "TOP_PERC_GAIN",
    "top_losers": "TOP_PERC_LOSE",
    "most_active": "MOST_ACTIVE",
    "hot_by_volume": "HOT_BY_VOLUME",
    "top_volume": "TOP_VOLUME",
    "hot_by_price": "HOT_BY_PRICE",
    "top_trade_rate": "TOP_TRADE_RATE",
}


@dataclass
class BarsCfg:
    bar_size: str
    duration: str
    use_rth: bool
    what_to_show: str = "TRADES"


def _norm_sym(s: str) -> str:
    return str(s or "").strip().upper()


async def fetch_scanner_symbols_async(ib: IB, scan_code: str, location: str, limit: int) -> List[str]:
    scan = ScannerSubscription(
        instrument="STK",
        locationCode=location,
        scanCode=scan_code,
        numberOfRows=limit,
    )

    items = await ib.reqScannerDataAsync(scan)

    # tiny yield/pacing without relying on util.sleepAsync
    await asyncio.sleep(0.2)

    out: List[str] = []
    for d in (items or [])[:limit]:
        cd = d.contractDetails
        out.append(_norm_sym(cd.contract.symbol))

    # de-dupe, preserve order
    seen = set()
    uniq: List[str] = []
    for s in out:
        if not s or s in seen:
            continue
        uniq.append(s)
        seen.add(s)
    return uniq


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bars_to_df(bars) -> Optional[pd.DataFrame]:
    if not bars:
        return None
    df = pd.DataFrame(
        [{
            "time": b.date,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        } for b in bars]
    )
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df if not df.empty else None


def relvol_from_last_30m_bar(df_30m: pd.DataFrame, lookback_days: int) -> Optional[float]:
    """
    RelVol = today's last 30-min bar volume / avg(prior days last 30-min bar volume)
    """
    if df_30m is None or df_30m.empty:
        return None

    df = df_30m.copy()
    df["date"] = df["time"].dt.date
    days = sorted(df["date"].unique())
    if len(days) < 2:
        return None

    today = days[-1]
    prev_days = days[-(lookback_days + 1):-1]
    if not prev_days:
        return None

    df_today = df[df["date"] == today]
    if df_today.empty:
        return None

    vol_today = float(df_today.iloc[-1]["volume"] or 0.0)
    if vol_today <= 0:
        return None

    vols = []
    for d in prev_days:
        ddf = df[df["date"] == d]
        if ddf.empty:
            continue
        v = float(ddf.iloc[-1]["volume"] or 0.0)
        if v > 0:
            vols.append(v)

    if not vols:
        return None

    avg_prev = float(np.mean(vols))
    if avg_prev <= 0:
        return None

    return float(vol_today / avg_prev)


async def req_hist_df_async(
    ib: IB,
    contract,
    cfg: BarsCfg,
    sem: asyncio.Semaphore,
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    async with sem:
        for attempt in range(1, retries + 1):
            try:
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr=cfg.duration,
                    barSizeSetting=cfg.bar_size,
                    whatToShow=cfg.what_to_show,
                    useRTH=1 if cfg.use_rth else 0,
                    formatDate=1,
                    keepUpToDate=False,
                )
                return bars_to_df(bars)
            except Exception:
                await asyncio.sleep(0.6 * attempt + random.random() * 0.4)
        return None


async def compute_one_symbol(
    ib: IB,
    sym: str,
    sem: asyncio.Semaphore,
    lookback_days: int,
    relvol_cfg: BarsCfg,
    rsi_macd_cfg: BarsCfg,
) -> dict:
    sym = _norm_sym(sym)
    c = Stock(sym, "SMART", "USD")
    try:
        await ib.qualifyContractsAsync(c)
    except Exception:
        pass

    # RelVol from 30m bars (cheap)
    df_rel = await req_hist_df_async(ib, c, relvol_cfg, sem)
    relv = relvol_from_last_30m_bar(df_rel, lookback_days=lookback_days)

    # RSI/MACD from configured bars
    df_rm = await req_hist_df_async(ib, c, rsi_macd_cfg, sem)

    out = {
        "symbol": sym,
        "rsi14": None,
        "macd": None,
        "macd_signal": None,
        "macd_hist": None,
        "relvol": float(relv) if relv is not None else None,
        "last_bar_time": None,
        "last_close": None,
    }

    if df_rm is None or df_rm.empty:
        return out

    close = df_rm["close"].astype(float)

    r = rsi(close, 14)
    macd_line, sig_line, hist = macd(close, 12, 26, 9)

    out["rsi14"] = float(r.iloc[-1]) if pd.notna(r.iloc[-1]) else None
    out["macd"] = float(macd_line.iloc[-1]) if pd.notna(macd_line.iloc[-1]) else None
    out["macd_signal"] = float(sig_line.iloc[-1]) if pd.notna(sig_line.iloc[-1]) else None
    out["macd_hist"] = float(hist.iloc[-1]) if pd.notna(hist.iloc[-1]) else None
    out["last_bar_time"] = df_rm["time"].iloc[-1].isoformat()
    out["last_close"] = float(close.iloc[-1]) if pd.notna(close.iloc[-1]) else None
    return out


async def run_async(args):
    ib = IB()
    client_id = args.client_id if args.client_id else random.randint(2000, 65000)

    try:
        await ib.connectAsync("127.0.0.1", args.port, clientId=client_id, readonly=True, timeout=60)
        print(f"✓ Connected to IBKR on port {args.port} (clientId={client_id})")

        scan_code = SCANNER_CODES[args.scanner]
        syms = await fetch_scanner_symbols_async(ib, scan_code, args.location, args.limit)
        print(f"✓ Scanner {args.scanner} returned {len(syms)} symbols")

        sem = asyncio.Semaphore(args.concurrency)

        relvol_cfg = BarsCfg(
            bar_size="30 mins",
            duration=f"{args.lookback_days} D",
            use_rth=bool(args.use_rth),
            what_to_show=args.what,
        )

        rsi_macd_cfg = BarsCfg(
            bar_size=args.rsi_macd_barsize,
            duration=args.rsi_macd_duration,
            use_rth=bool(args.use_rth),
            what_to_show=args.what,
        )

        rows = await asyncio.gather(
            *[compute_one_symbol(ib, sym, sem, args.lookback_days, relvol_cfg, rsi_macd_cfg) for sym in syms]
        )

        out_df = pd.DataFrame(rows)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        out_df.to_csv(args.out, index=False)
        print(f"\n✓ Wrote {len(out_df)} rows -> {args.out}")

    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass
        # yield once so callbacks flush before loop ends
        await asyncio.sleep(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7496)
    ap.add_argument("--client-id", type=int, default=0)
    ap.add_argument("--scanner", type=str, default="most_active", choices=SCANNER_CODES.keys())
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--location", type=str, default="STK.US.MAJOR")

    ap.add_argument("--use-rth", action="store_true")
    ap.add_argument("--what", type=str, default="TRADES")
    ap.add_argument("--lookback-days", type=int, default=10)

    ap.add_argument("--rsi-macd-barsize", type=str, default="30 mins")
    ap.add_argument("--rsi-macd-duration", type=str, default="10 D")

    ap.add_argument("--concurrency", type=int, default=4, help="Try 3-6; too high may hit IB pacing.")
    ap.add_argument("--out", type=str, default="./ibkr_indicators.csv")
    args = ap.parse_args()

    asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
