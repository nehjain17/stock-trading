"""
ibkr_social_sentiment.py

- Gets symbols from IBKR scanner (ib_insync)
- Fetches Stocktwits messages per symbol
- Fetches ApeWisdom (Reddit aggregate) once, then joins
- Computes simple sentiment (VADER if available; else rule-based)
- Produces per-symbol metrics you can sort in your UI

Run:
  python ibkr_social_sentiment.py

Requirements:
  pip install ib_insync requests
Optional:
  pip install nltk && python -c "import nltk; nltk.download('vader_lexicon')"
"""

from __future__ import annotations

import os
import re
import time
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
from ib_insync import IB, Stock, ScannerSubscription, util

# ----------------------------
# Sentiment helpers (free)
# ----------------------------

BULL_WORDS = {
    "breakout", "rip", "moon", "squeeze", "gamma", "runner", "send", "pump",
    "bullish", "long", "calls", "gap", "reversal", "support", "accumulate",
    "undervalued", "buy", "buying", "added", "loading"
}
BEAR_WORDS = {
    "dump", "rug", "dilution", "offering", "short", "bearish", "puts",
    "fraud", "scam", "bag", "bagholder", "sell", "selling", "overvalued",
    "collapse", "reject", "resistance"
}

WORD_RE = re.compile(r"[A-Za-z]+")

try:
    from nltk.sentiment.vader import SentimentIntensityAnalyzer  # type: ignore
    _VADER = SentimentIntensityAnalyzer()
except Exception:
    _VADER = None


def rule_sentiment(text: str) -> float:
    """Returns a cheap polarity score in [-1, 1] based on keyword counts."""
    words = [w.lower() for w in WORD_RE.findall(text)]
    if not words:
        return 0.0
    bull = sum(1 for w in words if w in BULL_WORDS)
    bear = sum(1 for w in words if w in BEAR_WORDS)
    score = (bull - bear) / max(3, (bull + bear + 3))  # damped
    return max(-1.0, min(1.0, score))


def vader_sentiment(text: str) -> float:
    """If VADER available, returns compound score in [-1, 1]."""
    if _VADER is None:
        return 0.0
    return float(_VADER.polarity_scores(text).get("compound", 0.0))


def combined_sentiment(texts: List[str]) -> Tuple[float, str]:
    """
    Aggregate sentiment for a batch of texts.
    Returns (score [-1..1], label).
    """
    if not texts:
        return 0.0, "neutral"

    # Combine both signals; VADER gets more weight if present.
    rs = sum(rule_sentiment(t) for t in texts) / len(texts)
    vs = sum(vader_sentiment(t) for t in texts) / len(texts) if _VADER else 0.0
    score = (0.35 * rs) + (0.65 * vs) if _VADER else rs

    if score > 0.15:
        return score, "bullish"
    if score < -0.15:
        return score, "bearish"
    return score, "neutral"


# ----------------------------
# Stocktwits
# ----------------------------

def fetch_stocktwits(symbol: str, limit: int = 30, timeout: int = 10) -> Dict:
    """
    Fetch Stocktwits stream for a symbol.
    Public endpoint; rate-limited.
    """
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # Keep only newest messages
    msgs = data.get("messages", [])[:limit]
    out = {
        "symbol": symbol,
        "messages": [{
            "created_at": m.get("created_at"),
            "body": m.get("body", ""),
            "entities": m.get("entities", {}),
        } for m in msgs]
    }
    return out


def stocktwits_metrics(st: Dict) -> Dict:
    msgs = st.get("messages", [])
    bodies = [m.get("body", "") for m in msgs if m.get("body")]
    # Count labeled sentiment if present
    bullish = 0
    bearish = 0
    for m in msgs:
        entities = (m.get("entities") or {})
        sentiment = entities.get("sentiment") or {}
        if isinstance(sentiment, dict):
            basic = (sentiment.get("basic") or "").lower()
            if basic == "bullish":
                bullish += 1
            elif basic == "bearish":
                bearish += 1

    score, label = combined_sentiment(bodies)

    return {
        "st_msg_count": len(msgs),
        "st_bullish_count": bullish,
        "st_bearish_count": bearish,
        "st_llm_free_sentiment": label,
        "st_llm_free_score": round(score, 4),
        "st_sample_texts": bodies[:3],  # helpful for debugging/UI tooltip
    }


# ----------------------------
# ApeWisdom
# ----------------------------

def fetch_apewisdom_all_pages(max_pages: int = 5, timeout: int = 10) -> List[Dict]:
    """
    Fetch ApeWisdom 'all-stocks' pages.
    Not official-guaranteed SLA; cache results in your app.
    """
    rows: List[Dict] = []
    for page in range(1, max_pages + 1):
        url = f"https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}"
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            break
        data = r.json()
        # API returns list
        if not isinstance(data, list) or not data:
            break
        rows.extend(data)
        time.sleep(0.15)  # be polite
    return rows


def apewisdom_index(rows: List[Dict]) -> Dict[str, Dict]:
    """
    Index by ticker upper.
    """
    idx: Dict[str, Dict] = {}
    for row in rows:
        t = (row.get("ticker") or "").upper()
        if not t:
            continue
        idx[t] = row
    return idx


