#!/usr/bin/env python3
# backend/app.py
from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ----------------------------
# Paths / config
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

DEDUP_ALL_BY_SYMBOL_DEFAULT = True

LABEL_MAP = {
    "all": "All (Merged)",
    "most_active": "Most Active",
    "top_gainers": "Top % Gainers",
    "top_losers": "Top % Losers",
    "top_volume": "Top Volume",
    "top_trade_rate": "Top Trade Rate",
}

# IMPORTANT: SINGLE output CSV per screener (scanner+bars+VWAP+INDICATORS)
SCREENER_SCANNER_FILES = {
    "most_active": "ibkr_data_most_active.csv",
    "top_gainers": "ibkr_data_top_gainers.csv",
    "top_losers": "ibkr_data_top_losers.csv",
    "top_volume": "ibkr_data_top_volume.csv",
    "top_trade_rate": "ibkr_data_top_trade_rate.csv",
}

NEWS_FILE_PREFIXES = [
    "news_ibkr_",
    "news_benzinga_",
    "news_finnhub_",
    "news_polygon_",
]

TEST_IBKR = DATA_DIR / "test_ibkr.py"  # legacy reference
IBKR_NEWS = DATA_DIR / "ibkr_news.py"
BENZINGA = DATA_DIR / "benzinga.py"
FINNHUB = DATA_DIR / "finnhub.py"
POLYGON = DATA_DIR / "polygon.py"

# ✅ One-pass generator module (scanner + bars + indicators into ONE CSV)
# Put module at: backend/data/ibkr_onepass.py  (importable as data.ibkr_onepass)
ONEPASS_MODULE = "data.ibkr_onepass"

# ----------------------------
# Time helpers
# ----------------------------
def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: Optional[datetime] = None) -> str:
    return (dt or utc_now_dt()).isoformat()


def pd_utc_now() -> pd.Timestamp:
    """
    tz-aware pandas Timestamp in UTC without tz_localize() errors.
    """
    ts = pd.Timestamp.utcnow()
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


# ----------------------------
# Utils
# ----------------------------
def tail_text(path: Path, max_bytes: int = 25_000) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
        if len(data) <= max_bytes:
            return data.decode("utf-8", errors="replace")
        return data[-max_bytes:].decode("utf-8", errors="replace")
    except Exception:
        return ""


def safe_read_csv(path: Path) -> pd.DataFrame:
    """
    Avoid pandas.errors.EmptyDataError crashing your API.
    If file is empty or missing, return empty DF.
    """
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception:
        # If partially-written during refresh, avoid crashing.
        return pd.DataFrame()


def normalize_symbol(s: Any) -> str:
    """
    Robust symbol normalizer.
    Handles cases where pandas passes a Series because df has duplicate 'symbol' columns.
    Avoids boolean evaluation of Series (your crash).
    """
    if s is None:
        return ""

    if isinstance(s, (pd.Series, pd.Index, list, tuple, np.ndarray)):
        try:
            for v in list(s):
                if v is None:
                    continue
                sv = str(v).strip()
                if sv and sv.lower() != "nan":
                    return sv.upper()
            return ""
        except Exception:
            return ""

    try:
        sv = str(s).strip()
        if not sv or sv.lower() == "nan":
            return ""
        return sv.upper()
    except Exception:
        return ""


