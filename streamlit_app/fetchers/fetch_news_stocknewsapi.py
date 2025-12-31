import os
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests
import argparse
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
try:
    from utils.security import sanitize_text, safe_url
except Exception:
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from utils.security import sanitize_text, safe_url

# Load local .env (closest) and also project root .env to pick up keys
load_dotenv(find_dotenv(), override=False)
try:
    # Resolve project root two levels up from this file: streamlit_app/fetchers -> streamlit_app -> repo root
    root_env = Path(__file__).resolve().parents[2] / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=str(root_env), override=False)
except Exception:
    pass

API_BASE = "https://stocknewsapi.com/api/v1"


def _get_token(explicit_token: Optional[str] = None) -> Optional[str]:
    if explicit_token:
        return explicit_token
    # Support multiple env var names for convenience
    return (
        os.getenv("STOCKNEWS_API_TOKEN")
        or os.getenv("STOCKNEWSAPI_TOKEN")
        or os.getenv("STOCKNEWS_API_KEY")
        or os.getenv("STOCKNEWSAPI_KEY")
    )


def _normalize_article(a: dict) -> dict:
    title = a.get("title") or a.get("headline") or ""
    url = a.get("news_url") or a.get("url") or ""
    created = a.get("date") or a.get("time") or a.get("published_date") or ""
    source = a.get("source_name") or a.get("source") or ""
    tickers = a.get("tickers") or []
    return {
        "title": sanitize_text(title, max_len=300),
        "url": safe_url(url),
        "created": sanitize_text(created, max_len=64),
        "source": sanitize_text(source, max_len=64),
        "tickers": [sanitize_text(t, max_len=16) for t in tickers if t],
    }


def fetch_stocknews_news(
    symbols: List[str],
    mode: str = "any",  # "any" -> tickers, "include" -> tickers-include, "only" -> tickers-only
    items: int = 50,
    page: int = 1,
    token: Optional[str] = None,
    date: Optional[str] = None,
    datetimerange: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    sourceexclude: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, List[dict]]:
    """
    Fetch news from StockNewsAPI for given symbols.

    - mode="any": articles mentioning any of the tickers (endpoint param: tickers)
    - mode="include": articles where all tickers are mentioned (endpoint param: tickers-include)
    - mode="only": articles where only the specified tickers are mentioned (endpoint param: tickers-only)

    Time filters:
    - date: supports formats like "last7days", "last30days" or a range "MMDDYYYY-MMDDYYYY"
      Example: date="01012022-01152022"
    - datetimerange: supports human keywords and HHMMSS ranges, e.g.
      "yesterday+160000-today+090000" or explicit dates "01012022+160000-01022022+090000"

    Returns a dict mapping symbol -> list of normalized articles.
    """
    tkn = _get_token(token)
    if not tkn:
        raise ValueError(
            "StockNewsAPI token not found. Set one of STOCKNEWS_API_TOKEN, STOCKNEWSAPI_TOKEN, STOCKNEWS_API_KEY, or STOCKNEWSAPI_KEY in .env, or pass token explicitly."
        )

    if not symbols:
        return {}

    # Build base params
    params = {
        "items": max(1, min(items, 100)),
        "page": max(1, page),
        "token": tkn,
    }
    if date:
        params["date"] = date
    if datetimerange:
        params["datetimerange"] = datetimerange
    if topic:
        params["topic"] = topic
    if source:
        params["source"] = source
    if sourceexclude:
        params["sourceexclude"] = sourceexclude

    # Select ticker parameter name based on mode
    tickers_param = {
        "any": "tickers",
        "include": "tickers-include",
        "only": "tickers-only",
    }.get(mode, "tickers")

    params[tickers_param] = ",".join(symbols)

    url = API_BASE
    # Example endpoints use the same base path; category endpoints use /category?section=...

    r = requests.get(url, params=params, timeout=max(3, timeout))
    if r.status_code != 200:
        raise RuntimeError(f"StockNewsAPI request failed: {r.status_code} {r.text[:200]}")

    data = r.json() if "application/json" in r.headers.get("Content-Type", "") else None
    if not data:
        # Attempt direct JSON parse regardless
        try:
            data = r.json()
        except Exception:
            data = {}

    articles = data.get("data") if isinstance(data, dict) else None
    if articles is None:
        # Some responses may return a list directly
        if isinstance(data, list):
            articles = data
        else:
            articles = []

    # Normalize and bucket by symbol
    by_symbol: Dict[str, List[dict]] = {s: [] for s in symbols}
    for a in articles:
        norm = _normalize_article(a)
        # Assign to mentioned tickers intersection
        mentioned = norm.get("tickers") or []
        for s in symbols:
            if s in mentioned or mode == "only":
                by_symbol.setdefault(s, []).append(norm)

    return by_symbol