# ----------------------------
# IBKR Scanner
# ----------------------------

@dataclass
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497  # 7497 paper TWS; 7496 live TWS (common defaults)
    client_id: int = 91


def ibkr_get_scanner_symbols(
    cfg: IBKRConfig,
    scan_code: str = "MOST_ACTIVE",
    instrument: str = "STK",
    location_code: str = "STK.US.MAJOR",   # try: STK.US.MAJOR, STK.US, STK.NASDAQ, STK.SMART
    number_of_rows: int = 50,
) -> List[str]:
    """
    Requires TWS or IB Gateway running locally and API enabled.
    """
    ib = IB()
    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id)

    sub = ScannerSubscription(
        instrument=instrument,
        locationCode=location_code,
        scanCode=scan_code,
        numberOfRows=number_of_rows,
    )

    scan_data = ib.reqScannerData(sub)
    symbols: List[str] = []
    for sd in scan_data:
        c = sd.contractDetails.contract
        if getattr(c, "symbol", None):
            symbols.append(str(c.symbol).upper())

    ib.disconnect()
    # Dedup preserve order
    seen = set()
    out = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ----------------------------
# Join + Scoring
# ----------------------------

def social_score(row: Dict) -> float:
    """
    Simple score combining:
    - Stocktwits message count
    - bullish ratio (from labeled sentiment if present; else from score)
    - ApeWisdom mentions/upvotes + rank movement
    """
    st_cnt = row.get("st_msg_count", 0) or 0
    bull = row.get("st_bullish_count", 0) or 0
    bear = row.get("st_bearish_count", 0) or 0
    total_labeled = bull + bear
    bull_ratio = (bull / total_labeled) if total_labeled > 0 else (0.5 + 0.5 * float(row.get("st_llm_free_score", 0.0)))

    # ApeWisdom fields may be strings
    aw_mentions = int(float(row.get("aw_mentions", 0) or 0))
    aw_upvotes = int(float(row.get("aw_upvotes", 0) or 0))
    aw_rank = int(float(row.get("aw_rank", 9999) or 9999))
    aw_rank_24h = int(float(row.get("aw_rank_24h_ago", aw_rank) or aw_rank))
    rank_delta = (aw_rank_24h - aw_rank)  # positive means improved rank

    # Normalize a bit
    score = 0.0
    score += min(40.0, st_cnt * 1.2)
    score += (bull_ratio - 0.5) * 20.0
    score += min(25.0, aw_mentions * 0.5)
    score += min(15.0, math.log1p(aw_upvotes) * 3.0)
    score += max(-10.0, min(10.0, rank_delta * 0.25))
    return round(score, 3)


def build_social_rows(symbols: List[str], ape_rows: List[Dict], st_limit: int = 30) -> List[Dict]:
    aw = apewisdom_index(ape_rows)
    out: List[Dict] = []

    for sym in symbols:
        row: Dict = {"symbol": sym}

        # ApeWisdom join (if present)
        awrow = aw.get(sym, {})
        row.update({
            "aw_rank": awrow.get("rank"),
            "aw_mentions": awrow.get("mentions"),
            "aw_upvotes": awrow.get("upvotes"),
            "aw_rank_24h_ago": awrow.get("rank_24h_ago"),
            "aw_mentions_24h_ago": awrow.get("mentions_24h_ago"),
        })

        # Stocktwits fetch + metrics
        try:
            st = fetch_stocktwits(sym, limit=st_limit)
            row.update(stocktwits_metrics(st))
        except Exception as e:
            row.update({
                "st_msg_count": 0,
                "st_bullish_count": 0,
                "st_bearish_count": 0,
                "st_llm_free_sentiment": "neutral",
                "st_llm_free_score": 0.0,
                "st_error": str(e),
            })

        row["social_score"] = social_score(row)
        out.append(row)

        time.sleep(0.2)  # be polite to Stocktwits

    return out


# ----------------------------
# Main
# ----------------------------

def main():
    cfg = IBKRConfig(
        host=os.getenv("IB_HOST", "127.0.0.1"),
        port=int(os.getenv("IB_PORT", "7496")),
        client_id=int(os.getenv("IB_CLIENT_ID", "91")),
    )

    scan_code = os.getenv("IB_SCAN_CODE", "MOST_ACTIVE")
    location_code = os.getenv("IB_LOCATION_CODE", "STK.US.MAJOR")
    number_of_rows = int(os.getenv("IB_ROWS", "30"))

    print(f"[IBKR] Getting scanner symbols: scan_code={scan_code} location={location_code} rows={number_of_rows}")
    symbols = ibkr_get_scanner_symbols(
        cfg=cfg,
        scan_code=scan_code,
        location_code=location_code,
        number_of_rows=number_of_rows,
    )
    print(f"[IBKR] Symbols: {symbols}")

    print("[ApeWisdom] Fetching trending pages...")
    ape_rows = fetch_apewisdom_all_pages(max_pages=5)

    print("[Social] Building rows (Stocktwits + ApeWisdom + sentiment)...")
    rows = build_social_rows(symbols, ape_rows, st_limit=30)

    # Sort best first
    rows.sort(key=lambda r: r.get("social_score", 0), reverse=True)

    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