def to_number(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        try:
            vv = float(v)
            if not math.isfinite(vv):
                return None
            if abs(vv - int(vv)) < 1e-12:
                return int(vv)
            return vv
        except Exception:
            return None
    try:
        s = str(v).replace(",", "").strip()
        if s == "" or s.lower() == "nan":
            return None
        f = float(s)
        if not math.isfinite(f):
            return None
        if abs(f - int(f)) < 1e-12:
            return int(f)
        return f
    except Exception:
        return None


def get_scanner_path(screener: str) -> Path:
    fname = SCREENER_SCANNER_FILES.get(screener, f"ibkr_data_{screener}.csv")
    return DATA_DIR / fname


def find_news_files_for_screener(screener: str) -> List[Path]:
    files: List[Path] = []
    for pref in NEWS_FILE_PREFIXES:
        p = DATA_DIR / f"{pref}{screener}.csv"
        if p.exists():
            files.append(p)
    return files


def json_safe(x: Any) -> Any:
    """
    Convert NaN/Inf to None so Starlette can JSON serialize.
    Works recursively for dict/list/tuples.
    """
    if x is None:
        return None

    if isinstance(x, (np.generic,)):
        x = x.item()

    if isinstance(x, float):
        if not math.isfinite(x):
            return None
        return x

    if isinstance(x, (int, bool, str)):
        return x

    if isinstance(x, datetime):
        return x.isoformat()

    if isinstance(x, pd.Timestamp):
        if pd.isna(x):
            return None
        try:
            return x.isoformat()
        except Exception:
            return str(x)

    if isinstance(x, dict):
        return {k: json_safe(v) for k, v in x.items()}

    if isinstance(x, (list, tuple)):
        return [json_safe(v) for v in x]

    return x


def canonicalize_scanner_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize scanner CSV schema so API/UI always works:
    - Ensures EXACTLY ONE 'symbol' column (fixes duplicate column crash)
    - Accepts 'Symbol' and renames to 'symbol'
    - Also canonicalizes common "UI column" names from test_ibkr.py
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # If "symbol" missing but "Symbol" exists, rename
    if "symbol" not in df.columns and "Symbol" in df.columns:
        df = df.rename(columns={"Symbol": "symbol"})

    # Collapse duplicate symbol columns: df.loc[:, "symbol"] can become DataFrame
    sym_idxs = [i for i, c in enumerate(df.columns) if c == "symbol"]
    if len(sym_idxs) >= 2:
        sym_df = df.loc[:, ["symbol"]]
        # if duplicate names, selecting ["symbol"] can still return multiple
        if isinstance(sym_df, pd.DataFrame) and sym_df.shape[1] > 1:
            chosen = None
            for col_i in range(sym_df.shape[1]):
                col = sym_df.iloc[:, col_i]
                if col.notna().any():
                    chosen = col
                    break
            if chosen is None:
                chosen = sym_df.iloc[:, 0]
            df = df.drop(columns=["symbol"])
            df["symbol"] = chosen
        else:
            # already single
            pass

    # Normalize symbol values
    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].apply(normalize_symbol)

    # Map common test_ibkr.py header names into snake_case API-friendly fields
    rename_map = {
        "Last": "last",
        "%Chg": "pct_change",
        "RelVol": "relvol",

        "Vol(1m)": "vol_1m", 
        "Vol(3m)": "vol_3m",
        "Vol(5m)": "vol_5m",
        "Vol(10m)": "vol_10m",
        "Vol(15m)": "vol_15m",

        "Trades(1m)": "trades_1m",
        "Trades(5m)": "trades_5m",
        "Trades(10m)": "trades_10m",
        "Trades(15m)": "trades_15m",

        "Shortable": "shortable_shares",

        "RSI(14)": "rsi14",
        "MACD": "macd",
        "MACD Sig": "macd_signal",
        "MACD Hist": "macd_hist",

        "VWAP5 Dist": "vwap5_dist",
        "VWAP30 Dist": "vwap30_dist",
        "VWAP(30m)": "vwap_30m",
    }

    for old, new in rename_map.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    return df


# ----------------------------
# Loading data
# ----------------------------
def load_news_df(screener: str) -> Tuple[pd.DataFrame, List[str]]:
    files = find_news_files_for_screener(screener)
    if not files:
        return pd.DataFrame(), []
    dfs: List[pd.DataFrame] = []
    for f in files:
        d = safe_read_csv(f)
        if not d.empty:
            dfs.append(d)
    if not dfs:
        return pd.DataFrame(), [f.name for f in files]
    out = pd.concat(dfs, ignore_index=True)
    return out, [f.name for f in files]