def _parse_created_date(value: str) -> Optional[datetime]:
    """Best-effort parse for StockNewsAPI 'created' strings.
    Supports RFC2822 (e.g., 'Thu, 18 Dec 2025 19:00:00 -0500') and ISO-like formats.
    Returns timezone-aware datetime when possible; else None.
    """
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt
    except Exception:
        pass
    # Fallbacks for common patterns
    fmts = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(value, fmt)
            # Assume local time if tz-naive; convert to local timezone
            if dt.tzinfo is None:
                return dt
            return dt
        except Exception:
            continue
    return None


def _is_today_or_yesterday(dt: Optional[datetime]) -> bool:
    try:
        if dt is None:
            return False
        today = datetime.now(dt.tzinfo).date() if dt.tzinfo else datetime.now().date()
        yesterday = today - timedelta(days=1)
        return dt.date() in (today, yesterday)
    except Exception:
        return False


def _sort_desc_by_created(articles: List[dict]) -> List[dict]:
    def key(a: dict):
        dt = _parse_created_date(
            a.get("created")
            or a.get("date")
            or a.get("time")
            or a.get("published_date")
            or ""
        )
        return dt or datetime.min
    return sorted(articles, key=key, reverse=True)


def _filter_recent_today_yesterday(articles: List[dict]) -> List[dict]:
    filtered = []
    for a in articles:
        dt = _parse_created_date(
            a.get("created")
            or a.get("date")
            or a.get("time")
            or a.get("published_date")
            or ""
        )
        if _is_today_or_yesterday(dt):
            filtered.append(a)
    return filtered


def main_cli():
    parser = argparse.ArgumentParser(description="Fetch StockNewsAPI articles and write JSON per symbol")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated tickers to fetch")
    parser.add_argument("--from-csv", type=str, default="", help="CSV file with a 'symbol' column to read tickers from")
    parser.add_argument("--items", type=int, default=100, help="Items to request from API (max 100)")
    parser.add_argument("--mode", type=str, default="any", choices=["any","include","only"], help="Ticker match mode")
    parser.add_argument("--output", type=str, default=str(Path(__file__).resolve().parents[1] / "output" / "stocknewsapi_articles_top30.json"), help="Output JSON path")
    parser.add_argument("--per-symbol-limit", type=int, default=10, help="Max articles per symbol in output after filtering")
    parser.add_argument("--token", type=str, default="", help="Explicit StockNewsAPI token override")
    parser.add_argument("--recent-only", action="store_true", help="Keep only today/yesterday articles for each symbol")
    args = parser.parse_args()

    # Resolve symbols
    symbols: List[str] = []
    if args.from_csv:
        try:
            import pandas as pd
            df = pd.read_csv(args.from_csv)
            if "symbol" in df.columns:
                symbols = [str(s) for s in df["symbol"].dropna().astype(str).tolist()]
        except Exception as e:
            print(f"⚠ Unable to read CSV '{args.from_csv}': {e}")
    if args.symbols:
        symbols += [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    symbols = sorted(set(symbols))

    if not symbols:
        print("✗ No symbols provided")
        return 1

    print(f"Fetching StockNewsAPI for {len(symbols)} symbols...")
    try:
        news_map = fetch_stocknews_news(symbols, mode=args.mode, items=args.items, page=1, token=(args.token or None))
    except Exception as e:
        print(f"✗ StockNewsAPI error: {e}")
        return 2

    # Filter and sort per symbol
    out_map: Dict[str, List[dict]] = {}
    for sym in symbols:
        arts = news_map.get(sym, [])
        arts_sorted = _sort_desc_by_created(arts)
        if args.recent_only:
            arts_sorted = _filter_recent_today_yesterday(arts_sorted)
        if args.per_symbol_limit > 0:
            arts_sorted = arts_sorted[: args.per_symbol_limit]
        out_map[sym] = arts_sorted

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out_map, f, indent=2)
    print(f"✓ Saved {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