def load_scanner_df_for_screener(screener: str) -> Tuple[pd.DataFrame, Optional[str]]:
    path = get_scanner_path(screener)
    df = safe_read_csv(path)
    if df.empty:
        return df, f"Scanner file empty or missing: {path.name}"
    df = canonicalize_scanner_df(df)
    if df.empty:
        return df, f"Scanner file unreadable/empty after canonicalize: {path.name}"
    if "symbol" not in df.columns:
        return df, f"Scanner file missing symbol column after canonicalize: {path.name}"
    return df, None


def load_scanner_df(screener: str, dedupe_all_by_symbol: bool) -> Tuple[pd.DataFrame, Optional[str], List[str]]:
    warnings: List[str] = []

    if screener != "all":
        df, err = load_scanner_df_for_screener(screener)
        if err:
            warnings.append(err)
        return df, err, warnings

    dfs: List[pd.DataFrame] = []
    for key, fname in SCREENER_SCANNER_FILES.items():
        p = DATA_DIR / fname
        df = safe_read_csv(p)
        if df.empty:
            warnings.append(f"Scanner file empty/missing: {fname}")
            continue
        df = canonicalize_scanner_df(df)
        if df.empty or "symbol" not in df.columns:
            warnings.append(f"Scanner file invalid after canonicalize: {fname}")
            continue
        df = df.copy()
        df["screener"] = key
        df["screenerLabel"] = LABEL_MAP.get(key, key)
        dfs.append(df)

    if not dfs:
        return pd.DataFrame(), "No scanner files found or all empty.", warnings

    out = pd.concat(dfs, ignore_index=True)

    if dedupe_all_by_symbol and "symbol" in out.columns:
        out = out.drop_duplicates("symbol", keep="first")

    return out, None, warnings


# ----------------------------
# Build rows (THIS feeds UI)
# ----------------------------
def build_rows(scanner_df: pd.DataFrame, news_df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if scanner_df is None or scanner_df.empty:
        return [], {"newsRows": 0, "symbolsWithNews": 0, "providers": 0}

    df = scanner_df.copy()
    if "symbol" not in df.columns:
        return [], {"newsRows": 0, "symbolsWithNews": 0, "providers": 0}

    df["symbol"] = df["symbol"].apply(normalize_symbol)

    def pick_num(row, *keys):
        for k in keys:
            if k in df.columns:
                v = row.get(k)
                if v is not None:
                    return to_number(v)
        return None

    def pick_str(row, *keys):
        for k in keys:
            if k in df.columns:
                v = row.get(k)
                if v is not None and str(v).strip() != "" and str(v).lower() != "nan":
                    return str(v)
        return None

    # ----------------------------
    # News aggregation
    # ----------------------------
    if news_df is None or news_df.empty:
        df["latestNewsUtc"] = None
        df["latestHeadline"] = None
        df["newsCount"] = 0
        providers = 0
        news_rows = 0
        symbols_with_news = 0
    else:
        n = news_df.copy()
        if "symbol" in n.columns:
            n["symbol"] = n["symbol"].apply(normalize_symbol)
        else:
            n["symbol"] = ""

        if "published_at_utc" in n.columns:
            n["published_at_utc"] = pd.to_datetime(n["published_at_utc"], utc=True, errors="coerce")
        else:
            n["published_at_utc"] = pd.NaT

        if "headline" not in n.columns:
            n["headline"] = ""

        n_sorted = n.sort_values("published_at_utc", ascending=False)
        latest = n_sorted.groupby("symbol", as_index=False).first()
        counts = n.groupby("symbol").size().reset_index(name="newsCount")

        df = (
            df.merge(latest[["symbol", "published_at_utc", "headline"]], on="symbol", how="left")
            .merge(counts, on="symbol", how="left")
        )

        df["latestNewsUtc"] = df["published_at_utc"].dt.strftime("%Y-%m-%d %H:%M:%S")
        df["latestHeadline"] = df["headline"]
        df["newsCount"] = df["newsCount"].fillna(0).astype(int)

        providers = int(n["provider"].nunique()) if "provider" in n.columns else 0
        news_rows = int(len(n))
        symbols_with_news = int((df["newsCount"] > 0).sum())

    # ----------------------------
    # Normalize output schema
    # ----------------------------
    out_rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        pct_change_val = r.get("pct_change") if "pct_change" in df.columns else r.get("pctChange")
        shortable_val = r.get("shortable_shares") if "shortable_shares" in df.columns else r.get("Shortable")

        vol_1m = pick_num(r, "vol_1m", "Vol(1m)")
        vol_3m = pick_num(r, "vol_3m", "Vol(3m)")
        vol_5m = pick_num(r, "vol_5m", "Vol(5m)")
        vol_10m = pick_num(r, "vol_10m", "Vol(10m)")
        vol_15m = pick_num(r, "vol_15m", "Vol(15m)")

        trades_1m = pick_num(r, "trades_1m", "Trades(1m)")
        trades_5m = pick_num(r, "trades_5m", "Trades(5m)")
        trades_10m = pick_num(r, "trades_10m", "Trades(10m)")
        trades_15m = pick_num(r, "trades_15m", "Trades(15m)")

        vwap_30m = pick_num(r, "vwap_30m", "VWAP(30m)")
        vwap5_dist = pick_num(r, "vwap5_dist", "VWAP5 Dist")
        vwap30_dist = pick_num(r, "vwap30_dist", "VWAP30 Dist")
        relvol = pick_num(r, "relvol", "RelVol")

        rsi14 = pick_num(r, "rsi14", "RSI(14)")
        macd = pick_num(r, "macd", "MACD")
        macd_signal = pick_num(r, "macd_signal", "MACD Sig")
        macd_hist = pick_num(r, "macd_hist", "MACD Hist")

        out_rows.append(
            {
                "screener": r.get("screener"),
                "screenerLabel": r.get("screenerLabel"),
                "symbol": r.get("symbol"),

                "last": to_number(r.get("last") if "last" in df.columns else r.get("Last")),
                "prevClose": to_number(r.get("prev_close") if "prev_close" in df.columns else r.get("_prevClose")),
                "pctChange": to_number(pct_change_val),

                "vol_1m": vol_1m,
                "vol_3m": vol_3m,
                "vol_5m": vol_5m,
                "vol_10m": vol_10m,
                "vol_15m": vol_15m,

                "trades_1m": trades_1m,
                "trades_5m": trades_5m,
                "trades_10m": trades_10m,
                "trades_15m": trades_15m,

                "shortable_shares": to_number(shortable_val),

                "rsi14": rsi14,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_hist": macd_hist,
                "relvol": relvol,

                "vwap_30m": vwap_30m,
                "vwap5_dist": vwap5_dist,
                "vwap30_dist": vwap30_dist,

                # camelCase aliases (UI safety)
                "vol3m": vol_3m,
                "vol5m": vol_5m,
                "vol10m": vol_10m,
                "vol15m": vol_15m,

                "trades5m": trades_5m,
                "trades10m": trades_10m,
                "trades15m": trades_15m,

                "shortableShares": to_number(shortable_val),
                "relVol": relvol,
                "macdSignal": macd_signal,
                "macdHist": macd_hist,

                "newsCount": to_number(r.get("newsCount")),
                "latestNewsUtc": r.get("latestNewsUtc"),
                "latestHeadline": r.get("latestHeadline"),
            }
        )

    return out_rows, {"newsRows": news_rows, "symbolsWithNews": symbols_with_news, "providers": providers}


# ----------------------------
# Refresh job models
# ----------------------------
class RefreshRequest(BaseModel):
    screener: str = "most_active"
    days: int = 3
    refresh_scanner: bool = True
    providers: List[str] = ["ibkr", "benzinga", "finnhub"]
    limit: int = 50
    dedupe_all_by_symbol: bool = True

    # one-pass tuning
    concurrency: int = 1
    lookback_days: int = 3
    rsi_macd_barsize: str = "30 mins"
    rsi_macd_duration: str = "3 D"


@dataclass
class StepState:
    name: str
    cmd: List[str]
    status: str = "queued"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    return_code: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: Optional[str] = None


@dataclass
class JobState:
    job_id: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: utc_iso())
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    request: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    steps: List[StepState] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
    log_file: Optional[str] = None
    pid: Optional[int] = None


JOBS: Dict[str, JobState] = {}
JOBS_LOCK = threading.Lock()

ACTIVE_BY_KEY: Dict[str, str] = {}
ACTIVE_LOCK = threading.Lock()


# ----------------------------
# Build commands
# ----------------------------
def python_exe() -> str:
    return os.environ.get("PYTHON") or sys.executable


def build_step_commands(req: RefreshRequest, screener_key: str) -> List[Tuple[str, List[str]]]:
    out: List[Tuple[str, List[str]]] = []
    py = python_exe()

    if req.refresh_scanner:
        out.append(
            (
                "onepass",
                [
                    py,
                    "-m",
                    ONEPASS_MODULE,
                    "--scanner",
                    screener_key,
                    "--limit",
                    str(req.limit),
                    "--concurrency",
                    str(req.concurrency),
                    "--lookback-days",
                    str(req.lookback_days),
                    "--rsi-macd-barsize",
                    str(req.rsi_macd_barsize),
                    "--rsi-macd-duration",
                    str(req.rsi_macd_duration),
                    "--out",
                    str(get_scanner_path(screener_key)),
                ],
            )
        )

    prov = set([p.lower().strip() for p in (req.providers or [])])

    if "ibkr" in prov:
        out.append(("ibkr_news", [py, "-m", "data.ibkr_news", "--scanner", screener_key, "--days", str(req.days)]))
    if "benzinga" in prov:
        out.append(("benzinga", [py, "-m", "data.benzinga", "--scanner", screener_key, "--days", str(req.days)]))
    if "finnhub" in prov:
        out.append(("finnhub", [py, "-m", "data.finnhub", "--scanner", screener_key, "--days", str(req.days)]))
    if "polygon" in prov:
        out.append(("polygon", [py, "-m", "data.polygon", "--scanner", screener_key, "--days", str(req.days)]))

    return out


def run_subprocess_with_live_log(
    job_id: str,
    step: StepState,
    cmd: List[str],
    log_path: Path,
    cwd: Path,
    timeout_sec: int = 1200,
) -> int:
    step.status = "running"
    step.started_at = utc_iso()

    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n=== [{utc_iso()}] STEP {step.name} START ===\n")
        lf.write(f"CMD: {' '.join(cmd)}\n")

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job.pid = proc.pid

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    def pump(stream, collector, prefix: str):
        for line in iter(stream.readline, ""):
            collector.append(line)
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(prefix + line)
        stream.close()

    t1 = threading.Thread(target=pump, args=(proc.stdout, stdout_lines, ""), daemon=True)
    t2 = threading.Thread(target=pump, args=(proc.stderr, stderr_lines, "ERR: "), daemon=True)
    t1.start()
    t2.start()

    start = time.time()
    rc: Optional[int] = None
    try:
        while True:
            if proc.poll() is not None:
                rc = proc.returncode
                break
            if time.time() - start > timeout_sec:
                proc.terminate()
                time.sleep(1)
                if proc.poll() is None:
                    proc.kill()
                rc = -1
                step.error = f"Timeout after {timeout_sec}s"
                break
            time.sleep(0.2)
    finally:
        t1.join(timeout=2)
        t2.join(timeout=2)

    step.stdout_tail = "".join(stdout_lines[-80:])
    step.stderr_tail = "".join(stderr_lines[-80:])
    step.return_code = int(rc if rc is not None else -1)
    step.ended_at = utc_iso()

    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(f"=== [{utc_iso()}] STEP {step.name} END rc={step.return_code} ===\n")

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job and job.pid == proc.pid:
            job.pid = None

    return step.return_code


def refresh_worker(job_id: str, req: RefreshRequest):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = utc_iso()
        job.error = None

    screeners = list(SCREENER_SCANNER_FILES.keys()) if req.screener == "all" else [req.screener]
    log_path = LOG_DIR / f"refresh_{job_id}.log"

    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job.log_file = str(log_path)

    try:
        for screener_key in screeners:
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job or job.status == "canceled":
                    raise RuntimeError("Job canceled")

            step_cmds = build_step_commands(req, screener_key)
            steps: List[StepState] = [StepState(name=f"{screener_key}:{nm}", cmd=cmd) for nm, cmd in step_cmds]

            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job:
                    job.steps.extend(steps)

            for step in steps:
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if not job or job.status == "canceled":
                        step.status = "canceled"
                        raise RuntimeError("Job canceled")

                rc = run_subprocess_with_live_log(job_id, step, step.cmd, log_path, cwd=BASE_DIR, timeout_sec=1200)
                if rc != 0:
                    step.status = "failed"
                    raise RuntimeError(f"Step failed: {step.name} rc={rc}")
                step.status = "done"

        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job.status = "done"
                job.ended_at = utc_iso()
                job.outputs = {
                    "scannerFiles": (
                        list(SCREENER_SCANNER_FILES.values())
                        if req.screener == "all"
                        else [get_scanner_path(req.screener).name]
                    ),
                    "newsFiles": [],
                }

    except Exception as e:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                if job.status != "canceled":
                    job.status = "failed"
                    job.error = str(e)
                job.ended_at = utc_iso()
    finally:
        with ACTIVE_LOCK:
            if ACTIVE_BY_KEY.get(req.screener) == job_id:
                ACTIVE_BY_KEY.pop(req.screener, None)


def start_refresh_job(req: RefreshRequest) -> JobState:
    with ACTIVE_LOCK:
        existing = ACTIVE_BY_KEY.get(req.screener)
        if existing:
            with JOBS_LOCK:
                job = JOBS.get(existing)
                if job and job.status in ("queued", "running"):
                    return job
            ACTIVE_BY_KEY.pop(req.screener, None)

        job_id = str(uuid.uuid4())
        ACTIVE_BY_KEY[req.screener] = job_id

    job = JobState(job_id=job_id, status="queued", created_at=utc_iso(), request=req.model_dump())
    with JOBS_LOCK:
        JOBS[job_id] = job

    threading.Thread(target=refresh_worker, args=(job_id, req), daemon=True).start()
    return job


def cancel_job(job_id: str) -> JobState:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        job.status = "canceled"
        job.ended_at = utc_iso()
        pid = job.pid

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        except Exception:
            pass
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    return job


# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/screeners")
def api_screeners():
    return {"screeners": [{"value": k, "label": LABEL_MAP.get(k, k)} for k in ["all"] + list(SCREENER_SCANNER_FILES.keys())]}


@app.get("/api/screener")
def api_screener(
    screener: str = "most_active",
    days: int = 3,
    search: str = "",
    dedupe_all_by_symbol: bool = DEDUP_ALL_BY_SYMBOL_DEFAULT,
):
    scanner_df, err, warnings = load_scanner_df(screener, dedupe_all_by_symbol=dedupe_all_by_symbol)

    if screener != "all" and err and (scanner_df is None or scanner_df.empty):
        return {"error": err, "warnings": warnings}

    if scanner_df is None or scanner_df.empty:
        return json_safe(
            {
                "screener": screener,
                "screenerLabel": LABEL_MAP.get(screener, screener),
                "days": int(days),
                "symbols": 0,
                "newsRows": 0,
                "symbolsWithNews": 0,
                "providers": 0,
                "rows": [],
                "scannerFiles": (
                    [SCREENER_SCANNER_FILES.get(screener, f"ibkr_data_{screener}.csv")]
                    if screener != "all"
                    else list(SCREENER_SCANNER_FILES.values())
                ),
                "newsFiles": [],
                "indicatorFiles": [],
                "warnings": warnings,
            }
        )

    news_df, news_files = load_news_df(screener)
    cutoff = pd_utc_now() - pd.Timedelta(days=int(days))

    if news_df is not None and not news_df.empty:
        if "published_at_utc" in news_df.columns:
            news_df["published_at_utc"] = pd.to_datetime(news_df["published_at_utc"], utc=True, errors="coerce")
            news_recent = news_df[news_df["published_at_utc"] >= cutoff].copy()
        else:
            news_recent = news_df.copy()
    else:
        news_recent = pd.DataFrame()

    scanner_syms = set(scanner_df["symbol"].apply(normalize_symbol).unique().tolist())
    if not news_recent.empty and "symbol" in news_recent.columns:
        news_recent["symbol"] = news_recent["symbol"].apply(normalize_symbol)
        news_recent = news_recent[news_recent["symbol"].isin(scanner_syms)]
        if search and "headline" in news_recent.columns:
            news_recent = news_recent[news_recent["headline"].astype(str).str.contains(search, case=False, na=False)]

    rows, stats = build_rows(scanner_df, news_recent)

    payload = {
        "screener": screener,
        "screenerLabel": LABEL_MAP.get(screener, screener),
        "days": int(days),
        "symbols": int(scanner_df["symbol"].apply(normalize_symbol).nunique()),
        "newsRows": stats["newsRows"],
        "symbolsWithNews": stats["symbolsWithNews"],
        "providers": stats["providers"],
        "rows": rows,
        "scannerFiles": ([get_scanner_path(screener).name] if screener != "all" else list(SCREENER_SCANNER_FILES.values())),
        "newsFiles": news_files,
        "indicatorFiles": [],
        "warnings": warnings,
    }
    return json_safe(payload)


@app.post("/api/refresh")
def api_refresh(req: RefreshRequest):
    job = start_refresh_job(req)
    return {"jobId": job.job_id, "status": job.status}


@app.get("/api/refresh/{job_id}")
def api_refresh_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        log_tail = ""
        if job.log_file:
            log_tail = tail_text(Path(job.log_file))

        return json_safe(
            {
                "jobId": job.job_id,
                "status": job.status,
                "createdAt": job.created_at,
                "startedAt": job.started_at,
                "endedAt": job.ended_at,
                "request": job.request,
                "error": job.error,
                "logFile": job.log_file,
                "logTail": log_tail,
                "steps": [
                    {
                        "name": s.name,
                        "status": s.status,
                        "startedAt": s.started_at,
                        "endedAt": s.ended_at,
                        "returnCode": s.return_code,
                        "cmd": s.cmd,
                        "stdoutTail": s.stdout_tail,
                        "stderrTail": s.stderr_tail,
                        "error": s.error,
                    }
                    for s in job.steps
                ],
                "outputs": job.outputs,
            }
        )


@app.post("/api/refresh/{job_id}/cancel")
def api_refresh_cancel(job_id: str):
    job = cancel_job(job_id)
    return {"jobId": job.job_id, "status": job.status}


"""
Run:
  python3 -m venv .venv
  source .venv/bin/activate
  pip install fastapi uvicorn pandas pydantic numpy

  uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""
